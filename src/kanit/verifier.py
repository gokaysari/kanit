from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from .models import CheckResult, FlowCheck, Verdict

MAX_CHANGED_FLOWS = 20


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
                        result.preexisting = self._violation(bf, check, "base") is not None
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
    def _violation(bf, check: FlowCheck, snapshot: str) -> str | None:
        """Beklentiyi bozan bir akış varsa onu döndürür; yoksa None (kanıtlandı)."""
        from pybatfish.datamodel.flow import HeaderConstraints, PathConstraints

        headers = HeaderConstraints(
            srcIps=check.src,
            dstIps=check.dst,
            ipProtocols=[check.protocol] if check.protocol else None,
            dstPorts=check.dst_ports,
        )
        # 'reachable' için başarısız olan akış, 'blocked' için başarılı olan akış aranır.
        actions = "FAILURE" if check.expect == "reachable" else "SUCCESS"
        df = (
            bf.q.reachability(
                pathConstraints=PathConstraints(startLocation=check.start),
                headers=headers,
                actions=actions,
            )
            .answer(snapshot=snapshot)
            .frame()
        )
        if len(df) == 0:
            return None
        row = df.iloc[0]
        return f"{row['Flow']} => {_disposition(row['Traces'])}"

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
