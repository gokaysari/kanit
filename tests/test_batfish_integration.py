"""Gerçek Batfish'e karşı uçtan uca test. BATFISH_HOST tanımlıysa çalışır."""

import os
from pathlib import Path

import pytest

from kanit import loop, report
from kanit.proposer import ScriptedProposer
from kanit.verifier import BatfishVerifier

ACME = Path(__file__).parent.parent / "examples" / "acme"
HOST = os.environ.get("BATFISH_HOST")

pytestmark = [
    pytest.mark.batfish,
    pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil"),
]


def test_broad_change_is_rejected_and_narrow_change_is_accepted():
    proposer = ScriptedProposer(
        [ACME / "scripted" / "01-fazla-genis.json", ACME / "scripted" / "02-dogru.json"]
    )
    result = loop.run("Kullanıcılara veritabanı 5432 aç", ACME, proposer, BatfishVerifier(HOST))
    print(report.render(result))

    first, second = result.rounds
    # 1. tur: 'permit ip' SSH'ı da açar; değişmez ihlali karşı örnekle yakalanmalı.
    assert not first.verdict.accepted
    failed = [c.check.name for c in first.verdict.failures]
    assert failed == ["Kullanıcılar veritabanı sunucusuna SSH yapamaz"]
    assert first.verdict.failures[0].counterexample

    # 2. tur: yalnızca tcp/5432; tüm değişmezler ve niyet kanıtlanmalı.
    assert second.verdict.accepted
    assert all(c.passed for c in second.verdict.checks)
    assert len(second.verdict.checks) == 4
    assert second.verdict.changed_flows, "5432 artık ulaşmalı; fark boş olamaz"
    assert not second.verdict.new_parse_issues


def test_unchanged_baseline_satisfies_invariants():
    """Örnek ağın kendisi değişmezleri sağlamalı; yoksa demo anlamsız olur."""
    from kanit.snapshot import read_invariants

    verdict = BatfishVerifier(HOST).verify(ACME, ACME, read_invariants(ACME), [])
    assert all(c.passed for c in verdict.checks), [
        (c.check.name, c.counterexample) for c in verdict.checks if not c.passed
    ]
    assert verdict.changed_flows == []
