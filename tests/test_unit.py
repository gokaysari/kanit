import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanit import loop, report
from kanit.models import CheckResult, FlowCheck, Proposal, ProposalError, Verdict
from kanit.proposer import ClaudeProposer, ScriptedProposer
from kanit.snapshot import apply_edits, read_configs, read_invariants

ACME = Path(__file__).parent.parent / "examples" / "acme"
BAD = ACME / "scripted" / "01-fazla-genis.json"
GOOD = ACME / "scripted" / "02-dogru.json"


def load(path):
    return Proposal.from_dict(json.loads(path.read_text()))


class FakeVerifier:
    """'permit ip' içeren adayı SSH değişmezini ihlal ediyor sayar."""

    def __init__(self):
        self.calls = 0

    def verify(self, base, candidate, invariants, intent_checks):
        self.calls += 1
        text = (candidate / "configs" / "core.cfg").read_text()
        broad = "permit ip 10.10.10.0" in text
        v = Verdict()
        for inv in invariants:
            bad = broad and inv.dst_ports == "22"
            v.checks.append(CheckResult(inv, "invariant", not bad, "akış-x" if bad else None))
        for c in intent_checks:
            v.checks.append(CheckResult(c, "intent", True))
        return v


def test_example_snapshot_loads():
    assert set(read_configs(ACME)) == {"core.cfg", "edge.cfg"}
    assert len(read_invariants(ACME)) == 3


def test_apply_edits_inserts_before_deny():
    out = apply_edits(read_configs(ACME), load(GOOD))
    lines = out["core.cfg"].splitlines()
    i = lines.index(" permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.30 eq 5432")
    assert lines[i + 1] == " deny ip any any"
    assert out["edge.cfg"] == read_configs(ACME)["edge.cfg"]


@pytest.mark.parametrize(
    "edit",
    [
        {"file": "yok.cfg", "old": "a", "new": "b"},
        {"file": "core.cfg", "old": "bu metin dosyada yok", "new": "b"},
        {"file": "core.cfg", "old": " no shutdown\n", "new": "b"},  # 3 kez geçiyor
        {"file": "core.cfg", "old": "", "new": "b"},
        {"file": "../policy.json", "old": "blocked", "new": "reachable"},
    ],
)
def test_apply_edits_rejects_bad_edits(edit):
    raw = json.loads(GOOD.read_text()) | {"edits": [edit]}
    with pytest.raises(ProposalError):
        apply_edits(read_configs(ACME), Proposal.from_dict(raw))


def test_proposal_requires_checks_and_edits():
    raw = json.loads(GOOD.read_text())
    with pytest.raises(ProposalError):
        Proposal.from_dict(raw | {"intent_checks": []})
    with pytest.raises(ProposalError):
        Proposal.from_dict(raw | {"edits": []})
    with pytest.raises(ProposalError):
        FlowCheck.from_dict({"name": "x", "start": "s", "dst": "d", "expect": "maybe"})


def test_loop_rejects_then_accepts():
    verifier = FakeVerifier()
    result = loop.run("db aç", ACME, ScriptedProposer([BAD, GOOD]), verifier)
    assert [r.verdict.accepted for r in result.rounds] == [False, True]
    assert result.accepted and verifier.calls == 2
    assert "DEĞİŞMEZ İHLALİ" in result.rounds[0].verdict.feedback()
    md = report.render(result)
    assert "KABUL EDİLDİ" in md and "+ permit tcp" in md and "**ihlal**" in md


def test_loop_gives_up_after_max_rounds():
    result = loop.run("db aç", ACME, ScriptedProposer([BAD, BAD]), FakeVerifier(), max_rounds=2)
    assert not result.accepted and len(result.rounds) == 2
    assert "REDDEDİLDİ" in report.render(result)


def test_unappliable_proposal_is_fed_back_without_calling_verifier(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text(
        json.dumps(
            json.loads(GOOD.read_text())
            | {"edits": [{"file": "core.cfg", "old": "yok", "new": "x"}]}
        )
    )
    verifier = FakeVerifier()
    result = loop.run("db aç", ACME, ScriptedProposer([broken, GOOD]), verifier)
    assert result.accepted and verifier.calls == 1
    assert result.rounds[0].verdict.error


def test_preexisting_invariant_violation_does_not_block():
    inv = read_invariants(ACME)[0]
    v = Verdict(checks=[CheckResult(inv, "invariant", False, "akış", preexisting=True)])
    assert v.accepted


class FakeClient:
    def __init__(self, inputs):
        self.inputs = list(inputs)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        n = len(self.requests)
        block = SimpleNamespace(type="tool_use", id=f"tu_{n}", input=self.inputs[n - 1])
        return SimpleNamespace(content=[block])


def test_claude_proposer_sends_configs_and_feeds_back_rejection():
    client = FakeClient([{"summary": "a"}, {"summary": "b"}])
    p = ClaudeProposer(
        "db aç", read_configs(ACME), read_invariants(ACME), model="m", client=client
    )
    assert p.propose(None) == {"summary": "a"}
    assert p.propose("DEĞİŞMEZ İHLALİ: ...") == {"summary": "b"}

    first, second = client.requests
    assert first["tool_choice"] == {"type": "tool", "name": "propose_change"}
    assert "hostname core" in first["messages"][0]["content"]
    assert "db aç" in first["messages"][0]["content"]
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    tool_result = second["messages"][2]["content"][0]
    assert tool_result["tool_use_id"] == "tu_1" and tool_result["is_error"]
    assert "DEĞİŞMEZ İHLALİ" in tool_result["content"]
