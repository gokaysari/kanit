"""Gerçek Claude API ve gerçek Batfish'e karşı uçtan uca test.

Ücretlidir; varsayılan `pytest` koşusunda seçilmez. Çalıştırmak için: make live-test
Anahtar ya da Batfish yoksa atlanmaz, kalır: atlanan test doğrulama sayılmaz.
"""

import os
from pathlib import Path

import pytest

from kanit import loop, report
from kanit.proposer import ClaudeProposer
from kanit.snapshot import read_configs, read_invariants
from kanit.verifier import BatfishVerifier

ACME = Path(__file__).parent.parent / "examples" / "acme"
INTENT = "Kullanıcı ağından veritabanı sunucusuna (10.20.20.30) tcp/5432 aç"

pytestmark = pytest.mark.claude


def test_real_claude_change_is_accepted_by_batfish():
    assert os.environ.get("ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY tanımlı değil"
    assert os.environ.get("BATFISH_HOST"), "BATFISH_HOST tanımlı değil"

    proposer = ClaudeProposer(INTENT, read_configs(ACME), read_invariants(ACME))
    result = loop.run(INTENT, ACME, proposer, BatfishVerifier(os.environ["BATFISH_HOST"]))
    print(report.render(result))

    assert result.error is None, result.error
    assert result.accepted
    final = result.final.verdict
    # Değişmezler ve modelin kendi niyet kontrolleri Batfish'te kanıtlanmış olmalı.
    assert all(c.passed for c in final.checks)
    assert any(c.kind == "intent" for c in final.checks)
    assert result.usage.calls >= 1 and result.usage.output_tokens > 0
