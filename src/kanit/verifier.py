from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
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


class _NoSources(Exception):
    """Batfish sorgunun akış kümesinin boş olduğunu söyledi: `start` o snapshot'ta etkin
    hiçbir konuma çözülmüyor ya da çözüldüğü konumların kaynak IP uzayı boş."""


# reachability, akış kümesi boş olduğunda tablo yerine bu metinlerden birini içeren bir
# StringAnswerElement döndürür (durum SUCCESS). Gerçek Batfish'te gözlendi; testle sabit
# (tests/test_location_batfish.py). Başka her tablo dışı cevap beklenmeyen hatadır.
EMPTY_SOURCE_ANSWERS = frozenset(
    {"No matching source locations", "All sources have empty source IpSpaces"}
)


def _table(answer):
    """Batfish cevabının tablosu. Boş akış kümesi `_NoSources`, başka her tablo dışı
    cevap RuntimeError (beklenmeyen Batfish hatası: doğrulama çalışmadı)."""
    if hasattr(answer, "frame"):
        return answer.frame()
    try:
        texts = [str(e.get("answer")) for e in answer["answerElements"]]
        status = str(answer.get("status"))
    except Exception:  # noqa: BLE001 - biçim tanınmadı; aşağıda hata olarak yükselir
        texts, status = [], "?"
    if status == "SUCCESS" and len(texts) == 1 and texts[0] in EMPTY_SOURCE_ANSWERS:
        raise _NoSources(texts[0])
    raise RuntimeError(f"Batfish beklenmeyen bir cevap döndürdü: {str(answer)[:500]}")


# Ağın tamamındaki başlangıç konumları: arayüze dışarıdan giren akışlar ve cihazın kendi
# arayüzünden çıkan akışlar. Yeni konumdan giren akışın kaynağı herhangi bir adres
# olabilir (Batfish'in bağlantı için çıkardığı kaynak uzayı /30 gibi bağlantılarda boştur).
NETWORK_UNIVERSES = (("@enter(/.*/[/.*/])", "0.0.0.0/0"), ("/.*/", None))


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


@dataclass(frozen=True)
class _Delta:
    """Bir başlangıç konumu belirtecinin iki snapshot'taki farkı.

    new: adayda etkin olup ortak olmayan konumların reachability belirteçleri.
    lost: mevcutta etkin olup adayda olmayan ya da etkin olmayan konumlar.
    common: iki snapshot'ta da ortak (etkin, aynı kaynak uzayı durumu) konum var mı.
    resolved: belirteç iki snapshot'tan en az birinde en az bir konuma çözüldü mü.
    """

    new: list[str]
    lost: list[str]
    lost_specs: list[str]
    common: bool
    resolved: bool


class BatfishVerifier:
    """Mevcut ve aday snapshot'ı Batfish'e yükler, kontrolleri aday üzerinde çalıştırır."""

    def __init__(self, host: str = "localhost"):
        self.host = host

    def verify(self, base, candidate, invariants, intent_checks) -> Verdict:
        """Değişmezleri ve niyet kontrollerini aday üzerinde kanıtlar, etkiyi listeler.

        Hata yönü: Batfish'in beklenmeyen her cevabı ya da istisnası yükselir (çağıran
        "doğrulama çalışmadı" der, çıkış 2). Boş başlangıç kümesi beklenen bir durumdur
        ve kontrolün kendisinde karara bağlanır (`_evaluate`).
        """
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
            network_delta = self._network_delta(bf)
            for kind, checks in (("invariant", invariants), ("intent", intent_checks)):
                for check in checks:
                    verdict.checks.append(self._evaluate(bf, check, kind, network_delta))
            verdict.changed_flows = self._changed_flows(bf, network_delta)
            return verdict
        finally:
            try:
                bf.delete_network(network)
            except Exception:
                pass

    def _evaluate(self, bf, check: FlowCheck, kind: str, network_delta) -> CheckResult:
        """Tek kontrol. `passed=True` yalnızca şunlar gösterildiğinde konur:

        - Adayda `start`'ın etkin konumlarından beklentiyi bozan akış yok (reachability
          boş; örnek ile küme: boş sonuç kanıttır).
        - `reachable`: mevcutta etkin olan hiçbir başlangıç konumu adayda kaybolmadı
          (kaybolan konumdan erişim kaybıdır; adaydaki sorgu onu göremez).
        - `blocked`: kaybolan konum ihlal değildir (oradan akış başlamaz). Ancak aynı
          adayda ağın herhangi bir yerinde yeni etkin konum varsa, kaybolan konum yeni
          adla (hostname ya da arayüz adı değişikliği) sürüyor olabilir; kontrolün başlık
          uzayı o yeni konumlardan da sınanır ve ihlal varsa kontrol başarısızdır.

        Boş başlangıç kümesi (Batfish "No matching source locations" / "All sources have
        empty source IpSpaces"):
        - niyet kontrolü: her zaman başarısız (kapalı yön; model start'ı düzeltmeli).
        - değişmez, `start` iki snapshot'ta da hiçbir arayüze çözülmüyor: başarısız
          (değişmez sınanamaz; policy.json düzeltilmeli). Önceden var olan sayılmaz.
        - `reachable` değişmez: başarısız ("erişim kayboldu" ya da konum iki tarafta da
          akış üretmiyorsa önceden var olan ihlal).
        - `blocked` değişmez: yukarıdaki `blocked` kuralı (kayıp + yeniden adlandırma).

        Kapalı yön: konumlar karşılaştırılamazsa (`_Unresolved`) kontrol başarısızdır.
        """
        try:
            example = self._violation(bf, check, "cand")
        except _NoSources as exc:
            return self._no_sources(bf, check, kind, str(exc), network_delta)
        result = CheckResult(check, kind, example is None, example)
        if kind == "invariant" and example is not None:
            self._classify_preexisting(bf, result, network_delta)
        elif example is None:
            self._check_lost_locations(bf, result, network_delta)
        return result

    def _no_sources(self, bf, check, kind, reason, network_delta) -> CheckResult:
        result = CheckResult(check, kind, False)
        try:
            delta = self._location_delta(bf, check.start)
        except _Unresolved as exc:
            result.counterexample = (
                f"başlangıç konumları karşılaştırılamadı ({exc}); kontrol kanıtlanamadı"
            )
            return result
        if not delta.resolved:
            result.counterexample = (
                f"başlangıç konumu ('{check.start}') iki snapshot'ta da hiçbir arayüze "
                "çözülmüyor; kontrol sınanamadı"
            )
            return result
        if delta.lost and check.expect == "reachable":
            result.counterexample = self._lost_message(delta.lost)
            return result
        if kind == "intent":
            result.counterexample = (
                f"başlangıç konumu ('{check.start}') adayda etkin ve kaynak adresi olan "
                f"hiçbir konuma çözülmüyor (Batfish: {reason}); niyet sınanamadı"
            )
            return result
        if check.expect == "blocked":
            # Adayda bu konumlardan hiçbir akış başlamıyor; engellenmeli olan akış yok.
            result.passed = True
            result.counterexample = None
            self._check_lost_locations(bf, result, network_delta, delta)
            return result
        # reachable değişmez, kaybolan konum yok: mevcutta da akış üretmiyorsa ihlal
        # önceden de vardı ve genişlemedi (iki tarafta da boş küme).
        result.counterexample = (
            f"başlangıç konumu ('{check.start}') adayda akış üretmiyor (Batfish: {reason}); "
            "erişim yok"
        )
        try:
            self._violation(bf, check, "base")
        except _NoSources:
            result.preexisting = True
        return result

    @staticmethod
    def _frame(bf, question: str, snapshot: str):
        return _table(getattr(bf.q, question)().answer(snapshot=snapshot))

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

        `start` verilirse değişmezin başlangıç noktası yerine o konumlarda aranır.
        Akış kümesi boşsa (başlangıç etkin hiçbir konuma çözülmüyor) `_NoSources`
        yükseltir; bunun ihlal olup olmadığına çağıran beklentiye göre karar verir."""
        from pybatfish.datamodel.flow import PathConstraints

        df = _table(
            bf.q.reachability(
                pathConstraints=PathConstraints(startLocation=start or check.start),
                headers=cls._headers(check),
                actions=cls._bad_actions(check),
            ).answer(snapshot=snapshot)
        )
        if len(df) == 0:
            return None
        row = df.iloc[0]
        return f"{row['Flow']} => {_disposition(row['Traces'])}"

    @classmethod
    def _violation_at(cls, bf, check: FlowCheck, snapshot: str, specs: list[str]) -> str | None:
        """`_violation`, verilen konumlarla sınırlı; konumların akış kümesi boşsa None."""
        if not specs:
            return None
        try:
            return cls._violation(bf, check, snapshot, start=", ".join(specs))
        except _NoSources:
            return None

    def _classify_preexisting(self, bf, result: CheckResult, network_delta) -> None:
        """Adayda ihlal edilen değişmezin önceden var olan ihlal sayılıp sayılmayacağı.

        Garanti: `preexisting=True` yalnızca şunların hepsi gösterildiğinde konur:
        (1) Başlangıç konumları: değişmezin `start`'ının adayda çözüldüğü her etkin konum,
            mevcutta da aynı durumda (etkin, kaynak IP uzayı boş/dolu aynı) vardır. Böyle
            olmayan (yeni, yeni etkinleşen ya da kaynak uzayı boş/dolu değişen) konumlar
            için adayda o konumlarla sınırlı düz `reachability` ihlal bulmamalıdır.
            `reachable` değişmezinde mevcutta etkin olup adayda kaybolan konum, o
            konumdan erişimin kaybıdır ve ihlal sayılır. `blocked` değişmezinde kaybolan
            konum ihlali genişletemez (oradan akış başlamaz); ama ağda yeni konum varsa
            kaybolan konum yeni adla sürüyor olabilir, o yeni konumlarda da ihlal
            aranır (`_check_lost_locations` ile aynı kural).
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
        gerekir; ortak konum yoksa hata verdiği için o durumda çağrılmaz) ve her konum
        için "adayda artan" ve "adayda azalan" kümelerden ayrı birer örnek döndürür.
        Sonuç boşsa ortak konumlarda iki ihlal kümesi eşittir. Dolu sonuçta yalnızca
        daralma örnekleri varsa, genişleme kümesi boş olmasaydı ondan da örnek dönecekti;
        tests/test_preexisting_batfish.py'deki aynı anda genişleten ve daraltan senaryo
        bunu, arayüz adresi değişen senaryo da kaynak uzayı değişen ortak konumun
        taranmasını sabitler.

        Kapalı yön: konum kümesi çözülemezse, sınıflandırılamayan örnek (boş iz, bilinmeyen
        disposition, iki tarafta aynı durum) görülürse genişleme sayılır. Yeni konumda
        bulunan her ihlal, mevcutta başka bir konumdan zaten mümkün olsa bile ret
        sebebidir: bu yanlış ret üretebilir, yanlış kabul üretmez. Mevcutta akış kümesi
        boşsa (3) sağlanmaz ve ihlal sayılır.

        Garanti etmez: mevcuttaki ihlalin kabul edilebilir olduğunu (ürün kararı; ihlal
        raporda görünür kalır); değişmezin başlık uzayı dışındaki davranışı (madde 3).
        """
        check = result.check
        delta: _Delta | None = None
        try:
            delta = self._location_delta(bf, check.start)
            widened = None
            if delta.lost and check.expect == "reachable":
                widened = self._lost_message(delta.lost)
            if widened is None and delta.new:
                example = self._violation_at(bf, check, "cand", delta.new)
                if example is not None:
                    widened = f"{example} (yeni başlangıç konumunda ihlal)"
            if widened is None and delta.lost and check.expect == "blocked":
                widened = self._renamed_violation(bf, check, delta, network_delta)
        except _Unresolved as exc:
            widened = (
                f"başlangıç konumları karşılaştırılamadı ({exc}); "
                "genişleme olmadığı kanıtlanamadı"
            )
        if widened is None and delta is not None and delta.common:
            widened = self._widening(bf, check)
        if widened is not None:
            result.counterexample = widened
            result.preexisting = False
            return
        # Genişleme yoksa mevcut da ihlal ediyor olmalı; değilse sonuçlar çelişiyordur
        # ve kapalı yönde (ihlal) karar verilir.
        try:
            result.preexisting = self._violation(bf, check, "base") is not None
        except _NoSources:
            result.preexisting = False

    def _check_lost_locations(
        self, bf, result: CheckResult, network_delta, delta: _Delta | None = None
    ) -> None:
        """Adayda kanıtlanmış kontrol (değişmez ya da niyet) için kaybolan konumlar.

        `reachable`: mevcutta etkin olan bir başlangıç konumu adayda yoksa ya da etkin
        değilse, o konumdan erişim kaybolmuştur. Adaydaki `reachability` yalnızca adayda
        var olan konumlara bakar; kaybolan konumu görmez. Bu yüzden kayıp ayrıca ihlal
        sayılır (kapalı yön).

        `blocked`: kaybolan konum ihlal değildir; yalnızca ağda yeni konum varsa
        `_renamed_violation` ile yeni konumlarda ihlal aranır."""
        try:
            if delta is None:
                delta = self._location_delta(bf, result.check.start)
            failure = None
            if delta.lost and result.check.expect == "reachable":
                failure = self._lost_message(delta.lost)
            elif delta.lost:
                failure = self._renamed_violation(bf, result.check, delta, network_delta)
        except _Unresolved as exc:
            failure = (
                f"başlangıç konumları karşılaştırılamadı ({exc}); kontrolün korunduğu "
                "kanıtlanamadı"
            )
        if failure is not None:
            result.passed = False
            result.counterexample = failure

    @classmethod
    def _renamed_violation(cls, bf, check: FlowCheck, delta: _Delta, network_delta):
        """`blocked` kontrolünün bir konumu kayboldu ve ağda yeni etkin konumlar var.

        Batfish konumu ada göre tanır; hostname ya da arayüz adı değişince eski konum
        kaybolur, aynı arayüz yeni adla gelir ve kontrolün `start`'ı onu kapsamaz. Hangi
        yeni konumun hangi eskisinin devamı olduğu bilinemediği için kontrolün başlık
        uzayı bütün yeni konumlardan sınanır (kapalı yön: yanlış ret üretebilir, yanlış
        kabul üretmez)."""
        new_specs = [spec for spec, _ in network_delta.new_specs]
        example = cls._violation_at(bf, check, "cand", new_specs)
        if example is None:
            return None
        return (
            f"{example} (başlangıç konumu adayda kayboldu: {', '.join(delta.lost)}; ağdaki "
            "yeni bir konumda engellenmesi gereken akış geçiyor, konum yeni adla sürüyor "
            "olabilir)"
        )

    @staticmethod
    def _lost_message(lost: list[str]) -> str:
        return (
            f"başlangıç konumu adayda yok ya da etkin değil: {', '.join(lost)}; "
            "o konumdan erişim kayboldu"
        )

    @classmethod
    def _location_delta(cls, bf, start: str, compare_ips: bool = True) -> _Delta:
        """`start` belirtecinin iki snapshot arasındaki konum farkı (bkz. `_Delta`).

        Ortak konum: iki snapshot'ta da etkin ve (compare_ips ise) kaynak IP uzayı ikisinde
        de boş ya da ikisinde de dolu. Ortak olmayan her aday konumu ayrıca düz
        `reachability` ile sınanır; bu, konumun değişip değişmediğini bilmekten daha
        sıkıdır (kapalı yön).
        """
        base = cls._location_states(bf, start, "base")
        cand = cls._location_states(bf, start, "cand")

        def same(loc, ips, other):
            spec, active, other_ips = other.get(loc, (None, False, None))
            return active and (not compare_ips or other_ips == ips)

        new_specs = [
            spec
            for loc, (spec, active, ips) in sorted(cand.items())
            if active and not same(loc, ips, base)
        ]
        lost = sorted(
            loc for loc, (_, active, _) in base.items()
            if active and not cand.get(loc, (None, False, None))[1]
        )
        lost_specs = [base[loc][0] for loc in lost]
        common = any(
            active and same(loc, ips, base) for loc, (_, active, ips) in cand.items()
        )
        return _Delta(new_specs, lost, lost_specs, common, bool(base) or bool(cand))

    @staticmethod
    def _location_states(bf, start: str, snapshot: str) -> dict[str, tuple[str, bool, bool]]:
        """`start`'ın çözüldüğü konumlar (kapalı arayüzler dahil).

        {konum: (reachability belirteci, etkin mi, kaynak IP uzayı dolu mu)}"""
        names = _table(
            bf.q.resolveLocationSpecifier(locations=start).answer(snapshot=snapshot)
        )
        expected = {str(loc) for loc in names["Location"]} if len(names) else set()
        ips_df = _table(
            bf.q.resolveIpsOfLocationSpecifier(locations=start).answer(snapshot=snapshot)
        )
        has_ips: dict[str, bool] = {}
        for _, row in ips_df.iterrows():
            for loc in _location_list(row["Locations"]):
                has_ips[loc] = str(row["IP_Space"]).strip().lower() != "empty"
        if set(has_ips) != expected:
            raise _Unresolved(f"{snapshot}: konum ve IP uzayı listeleri uyuşmuyor")
        if not expected:
            return {}

        props = _table(
            bf.q.interfaceProperties(properties="Active").answer(snapshot=snapshot)
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
        df = _table(
            bf.q.differentialReachability(
                pathConstraints=PathConstraints(startLocation=check.start),
                headers=cls._headers(check),
                actions=cls._bad_actions(check),
            ).answer(snapshot="cand", reference_snapshot="base")
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

    @classmethod
    def _network_delta(cls, bf) -> "_NetworkDelta":
        """Ağın tamamında (NETWORK_UNIVERSES) etkinliği değişen başlangıç konumları.

        Yeni: adayda etkin, mevcutta yok ya da etkin değil. Kayıp: tersi. Kaynak uzayı
        karşılaştırılmaz; yeni konumdan giren akışın kaynağı her adres sayılır."""
        new_specs: list[tuple[str, str | None]] = []
        lost_specs: list[tuple[str, str | None]] = []
        common = False
        for universe, src in NETWORK_UNIVERSES:
            try:
                delta = cls._location_delta(bf, universe, compare_ips=False)
            except _Unresolved as exc:
                raise RuntimeError(
                    f"ağdaki başlangıç konumları karşılaştırılamadı: {exc}"
                ) from exc
            new_specs += [(spec, src) for spec in delta.new]
            lost_specs += [(spec, src) for spec in delta.lost_specs]
            common = common or delta.common
        return _NetworkDelta(new_specs, lost_specs, common)

    @classmethod
    def _location_flows(cls, bf, specs, snapshot: str) -> list:
        """Verilen konumlardan başlayan başarılı (ulaşan) örnek akışlar: (akış, disposition)."""
        from pybatfish.datamodel.flow import HeaderConstraints, PathConstraints

        out = []
        for src in sorted({s for _, s in specs}, key=str):
            starts = [spec for spec, s in specs if s == src]
            try:
                df = _table(
                    bf.q.reachability(
                        pathConstraints=PathConstraints(startLocation=", ".join(starts)),
                        headers=HeaderConstraints(srcIps=src),
                        actions="SUCCESS",
                    ).answer(snapshot=snapshot)
                )
            except _NoSources:
                continue
            for _, row in df.iterrows():
                out.append((row["Flow"], _disposition(row["Traces"])))
        return out

    @classmethod
    def _changed_flows(cls, bf, network_delta: "_NetworkDelta") -> list[str]:
        """Davranışı değişen örnek akışlar (örnek; tam liste değil).

        Garanti: adayda yeni ya da yeniden etkinleşen her başlangıç konumundan (ağın
        tamamında) ulaşan bir akış varsa, listede o konumlardan en az bir örnek bulunur
        ("(konum yok) -> ..."); kaybolan konumlardan mevcutta ulaşan akışlar da
        "... -> (konum yok)" olarak listelenir. Ortak konumlar için düz
        `differentialReachability()` örnekleri eklenir; ortak konum yoksa o sorgu
        Batfish'te hata verdiği için çağrılmaz. Her bölüm en fazla MAX_CHANGED_FLOWS.

        Garanti etmez: listenin tam olduğunu; kabul kararını etkilemez (madde 3).
        """
        out = []
        for flow, disp in cls._location_flows(bf, network_delta.new_specs, "cand")[
            :MAX_CHANGED_FLOWS
        ]:
            out.append(f"{flow}: (konum yok) -> {disp}")
        for flow, disp in cls._location_flows(bf, network_delta.lost_specs, "base")[
            :MAX_CHANGED_FLOWS
        ]:
            out.append(f"{flow}: {disp} -> (konum yok)")
        if not network_delta.common:
            return out
        df = _table(
            bf.q.differentialReachability().answer(snapshot="cand", reference_snapshot="base")
        )
        for _, row in df.head(MAX_CHANGED_FLOWS).iterrows():
            before = _disposition(row["Reference_Traces"])
            after = _disposition(row["Snapshot_Traces"])
            out.append(f"{row['Flow']}: {before} -> {after}")
        return out


@dataclass(frozen=True)
class _NetworkDelta:
    new_specs: list[tuple[str, str | None]]
    lost_specs: list[tuple[str, str | None]]
    common: bool
