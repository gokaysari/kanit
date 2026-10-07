"""`kanit check` gerçek Batfish'e karşı: PR botunun verdiği kabul ve ret kararları.

Adaylar, deneme PR'ında yapılacak değişikliğin aynısıdır: kayıtlı önerilerin
(01 fazla geniş, 02 doğru) düzenlemeleri examples/acme kopyasına uygulanır.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from kanit import cli
from kanit.models import Proposal
from kanit.snapshot import POLICY_FILE, apply_edits, read_configs

ACME = Path(__file__).parent.parent / "examples" / "acme"
HOST = os.environ.get("BATFISH_HOST")

pytestmark = [
    pytest.mark.batfish,
    pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil"),
]


def pr_snapshot(tmp_path: Path, scripted: str) -> Path:
    dest = tmp_path / "pr"
    shutil.copytree(ACME, dest)
    raw = json.loads((ACME / "scripted" / scripted).read_text())
    for name, text in apply_edits(read_configs(dest), Proposal.from_dict(raw)).items():
        (dest / "configs" / name).write_text(text)
    return dest


def check(base: Path, cand: Path, out: Path) -> tuple[int, str]:
    rc = cli.main(
        ["check", "--base", str(base), "--candidate", str(cand), "--out", str(out),
         "--batfish-host", HOST]
    )
    return rc, out.read_text()


def test_pr_with_narrow_rule_is_accepted(tmp_path):
    rc, md = check(ACME, pr_snapshot(tmp_path, "02-dogru.json"), tmp_path / "r.md")
    print(md)
    assert rc == 0
    assert "Kanıt etki raporu: KABUL EDİLDİ" in md
    assert "3 değişmez, 3 kanıtlandı, 0 ihlal" in md
    assert "+ permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.30 eq 5432" in md
    # 5432 artık ulaşıyor; fark boş olamaz.
    assert "DENIED_OUT -> DELIVERED_TO_SUBNET" in md


def test_pr_with_broad_rule_is_rejected_with_counterexample(tmp_path):
    rc, md = check(ACME, pr_snapshot(tmp_path, "01-fazla-genis.json"), tmp_path / "r.md")
    print(md)
    assert rc == 1
    assert "Kanıt etki raporu: REDDEDİLDİ" in md
    row = next(line for line in md.splitlines() if "SSH yapamaz" in line)
    assert "**ihlal**" in row and "10.20.20.30:22" in row


def test_pr_cannot_pass_by_deleting_the_invariant(tmp_path):
    """Geniş kural + SSH değişmezini silen PR: hedef daldaki değişmez yine uygulanır."""
    cand = pr_snapshot(tmp_path, "01-fazla-genis.json")
    policy = json.loads((cand / POLICY_FILE).read_text())
    policy["invariants"] = [i for i in policy["invariants"] if i.get("dst_ports") != "22"]
    (cand / POLICY_FILE).write_text(json.dumps(policy, ensure_ascii=False, indent=2))

    rc, md = check(ACME, cand, tmp_path / "r.md")
    assert rc == 1
    assert "**ihlal**" in md and "Ret sebebi" in md


def test_pr_that_only_drops_an_invariant_is_rejected(tmp_path):
    """İki adımlı kaçışın ilk adımı: yalnızca policy.json'dan SSH değişmezini silen PR."""
    cand = tmp_path / "pr"
    shutil.copytree(ACME, cand)
    policy = json.loads((cand / POLICY_FILE).read_text())
    policy["invariants"] = [i for i in policy["invariants"] if i.get("dst_ports") != "22"]
    (cand / POLICY_FILE).write_text(json.dumps(policy, ensure_ascii=False, indent=2))

    rc, md = check(ACME, cand, tmp_path / "r.md")
    print(md)
    assert rc == 1
    assert "Kanıt etki raporu: REDDEDİLDİ" in md and "DEĞİŞMEDİ" not in md
    assert "'Kullanıcılar veritabanı sunucusuna SSH yapamaz' silindi" in md


def test_pr_that_only_weakens_an_invariant_is_rejected(tmp_path):
    cand = tmp_path / "pr"
    shutil.copytree(ACME, cand)
    policy = json.loads((cand / POLICY_FILE).read_text())
    ssh = next(i for i in policy["invariants"] if i.get("dst_ports") == "22")
    ssh["expect"] = "reachable"
    (cand / POLICY_FILE).write_text(json.dumps(policy, ensure_ascii=False, indent=2))

    rc, md = check(ACME, cand, tmp_path / "r.md")
    assert rc == 1
    assert "değiştirildi (expect: blocked -> reachable)" in md
