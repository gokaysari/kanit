from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Protocol

from .models import CheckResult, FlowCheck, Verdict

MAX_CHANGED_FLOWS = 20

# Batfish'in 'SUCCESS' / 'FAILURE' eylem kümeleriyle aynı ayrım. Bu kümelerde olmayan
# bir disposition görülürse akış sınıflandırılamaz ve kapalı yönde karar verilir.
SUCCESS_DISPOSITIONS = frozenset({"ACCEPTED", "DELIVERED_TO_SUBNET", "EXITS_NETWORK"})
FAILURE_DISPOSITIONS = frozenset(
    {
        "DENIED_IN",
        "DENIED_OUT",
        "NO_ROUTE",
        "NULL_ROUTED",
        "NEIGHBOR_UNREACHABLE",
        "INSUFFICIENT_INFO",
        "LOOP",
    }
)


class Verifier(Protocol):
    def verify(
        self,
        base: Path,
        candidate: Path,
        invariants: list[FlowCheck],
        intent_checks: list[FlowCheck],
    ) -> Verdict: ...


def _disposition(traces) -> str:
    try:
        return str(traces[0].disposition)
    except Exception:
        return "?"


_LOCATION_ANY = re.compile(
    r"(InterfaceLinkLocation|InterfaceLocation)\{nodeName=([^,{}\"]+), "
    r"interfaceName=([^{}\"]+)\}"
)
_LOCATION = re.compile(f"^{_LOCATION_ANY.pattern}$")


class _Unresolved(Exception):
    """Başlangıç konumları güvenilir biçimde çözülemedi; kapalı yönde karar verilir."""


def _location_list(value) -> list[str]:
    """resolveIpsOfLocationSpecifier'ın 'Locations' hücresi: liste ya da "[a, b]" metni.

    Metin, tanınan konumların ", " ile birleşimine birebir eşit değilse çözülemedi
    sayılır (bir konumu sessizce atlamamak için)."""
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    text = str(value)
    found = [m.group(0) for m in _LOCATION_ANY.finditer(text)]
    if f"[{', '.join(found)}]" != text:
        raise _Unresolved(f"konum listesi okunamadı: {text[:200]}")
    return found


def _dispositions(traces) -> set[str]:
    """Bir akışın tüm izlerindeki disposition'lar (çok yollu akışta birden fazla)."""
    return {str(t.disposition) for t in traces}


class BatfishVerifier:
    """Mevcut ve aday snapshot'ı Batfish'e yükler, kontrolleri aday üzerinde çalıştırır."""

    def __init__(self, host: str = "localhost"):
        self.host = host

    def verify(self, base, candidate, invariants, intent_checks) -> Verdict:
        from pybatfish.client.session import Session

        bf = Session(host=self.host)
        network = f"kanit-{uuid.uuid4().hex[:8]}"
        bf.set_network(network)
        try:
            bf.init_snapshot(str(base), name="base", overwrite=True)
            bf.init_snapshot(str(candidate), name="cand", overwrite=True)

            verdict = Verdict()
            verdict.new_parse_issues = self._new_rows(
                bf, "initIssues", ["Type", "Details", "Line_Text"]
            )
            verdict.new_undefined_refs = self._new_rows(
                bf, "undefinedReferences", ["File_Name", "Struct_Type", "Ref_Name", "Context"]
            )
            for kind, checks in (("invariant", invariants), ("intent", intent_checks)):
                for check in checks:
                    example = self._violation(bf, check, "cand")
                    result = CheckResult(check, kind, example is None, example)
                    if kind == "invariant" and example is not None:
                        self._classify_preexisting(bf, result)
                    elif kind == "invariant" and check.expect == "reachable":
                        self._check_lost_locations(bf, result)
                    verdict.checks.append(result)
            verdict.changed_flows = self._changed_flows(bf)
            return verdict
        finally:
            try:
                bf.delete_network(network)
            except Exception:
                pass

    @staticmethod
    def _frame(bf, question: str, snapshot: str):
        return getattr(bf.q, question)().answer(snapshot=snapshot).frame()

    def _new_rows(self, bf, question: str, columns: list[str]) -> list[str]:
        def keys(snapshot: str) -> list[str]:
            df = self._frame(bf, question, snapshot)
            cols = [c for c in columns if c in df.columns]
            return [" | ".join(str(row[c]) for c in cols) for _, row in df.iterrows()]

        before = set(keys("base"))
        return [k for k in keys("cand") if k not in before]

    @staticmethod
    def _headers(check: FlowCheck):
        from pybatfish.datamodel.flow import HeaderConstraints

        return HeaderConstraints(
            srcIps=check.src,
            dstIps=check.dst,
            ipProtocols=[check.protocol] if check.protocol else None,
            dstPorts=check.dst_ports,
        )

    @staticmethod
    def _bad_actions(check: FlowCheck) -> str:
        """Beklentiyi bozan eylem: 'reachable' için FAILURE, 'blocked' için SUCCESS."""
        return "FAILURE" if check.expect == "reachable" else "SUCCESS"

    @classmethod
    def _violation(
        cls, bf, check: FlowCheck, snapshot: str, start: str | None = None
    ) -> str | None:
        """Beklentiyi bozan bir akış varsa onu döndürür; yoksa None (kanıtlandı).

        `start` verilirse değişmezin başlangıç noktası yerine o konumlarda aranır."""
        from pybatfish.datamodel.flow import PathConstraints

        df = (
            bf.q.reachability(
                pathConstraints=PathConstraints(startLocation=start or check.start),
                headers=cls._headers(check),
                actions=cls._bad_actions(check),
            )
            .answer(snapshot=snapshot)
            .frame()
        )
        if len(df) == 0:
            return None
        row = df.iloc[0]
        return f"{row['Flow']} => {_disposition(row['Traces'])}"

    def _classify_preexisting(self, bf, result: CheckResult) -> None:
        """Adayda ihlal edilen değişmezin önceden var olan ihlal sayılıp sayılmayacağı.

        Garanti: `preexisting=True` yalnızca şunların hepsi gösterildiğinde konur:
        (1) Başlangıç konumları: değişmezin `start`'ının adayda çözüldüğü her etkin konum,
            mevcutta da aynı durumda (etkin, kaynak IP uzayı boş/dolu aynı) vardır. Böyle
            olmayan (yeni, yeni etkinleşen ya da kaynak uzayı boş/dolu değişen) konumlar
            için adayda o konumlarla sınırlı düz `reachability` ihlal bulmamalıdır.
            `reachable` değişmezinde mevcutta etkin olup adayda kaybolan konum, o
            konumdan erişimin kaybıdır ve ihlal sayılır. `blocked` değişmezinde kaybolan
            konum ihlali genişletemez (oradan akış başlamaz).
        (2) Ortak konumlarda değişmezin başlık uzayıyla sınırlı `differentialReachability`
            mevcutta beklentiyi sağlayıp adayda bozan akış göstermez.
        (3) Mevcut snapshot bu değişmezi gerçekten ihlal ediyor.
        Bunlar, değişmezin başlık uzayında ve adaydaki tüm etkin başlangıç konumlarında
        adayın ihlal kümesinin mevcudun ihlal kümesinin alt kümesi olduğunu gösterir
        (ihlal genişlemedi; daralmış ya da aynı kalmış olabilir). Raporlardaki "bu
        değişiklik ihlali genişletmiyor (kanıtlandı)" ifadesi tam olarak bu iddiadır ve
        aşağıdaki Batfish davranışına dayanır. Genişleme varsa sonuç ihlaldir ve karşı
        örnek adayda YENİ bozulan akıştır.

        Dayandığı Batfish davranışı (belgelenmemiş, testle sabit): `differentialReachability`
        yalnızca iki snapshot'ta da var ve etkin olan konumları tarar (bu yüzden (1)
        gerekir) ve her konum için "adayda artan" ve "adayda azalan" kümelerden ayrı birer
        örnek döndürür. Sonuç boşsa ortak konumlarda iki ihlal kümesi eşittir. Dolu
        sonuçta yalnızca daralma örnekleri varsa, genişleme kümesi boş olmasaydı ondan da
        örnek dönecekti; tests/test_preexisting_batfish.py'deki aynı anda genişleten ve
        daraltan senaryo bunu, arayüz adresi değişen senaryo da kaynak uzayı değişen ortak
        konumun taranmasını sabitler.

        Kapalı yön: konum kümesi çözülemezse, sınıflandırılamayan örnek (boş iz, bilinmeyen
        disposition, iki tarafta aynı durum) görülürse genişleme sayılır. Yeni konumda
        bulunan her ihlal, mevcutta başka bir konumdan zaten mümkün olsa bile ret
        sebebidir: bu yanlış ret üretebilir, yanlış kabul üretmez.

        Garanti etmez: mevcuttaki ihlalin kabul edilebilir olduğunu (ürün kararı; ihlal
        raporda görünür kalır); değişmezin başlık uzayı dışındaki davranışı (madde 3).
        """
        check = result.check
        try:
            new_locations, lost = self._location_delta(bf, check)
            widened = None
            if lost and check.expect == "reachable":
                widened = self._lost_message(lost)
            if widened is None and new_locations:
                example = self._violation(bf, check, "cand", start=", ".join(new_locations))
                if example is not None:
                    widened = f"{example} (yeni başlangıç konumunda ihlal)"
        except _Unresolved as exc:
            widened = (
                f"başlangıç konumları karşılaştırılamadı ({exc}); "
                "genişleme olmadığı kanıtlanamadı"
            )
        if widened is None:
            widened = self._widening(bf, check)
        if widened is not None:
            result.counterexample = widened
            result.preexisting = False
            return
        # Genişleme yoksa mevcut da ihlal ediyor olmalı; değilse sonuçlar çelişiyordur
        # ve kapalı yönde (ihlal) karar verilir.
        result.preexisting = self._violation(bf, check, "base") is not None

    def _check_lost_locations(self, bf, result: CheckResult) -> None:
        """Adayda kanıtlanmış `reachable` değişmezi: mevcutta etkin olan bir başlangıç
        konumu adayda yoksa ya da etkin değilse, o konumdan erişim kaybolmuştur.

        Adaydaki `reachability` yalnızca adayda var olan konumlara bakar; kaybolan konumu
        görmez. Bu yüzden kayıp ayrıca ihlal sayılır (kapalı yön)."""
        try:
            _, lost = self._location_delta(bf, result.check)
        except _Unresolved as exc:
            result.passed = False
            result.counterexample = (
                f"başlangıç konumları karşılaştırılamadı ({exc}); erişimin korunduğu "
                "kanıtlanamadı"
            )
            return
        if lost:
            result.passed = False
            result.counterexample = self._lost_message(lost)

    @staticmethod
    def _lost_message(lost: list[str]) -> str:
        return (
            f"başlangıç konumu adayda yok ya da etkin değil: {', '.join(lost)}; "
            "o konumdan erişim kayboldu"
        )

    @classmethod
    def _location_delta(cls, bf, check: FlowCheck) -> tuple[list[str], list[str]]:
        """(adayda ortak olmayan etkin konumların belirteçleri, kaybolan etkin konumlar).

        Ortak konum: iki snapshot'ta da etkin ve kaynak IP uzayı ikisinde de boş ya da
        ikisinde de dolu. Ortak olmayan her aday konumu ayrıca düz `reachability` ile
        sınanır; bu, konumun değişip değişmediğini bilmekten daha sıkıdır (kapalı yön).
        """
        base = cls._location_states(bf, check.start, "base")
        cand = cls._location_states(bf, check.start, "cand")
        new_specs = [
            spec
            for loc, (spec, active, ips) in sorted(cand.items())
            if active and base.get(loc, (None, False, None))[1:] != (True, ips)
        ]
        lost = [
            loc
            for loc, (_, active, _) in sorted(base.items())
            if active and not cand.get(loc, (None, False, None))[1]
        ]
        return new_specs, lost

    @staticmethod
    def _location_states(bf, start: str, snapshot: str) -> dict[str, tuple[str, bool, bool]]:
        """`start`'ın çözüldüğü konumlar.

        {konum: (reachability belirteci, etkin mi, kaynak IP uzayı dolu mu)}"""
        names = bf.q.resolveLocationSpecifier(locations=start).answer(snapshot=snapshot).frame()
        expected = {str(loc) for loc in names["Location"]}
        ips_df = (
            bf.q.resolveIpsOfLocationSpecifier(locations=start)
            .answer(snapshot=snapshot)
            .frame()
        )
        has_ips: dict[str, bool] = {}
        for _, row in ips_df.iterrows():
            for loc in _location_list(row["Locations"]):
                has_ips[loc] = str(row["IP_Space"]).strip().lower() != "empty"
        if set(has_ips) != expected:
            raise _Unresolved(f"{snapshot}: konum ve IP uzayı listeleri uyuşmuyor")

        props = (
            bf.q.interfaceProperties(properties="Active").answer(snapshot=snapshot).frame()
        )
        active: dict[tuple[str, str], bool] = {}
        for _, row in props.iterrows():
            flag = str(row["Active"])
            if flag not in ("True", "False"):
                raise _Unresolved(f"{snapshot}: arayüz etkinliği okunamadı ({flag})")
            iface = row["Interface"]
            active[(str(iface.hostname).lower(), str(iface.interface))] = flag == "True"

        out: dict[str, tuple[str, bool, bool]] = {}
        for loc in expected:
            m = _LOCATION.match(loc)
            if not m:
                raise _Unresolved(f"{snapshot}: tanınmayan konum {loc}")
            kind, node, iface = m.groups()
            key = (node.lower(), iface)
            if key not in active:
                raise _Unresolved(f"{snapshot}: {node}[{iface}] arayüz listesinde yok")
            spec = f'"{node}"["{iface}"]'
            if kind == "InterfaceLinkLocation":
                spec = f"@enter({spec})"
            out[loc] = (spec, active[key], has_ips[loc])
        return out

    @classmethod
    def _widening(cls, bf, check: FlowCheck) -> str | None:
        """Mevcutta beklentiyi sağlayıp adayda bozan bir akış; kanıtla yoksa None."""
        from pybatfish.datamodel.flow import PathConstraints

        bad = SUCCESS_DISPOSITIONS if check.expect == "blocked" else FAILURE_DISPOSITIONS
        df = (
            bf.q.differentialReachability(
                pathConstraints=PathConstraints(startLocation=check.start),
                headers=cls._headers(check),
                actions=cls._bad_actions(check),
            )
            .answer(snapshot="cand", reference_snapshot="base")
            .frame()
        )
        for _, row in df.iterrows():
            before = _dispositions(row["Reference_Traces"])
            after = _dispositions(row["Snapshot_Traces"])
            known = SUCCESS_DISPOSITIONS | FAILURE_DISPOSITIONS
            if not before or not after or not (before | after) <= known:
                return (
                    f"{row['Flow']}: sınıflandırılamayan sonuç "
                    f"({sorted(before) or '?'} -> {sorted(after) or '?'}); "
                    "genişleme olmadığı kanıtlanamadı"
                )
            bad_before, bad_after = bool(before & bad), bool(after & bad)
            if bad_after and not bad_before:
                return f"{row['Flow']} => {_disposition(row['Snapshot_Traces'])} (yeni ihlal)"
            if bad_before and not bad_after:
                continue  # ihlal daraldı; bu örnek genişleme değil
            return (
                f"{row['Flow']}: iki snapshot'ta aynı durumda döndü "
                f"({sorted(before)} -> {sorted(after)}); genişleme olmadığı kanıtlanamadı"
            )
        return None

    @staticmethod
    def _changed_flows(bf) -> list[str]:
        df = (
            bf.q.differentialReachability()
            .answer(snapshot="cand", reference_snapshot="base")
            .frame()
        )
        out = []
        for _, row in df.head(MAX_CHANGED_FLOWS).iterrows():
            before = _disposition(row["Reference_Traces"])
            after = _disposition(row["Snapshot_Traces"])
            out.append(f"{row['Flow']}: {before} -> {after}")
        return out
