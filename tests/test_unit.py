import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from kanit import cli, loop, report
from kanit.models import CheckResult, FlowCheck, Proposal, ProposalError, Usage, Verdict
from kanit.proposer import TOOL, ClaudeProposer, ProposerError, ScriptedProposer
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


def tool_use(n, data):
    return SimpleNamespace(type="tool_use", id=f"tu_{n}", name="propose_change", input=data)


def response(*blocks, stop_reason="tool_use", input_tokens=1000, output_tokens=200):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, usage=usage)


class FakeClient:
    """Sırayla verilen yanıtları döndürür; öğe bir istisnaysa onu fırlatır.

    Öğe bir sözlükse propose_change çağrısı içeren yanıta çevrilir.
    """

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        n = len(self.requests)
        reply = self.replies[n - 1]
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, dict):
            return response(tool_use(n, reply))
        return reply


def proposer(client):
    return ClaudeProposer(
        "db aç", read_configs(ACME), read_invariants(ACME), model="m", client=client
    )


def test_claude_proposer_sends_configs_and_feeds_back_rejection():
    client = FakeClient([{"summary": "a"}, {"summary": "b"}])
    p = proposer(client)
    assert p.propose(None) == {"summary": "a"}
    assert p.propose("DEĞİŞMEZ İHLALİ: ...") == {"summary": "b"}

    first, second = client.requests
    # Bu modeller zorunlu tool_choice'u 400 ile reddeder; auto + strict kullanılmalı.
    assert first["tool_choice"]["type"] == "auto"
    assert "hostname core" in first["messages"][0]["content"]
    assert "db aç" in first["messages"][0]["content"]
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    tool_result = second["messages"][2]["content"][0]
    assert tool_result["tool_use_id"] == "tu_1" and tool_result["is_error"]
    assert "DEĞİŞMEZ İHLALİ" in tool_result["content"]
    assert p.usage == Usage(calls=2, input_tokens=2000, output_tokens=400)


def test_tool_schema_is_strict():
    assert TOOL["strict"] is True

    def objects(schema):
        if schema.get("type") == "object":
            yield schema
            for sub in schema["properties"].values():
                yield from objects(sub)
        elif schema.get("type") == "array":
            yield from objects(schema["items"])

    found = list(objects(TOOL["input_schema"]))
    assert len(found) == 3
    assert all(o["additionalProperties"] is False for o in found)


def test_claude_proposer_nudges_once_when_tool_not_called():
    text = SimpleNamespace(type="text", text="Önce şunu sorayım...")
    client = FakeClient([response(text, stop_reason="end_turn"), {"summary": "a"}])
    p = proposer(client)
    assert p.propose(None) == {"summary": "a"}
    roles = [m["role"] for m in client.requests[1]["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert "propose_change" in client.requests[1]["messages"][2]["content"]
    assert p.usage.calls == 2


def test_claude_proposer_gives_up_when_tool_never_called():
    text = SimpleNamespace(type="text", text="Bunu yapamam.")
    client = FakeClient([response(text, stop_reason="end_turn")] * 2)
    with pytest.raises(ProposerError, match="çağırmadı.*Bunu yapamam"):
        proposer(client).propose(None)


def test_claude_proposer_reports_refusal_and_truncation():
    refusal = response(stop_reason="refusal")
    refusal.stop_details = SimpleNamespace(category="cyber")
    with pytest.raises(ProposerError, match="reddetti.*cyber"):
        proposer(FakeClient([refusal])).propose(None)
    cut = response(tool_use(1, {"summary": "yar"}), stop_reason="max_tokens")
    with pytest.raises(ProposerError, match="token sınırında kesildi"):
        proposer(FakeClient([cut])).propose(None)


def _status_error(cls, code, headers=None):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(code, headers=headers or {}, request=request)
    return cls("hata", response=resp, body=None)


@pytest.mark.parametrize(
    "exc, message",
    [
        (_status_error(anthropic.AuthenticationError, 401), "anahtarı geçersiz"),
        (_status_error(anthropic.PermissionDeniedError, 403), "erişim izni yok"),
        (_status_error(anthropic.NotFoundError, 404), "modeli bulunamadı"),
        (
            _status_error(anthropic.RateLimitError, 429, {"retry-after": "30"}),
            "oran sınırına.*30 saniye",
        ),
        (_status_error(anthropic.InternalServerError, 529), "geçici olarak"),
        (_status_error(anthropic.BadRequestError, 400), r"reddetti \(400\)"),
        (
            anthropic.APIConnectionError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            "bağlanılamadı",
        ),
    ],
)
def test_api_errors_become_readable(exc, message):
    with pytest.raises(ProposerError, match=message):
        proposer(FakeClient([exc])).propose(None)


def test_loop_stops_cleanly_on_proposer_error():
    good = json.loads(GOOD.read_text())
    bad = json.loads(BAD.read_text())
    client = FakeClient([bad, _status_error(anthropic.RateLimitError, 429), good])
    result = loop.run("db aç", ACME, proposer(client), FakeVerifier())
    assert not result.accepted and len(result.rounds) == 1
    assert "oran sınırı" in result.error
    assert result.usage == Usage(calls=1, input_tokens=1000, output_tokens=200)
    md = report.render(result)
    assert "Döngü durdu" in md and "REDDEDİLDİ" in md


def test_usage_is_reported_per_round_and_in_total():
    client = FakeClient([json.loads(BAD.read_text()), json.loads(GOOD.read_text())])
    result = loop.run("db aç", ACME, proposer(client), FakeVerifier())
    assert result.accepted
    assert [r.usage.calls for r in result.rounds] == [1, 1]
    assert result.usage == Usage(calls=2, input_tokens=2000, output_tokens=400)
    md = report.render(result)
    assert "**Model:** m" in md
    assert "2 çağrı, 2.000 giriş + 400 çıkış token" in md
    assert md.count("Model kullanımı: 1 çağrı") == 2


def _good():
    return json.loads(GOOD.read_text())


@pytest.mark.parametrize(
    "bad_input, message",
    [
        ({"summary": "x", "edits": []}, "eksik alan: intent_checks"),
        (_good() | {"edits": "core.cfg"}, "'edits' bir liste olmalı"),
        (_good() | {"edits": [{"file": "core.cfg", "old": 5, "new": "x"}]}, "metin olmalı"),
        (_good() | {"intent_checks": ["tcp/5432 açık"]}, "nesne olmalı"),
        (_good() | {"intent_checks": [{"name": "x"}]}, "eksik alan"),
        (_good() | {"edits": []}, "hiç değişiklik içermiyor"),
    ],
)
def test_schema_invalid_tool_input_is_fed_back_and_loop_continues(bad_input, message):
    """Claude'un şemaya uymayan girdisi aynı konuşmada hata sonucu olarak geri verilir."""
    client = FakeClient([bad_input, _good()])
    verifier = FakeVerifier()
    result = loop.run("db aç", ACME, proposer(client), verifier)

    assert [r.verdict.accepted for r in result.rounds] == [False, True]
    assert result.accepted and result.error is None
    assert result.rounds[0].proposal is None and message in result.rounds[0].verdict.error
    assert verifier.calls == 1  # bozuk öneri Batfish'e gitmez

    second = client.requests[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"][0].input == bad_input  # aynı konuşma, geçmiş korunur
    tool_result = second[2]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "tu_1"
    assert tool_result["is_error"] is True
    assert "Öneri uygulanamadı:" in tool_result["content"]
    assert message in tool_result["content"]
    assert [r.usage.calls for r in result.rounds] == [1, 1]


def test_cli_stops_with_readable_error_and_writes_report(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sahte")
    client = FakeClient([_status_error(anthropic.AuthenticationError, 401)])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    out = tmp_path / "r.md"
    code = cli.main(["plan", "db aç", "--snapshot", str(ACME), "--out", str(out)])
    assert code == 2
    assert "anahtarı geçersiz" in capsys.readouterr().err
    assert "Döngü durdu" in out.read_text()


def test_cli_prints_usage_per_round_and_total(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sahte")
    client = FakeClient([json.loads(BAD.read_text()), _good()])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: FakeVerifier())
    out = tmp_path / "r.md"
    code = cli.main(
        ["plan", "db aç", "--snapshot", str(ACME), "--out", str(out), "--model", "m"]
    )
    assert code == 0
    stdout = capsys.readouterr().out
    assert "Tur 1: RET (1 çağrı, 1.000 giriş + 200 çıkış token)" in stdout
    assert "Tur 2: KABUL (1 çağrı, 1.000 giriş + 200 çıkış token)" in stdout
    assert "Toplam model kullanımı (m): 2 çağrı, 2.000 giriş + 400 çıkış token" in stdout


def test_cli_without_api_key_exits_with_message(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    code = cli.main(["plan", "db aç", "--snapshot", str(ACME), "--out", str(tmp_path / "r.md")])
    assert code == 2
    assert "ANTHROPIC_API_KEY tanımlı değil" in capsys.readouterr().err


# --- önceden var olan ihlalin sınıflandırılması (BatfishVerifier._widening) ----------
# Kanıt değildir (gerçek Batfish testi: test_preexisting_batfish.py); yalnızca örnek
# satırların sınıflandırılmasında kapalı yönde karar verildiğini sabitler.


def fake_bf(rows):
    import pandas as pd

    def traces(*disps):
        return [SimpleNamespace(disposition=d) for d in disps]

    frame = pd.DataFrame(
        [{"Flow": f, "Reference_Traces": traces(*b), "Snapshot_Traces": traces(*a)}
         for f, b, a in rows],
        columns=["Flow", "Reference_Traces", "Snapshot_Traces"],
    )
    answer = SimpleNamespace(answer=lambda **kw: SimpleNamespace(frame=lambda: frame))
    return SimpleNamespace(q=SimpleNamespace(differentialReachability=lambda **kw: answer))


SSH_ALL = FlowCheck("ssh", "@enter(core[GigabitEthernet0/1])", "10.20.20.0/24", "blocked",
                    "10.10.10.0/24", "TCP", "22")


@pytest.mark.parametrize(
    "rows, widened",
    [
        ([], False),  # fark yok: kanıt
        ([("f20", ["DELIVERED_TO_SUBNET"], ["DENIED_OUT"])], False),  # yalnızca daralma
        ([("f30", ["DENIED_OUT"], ["DELIVERED_TO_SUBNET"])], True),  # genişleme
        ([("f20", ["DELIVERED_TO_SUBNET"], ["DENIED_OUT"]),
          ("f30", ["DENIED_OUT"], ["DELIVERED_TO_SUBNET"])], True),  # daralma arkasında
        ([("f", ["DENIED_OUT"], ["DENIED_OUT", "ACCEPTED"])], True),  # çok yollu, yeni yol
        ([("f", ["DENIED_OUT"], ["YENI_DURUM"])], True),  # bilinmeyen disposition
        ([("f", ["DENIED_OUT"], [])], True),  # boş iz
        ([("f", ["ACCEPTED"], ["DELIVERED_TO_SUBNET"])], True),  # iki tarafta da ihlal
    ],
)
def test_widening_classification_fails_closed(rows, widened):
    from kanit.verifier import BatfishVerifier

    result = BatfishVerifier._widening(fake_bf(rows), SSH_ALL)
    assert (result is not None) == widened, result


def test_reachable_invariant_widening_is_flow_that_stops_reaching():
    from kanit.verifier import BatfishVerifier

    https = FlowCheck("https", "@enter(core[GigabitEthernet0/1])", "10.20.20.0/24",
                      "reachable", "10.10.10.0/24", "TCP", "443")
    lost = [("f10", ["DELIVERED_TO_SUBNET"], ["DENIED_OUT"])]
    gained = [("f30", ["DENIED_OUT"], ["DELIVERED_TO_SUBNET"])]
    assert "f10" in BatfishVerifier._widening(fake_bf(lost), https)
    assert BatfishVerifier._widening(fake_bf(gained), https) is None
