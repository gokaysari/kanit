"""Önceden var olan ihlal, gerçek Batfish'e karşı (hata D1).

Kural: değişmez değişiklikten önce de ihlal ediliyorsa, aday ihlal kümesini
GENİŞLETMEDİĞİ kanıtlanırsa kabulü engellemez. Eskiden mevcutta herhangi bir ihlal
olması yetiyordu; bu yüzden aşağıdaki geniş SSH değişmeziyle `01-fazla-genis.json`
(10.20.20.30:22'yi yeni açıyor) KABUL alıyordu.

Senaryo ağı: examples/acme kopyası; dar SSH değişmezi (yalnızca 10.20.20.30) yerine
mevcut ağın zaten ihlal ettiği geniş değişmez konur (mevcut ağ 10.20.20.20'ye SSH'ye
izin veriyor). Repodaki examples/acme değiştirilmez.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from kanit import cli, loop, report
from kanit.models import Proposal
from kanit.proposer import ScriptedProposer
from kanit.snapshot import POLICY_FILE, apply_edits, read_configs
from kanit.verifier import BatfishVerifier

ACME = Path(__file__).parent.parent / "examples" / "acme"
HOST = os.environ.get("BATFISH_HOST")
USERS = "@enter(core[GigabitEthernet0/1])"
BROAD_SSH = "Kullanıcılar hiçbir sunucuya SSH yapamaz"
BROAD_HTTPS = "Kullanıcılar tüm sunuculara HTTPS ile erişir"
LAST_RULE = " deny ip any any\n"
PREEXISTING_TEXT = (
    "önceden de ihlal ediliyordu; bu değişiklik ihlali genişletmiyor (kanıtlandı)"
)

pytestmark = [
    pytest.mark.batfish,
    pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil"),
]


def broad_snapshot(tmp_path: Path, extra: list[dict] | None = None) -> Path:
    """acme kopyası: dar SSH değişmezi yerine geniş (zaten ihlal edilen) SSH değişmezi."""
    dest = tmp_path / "base"
    shutil.copytree(ACME, dest)
    policy = json.loads((dest / POLICY_FILE).read_text())
    policy["invariants"] = [i for i in policy["invariants"] if i.get("dst_ports") != "22"]
    policy["invariants"].append(
        {"name": BROAD_SSH, "start": USERS, "src": "10.10.10.0/24", "dst": "10.20.20.0/24",
         "protocol": "TCP", "dst_ports": "22", "expect": "blocked"}
    )
    policy["invariants"] += extra or []
    (dest / POLICY_FILE).write_text(json.dumps(policy, ensure_ascii=False, indent=2))
    return dest


def proposal(tmp_path: Path, name: str, edits: list[tuple[str, str]], checks: list[dict]):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({
        "summary": name,
        "edits": [{"file": "core.cfg", "old": o, "new": n} for o, n in edits],
        "intent_checks": checks,
    }, ensure_ascii=False))
    return path


def run_once(snapshot: Path, scripted: Path):
    result = loop.run("test", snapshot, ScriptedProposer([scripted]), BatfishVerifier(HOST),
                      max_rounds=1)
    print(report.render(result))
    (r,) = result.rounds
    return result, {c.check.name: c for c in r.verdict.checks}


def ssh_check(dst: str, expect: str) -> dict:
    return {"name": f"{dst}:22 {expect}", "start": USERS, "src": "10.10.10.0/24",
            "dst": dst, "protocol": "TCP", "dst_ports": "22", "expect": expect}


# --- loop yolu ---------------------------------------------------------------------


def test_broad_rule_widening_preexisting_violation_is_rejected(tmp_path):
    """Karşı örnek: düzeltmeden önce bu öneri KABUL alıyordu."""
    scripted = ACME / "scripted" / "01-fazla-genis.json"
    result, checks = run_once(broad_snapshot(tmp_path), scripted)
    assert not result.accepted
    ssh = checks[BROAD_SSH]
    assert not ssh.passed and not ssh.preexisting
    assert ssh in result.final.verdict.failures
    # Karşı örnek adayda YENİ açılan akış olmalı, mevcutta da var olan ihlal değil.
    assert "->10.20.20.30:22 TCP" in ssh.counterexample, ssh.counterexample
    assert "DELIVERED_TO_SUBNET" in ssh.counterexample
    assert f"DEĞİŞMEZ İHLALİ: '{BROAD_SSH}'" in result.final.verdict.feedback()
    assert "10.20.20.30:22" in result.final.verdict.feedback()


def test_narrow_rule_keeps_preexisting_violation_and_is_accepted(tmp_path):
    result, checks = run_once(broad_snapshot(tmp_path), ACME / "scripted" / "02-dogru.json")
    assert result.accepted
    ssh = checks[BROAD_SSH]
    assert not ssh.passed and ssh.preexisting
    md = report.render(result)
    assert PREEXISTING_TEXT in md


def test_change_that_narrows_preexisting_violation_is_accepted(tmp_path):
    """10.20.20.20:22 izni kaldırılıyor; ihlal daralıyor (yönlendiricinin kendi adresi
    10.20.20.1:22 hâlâ ACCEPTED, yani değişmez hâlâ ihlalde) ama genişlemiyor."""
    allow_20 = " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.20 eq 22\n"
    p = proposal(tmp_path, "daralt", [(allow_20, "")], [ssh_check("10.20.20.20", "blocked")])
    result, checks = run_once(broad_snapshot(tmp_path), p)
    assert result.accepted
    ssh = checks[BROAD_SSH]
    assert not ssh.passed and ssh.preexisting
    assert "10.20.20.20:22" not in ssh.counterexample


def test_unrelated_change_keeping_violation_as_is_is_accepted(tmp_path):
    rule = " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.10 eq 80\n"
    check = {"name": "web 80", "start": USERS, "src": "10.10.10.0/24", "dst": "10.20.20.10",
             "protocol": "TCP", "dst_ports": "80", "expect": "reachable"}
    p = proposal(tmp_path, "ilgisiz", [(LAST_RULE, rule + LAST_RULE)], [check])
    result, checks = run_once(broad_snapshot(tmp_path), p)
    assert result.accepted
    assert checks[BROAD_SSH].preexisting


def test_widening_hidden_behind_simultaneous_narrowing_is_rejected(tmp_path):
    """Aynı başlangıç noktasında hem daraltıp (.20) hem genişleten (.30) değişiklik.

    Batfish'in differentialReachability'si 'artan' ve 'azalan' kümelerden ayrı örnek
    döndürmeseydi genişleme daralma örneğinin arkasında kaybolabilirdi; bu test o
    davranışı sabitler.
    """
    allow_20 = " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.20 eq 22\n"
    allow_30 = " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.30 eq 22\n"
    p = proposal(tmp_path, "takas", [(allow_20, allow_30)], [ssh_check("10.20.20.20", "blocked")])
    result, checks = run_once(broad_snapshot(tmp_path), p)
    assert not result.accepted
    ssh = checks[BROAD_SSH]
    assert not ssh.preexisting
    assert "->10.20.20.30:22 TCP" in ssh.counterexample, ssh.counterexample


def https_all() -> dict:
    # Mevcut ağda yalnızca 10.20.20.10:443 ulaşıyor; değişmez baştan ihlalde.
    return {"name": BROAD_HTTPS, "start": USERS, "src": "10.10.10.0/24",
            "dst": "10.20.20.0/24", "protocol": "TCP", "dst_ports": "443",
            "expect": "reachable"}


def test_reachable_invariant_widening_is_rejected(tmp_path):
    """'reachable' yönü: önceden kısmen ihlal edilen erişim değişmezinde, ulaşan akışı
    kesen değişiklik ihlali genişletir."""
    allow_443 = " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.10 eq 443\n"
    p = proposal(tmp_path, "https-kes", [(allow_443, "")], [ssh_check("10.20.20.30", "blocked")])
    result, checks = run_once(broad_snapshot(tmp_path, [https_all()]), p)
    assert not result.accepted
    https = checks[BROAD_HTTPS]
    assert not https.preexisting
    assert "->10.20.20.10:443 TCP" in https.counterexample, https.counterexample


def test_reachable_invariant_unchanged_violation_is_accepted(tmp_path):
    p = proposal(tmp_path, "dogru", [(LAST_RULE, " permit tcp 10.10.10.0 0.0.0.255 host "
                                      "10.20.20.30 eq 5432\n" + LAST_RULE)],
                 [{"name": "db", "start": USERS, "src": "10.10.10.0/24", "dst": "10.20.20.30",
                   "protocol": "TCP", "dst_ports": "5432", "expect": "reachable"}])
    result, checks = run_once(broad_snapshot(tmp_path, [https_all()]), p)
    assert result.accepted
    assert checks[BROAD_HTTPS].preexisting and checks[BROAD_SSH].preexisting


# --- kanit check (PR botu) yolu ------------------------------------------------------


def pr_from(base: Path, tmp_path: Path, scripted: str) -> Path:
    dest = tmp_path / "pr"
    shutil.copytree(base, dest)
    raw = json.loads((ACME / "scripted" / scripted).read_text())
    for name, text in apply_edits(read_configs(dest), Proposal.from_dict(raw)).items():
        (dest / "configs" / name).write_text(text)
    return dest


def check(base: Path, cand: Path, out: Path) -> tuple[int, str]:
    rc = cli.main(["check", "--base", str(base), "--candidate", str(cand), "--out", str(out),
                   "--batfish-host", HOST])
    md = out.read_text()
    print(md)
    return rc, md


def test_pr_check_rejects_broad_rule_with_preexisting_violation(tmp_path):
    base = broad_snapshot(tmp_path)
    rc, md = check(base, pr_from(base, tmp_path, "01-fazla-genis.json"), tmp_path / "r.md")
    assert rc == 1
    assert "Kanıt etki raporu: REDDEDİLDİ" in md
    row = next(line for line in md.splitlines() if BROAD_SSH in line)
    assert "**ihlal**" in row and "10.20.20.30:22" in row


def test_pr_check_accepts_narrow_rule_with_preexisting_violation(tmp_path):
    base = broad_snapshot(tmp_path)
    rc, md = check(base, pr_from(base, tmp_path, "02-dogru.json"), tmp_path / "r.md")
    assert rc == 0
    assert "Kanıt etki raporu: KABUL EDİLDİ" in md
    row = next(line for line in md.splitlines() if BROAD_SSH in line)
    assert PREEXISTING_TEXT in row
