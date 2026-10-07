from __future__ import annotations

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
                    if example is not None and kind == "invariant":
                        self._classify_preexisting(bf, result)
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
    def _violation(cls, bf, check: FlowCheck, snapshot: str) -> str | None:
        """Beklentiyi bozan bir akış varsa onu döndürür; yoksa None (kanıtlandı)."""
        from pybatfish.datamodel.flow import PathConstraints

        df = (
            bf.q.reachability(
                pathConstraints=PathConstraints(startLocation=check.start),
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

        Garanti: `preexisting=True` yalnızca şu iki şey kanıtlandığında konur:
        (1) değişmezin başlık uzayında (başlangıç noktası, src, dst, protokol, port)
        mevcutta beklentiyi sağlayıp adayda bozan hiçbir akış yoktur; yani adayın ihlal
        kümesi mevcudun ihlal kümesinin alt kümesidir (ihlal genişlemedi; daralmış ya da
        aynı kalmış olabilir), ve (2) mevcut snapshot gerçekten bu değişmezi ihlal ediyor.
        Genişleme varsa sonuç ihlaldir ve karşı örnek, adayda YENİ bozulan akıştır
        (adayın rastgele bir ihlal örneği değil).

        Garanti etmez: mevcuttaki ihlalin kabul edilebilir olduğunu (bu bir ürün
        kararıdır, ihlal raporda görünür kalır); değişmezin başlık uzayı dışındaki
        davranışı (o, yan etki kapısının işi, madde 3).

        Kanıt yönü: `differentialReachability`, değişmezi bozan eylem kümesi için iki
        snapshot arasında farklı davranan akışları arar ve her başlangıç noktası için
        "adayda artan" ve "adayda azalan" kümelerden ayrı ayrı birer örnek döndürür.
        Sonuç boşsa iki ihlal kümesi bu uzayda eşittir (kanıt). Dolu sonuçta yalnızca
        örneklere bakılır: adayda bozan/mevcutta bozmayan bir örnek genişlemedir;
        yalnızca daralma örnekleri varsa, Batfish genişleme kümesi boş olmasaydı ondan
        da örnek döndürecekti (bunu tests/test_preexisting_batfish.py'deki aynı anda
        genişleten ve daraltan senaryo sabitler). Sınıflandırılamayan her örnek (boş
        iz, bilinmeyen disposition, iki tarafta da aynı durum) kapalı yönde genişleme
        sayılır.
        """
        widened = self._widening(bf, result.check)
        if widened is not None:
            result.counterexample = widened
            result.preexisting = False
            return
        # Genişleme yoksa mevcut da ihlal ediyor olmalı; değilse sonuçlar çelişiyordur
        # ve kapalı yönde (ihlal) karar verilir.
        result.preexisting = self._violation(bf, result.check, "base") is not None

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
