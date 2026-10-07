from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .models import Proposal, ProposalError, Usage, Verdict
from .proposer import Proposer, ProposerError
from .snapshot import (
    UnsupportedLayout,
    apply_edits,
    read_configs,
    read_invariants,
    write_candidate,
)
from .verifier import Verifier


@dataclass
class Round:
    proposal: Proposal | None
    verdict: Verdict
    candidate_configs: dict[str, str] | None = None
    usage: Usage = field(default_factory=Usage)


@dataclass
class Result:
    intent: str
    base_configs: dict[str, str]
    rounds: list[Round] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str | None = None
    error: str | None = None  # döngü öneri alamadan durdu (API hatası vb.)

    @property
    def accepted(self) -> bool:
        return self.error is None and bool(self.rounds) and self.rounds[-1].verdict.accepted

    @property
    def final(self) -> Round | None:
        return self.rounds[-1] if self.rounds else None


def run(
    intent: str,
    snapshot: Path,
    proposer: Proposer,
    verifier: Verifier,
    max_rounds: int = 3,
) -> Result:
    """Öner -> doğrula -> karşı örnekle düzelt. Yalnızca doğrulanan öneri kabul edilir.

    Mevcut ve aday Batfish'e aynı yoldan (`write_candidate`, yalnızca `configs/`) gider;
    böylece iki taraf aynı türde dosya kümesiyle karşılaştırılır. Doğrulayıcının
    istisnası (Batfish'e ulaşılamadı, beklenmeyen cevap) döngüyü durdurur ve
    `result.error` olur: doğrulama çalışmadı, kabul edilmez (çıkış 2). Kontrolün
    kendisinin başarısız olması (ör. niyetin başlangıç konumu adayda çözülmüyor) istisna
    değil, rettir; geri bildirim modele gider ve döngü sürer."""
    model = getattr(proposer, "model", None)
    try:
        base_configs = read_configs(snapshot)
    except UnsupportedLayout as exc:
        return Result(intent, {}, model=model, error=f"Snapshot desteklenmeyen düzende: {exc}")
    invariants = read_invariants(snapshot)
    result = Result(intent, base_configs, model=model)
    feedback: str | None = None

    with tempfile.TemporaryDirectory(prefix="kanit-") as tmp:
        base_dir = write_candidate(base_configs, Path(tmp) / "base")
        for i in range(max_rounds):
            before = proposer.usage.copy()
            try:
                raw = proposer.propose(feedback)
            except ProposerError as exc:
                result.error = str(exc)
                break
            finally:
                result.usage = proposer.usage.copy()
            spent = proposer.usage - before
            try:
                proposal = Proposal.from_dict(raw)
                candidate = apply_edits(base_configs, proposal)
            except ProposalError as exc:
                verdict = Verdict(error=str(exc))
                result.rounds.append(Round(None, verdict, usage=spent))
                feedback = verdict.feedback()
                continue

            cand_dir = write_candidate(candidate, Path(tmp) / f"round-{i + 1}")
            try:
                verdict = verifier.verify(
                    base_dir, cand_dir, invariants, list(proposal.intent_checks)
                )
            except Exception as exc:  # noqa: BLE001 - result.error olarak raporlanır
                result.error = f"Batfish doğrulaması çalışmadı: {type(exc).__name__}: {exc}"
                break
            result.rounds.append(Round(proposal, verdict, candidate, spent))
            if verdict.accepted:
                break
            feedback = verdict.feedback()
    return result
