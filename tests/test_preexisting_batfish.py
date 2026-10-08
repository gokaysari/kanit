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


# --- başlangıç konumu kümeleri farklı olduğunda ---------------------------------------
# differentialReachability yalnızca iki snapshot'ta da var ve etkin olan konumları
# tarar. Adayda yeni, yeniden etkinleşen ya da kaybolan konumlar ayrıca sınanmalı.

A20 = " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.20 eq 22\n"
OPEN_30_ANY = (A20, A20 + " permit tcp any host 10.20.20.30 eq 22\n")
NO_SSH_DB = [
    (" ip access-group SERVERS-OUT out\n",
     " ip access-group SERVERS-OUT out\n ip access-group NO-SSH-DB in\n"),
    (" ip address 10.0.0.2 255.255.255.252\n",
     " ip address 10.0.0.2 255.255.255.252\n ip access-group NO-SSH-DB in\n"),
    (" ip address 10.10.10.1 255.255.255.0\n",
     " ip address 10.10.10.1 255.255.255.0\n ip access-group NO-SSH-DB in\n"),
    ("ip route 0.0.0.0",
     "ip access-list extended NO-SSH-DB\n deny tcp any host 10.20.20.30 eq 22\n"
     " permit ip any any\n!\nip route 0.0.0.0"),
]
LAB_IF = "interface GigabitEthernet0/3\n ip address 10.30.30.1 255.255.255.0\n"
BEFORE_GI2 = "interface GigabitEthernet0/2\n"
BRANCH = ("!\nhostname branch\n!\ninterface GigabitEthernet0/0\n"
          " ip address 10.20.40.1 255.255.255.0\n no shutdown\n!\nend\n")


def inv(name, start, dst, expect, port, src=None):
    return {"name": name, "start": start, "src": src, "dst": dst, "protocol": "TCP",
            "dst_ports": port, "expect": expect}


def pair(tmp_path, invariants, base_edits=(), cand_edits=(), cand_files=None):
    """acme kopyasından mevcut ve aday snapshot; policy yalnızca verilen değişmezler."""
    def edit(text, edits):
        for old, new in edits:
            assert text.count(old) == 1, old
            text = text.replace(old, new)
        return text

    base, cand = tmp_path / "base", tmp_path / "cand"
    shutil.copytree(ACME, base)
    core = edit((base / "configs" / "core.cfg").read_text(), base_edits)
    (base / "configs" / "core.cfg").write_text(core)
    policy = json.dumps({"invariants": invariants}, ensure_ascii=False, indent=2)
    (base / POLICY_FILE).write_text(policy)
    shutil.copytree(base, cand)
    (cand / "configs" / "core.cfg").write_text(edit(core, cand_edits))
    for name, text in (cand_files or {}).items():
        (cand / "configs" / name).write_text(text)
    return base, cand


def verify(base, cand):
    from kanit.snapshot import read_invariants

    verdict = BatfishVerifier(HOST).verify(base, cand, read_invariants(base), [])
    for c in verdict.checks:
        print(c.check.name, c.passed, c.preexisting, c.counterexample)
    return verdict, {c.check.name: c for c in verdict.checks}


SSH_FROM_CORE = inv("core'a giren hiçbir akış sunuculara SSH yapamaz", "@enter(core)",
                    "10.20.20.0/24", "blocked", "22")


def test_new_interface_opening_ssh_is_rejected(tmp_path):
    """Denetçi n3: mevcutta her core arayüzünde NO-SSH-DB var; aday ACL'siz yeni Gi0/3
    ekleyip .30:22'yi açıyor. Eski kodda differentialReachability 0 satır döndürüyor ve
    öneri KABUL alıyordu."""
    new_if = (BEFORE_GI2, LAB_IF + " no shutdown\n!\n" + BEFORE_GI2)
    base, cand = pair(tmp_path, [SSH_FROM_CORE], NO_SSH_DB, [new_if, OPEN_30_ANY])
    verdict, checks = verify(base, cand)
    assert not verdict.accepted
    c = checks[SSH_FROM_CORE["name"]]
    assert not c.preexisting
    assert "interface=GigabitEthernet0/3" in c.counterexample, c.counterexample
    assert "yeni başlangıç konumunda ihlal" in c.counterexample

    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 1 and "**ihlal**" in md and "GigabitEthernet0/3" in md


def test_same_opening_without_new_interface_is_accepted(tmp_path):
    """n3 kontrolü: aynı açılış, yeni arayüz olmadan; NO-SSH-DB her girişte .30:22'yi
    kestiği için ihlal genişlemiyor."""
    base, cand = pair(tmp_path, [SSH_FROM_CORE], NO_SSH_DB, [OPEN_30_ANY])
    verdict, checks = verify(base, cand)
    assert verdict.accepted
    assert checks[SSH_FROM_CORE["name"]].preexisting


def test_reactivated_interface_opening_ssh_is_rejected(tmp_path):
    """Konum iki snapshot'ta da var ama mevcutta kapalı (shutdown): fark sorgusu onu
    da taramaz."""
    lab = (BEFORE_GI2, LAB_IF + " shutdown\n!\n" + BEFORE_GI2)
    up = (LAB_IF + " shutdown\n", LAB_IF + " no shutdown\n")
    base, cand = pair(tmp_path, [SSH_FROM_CORE], NO_SSH_DB + [lab], [up, OPEN_30_ANY])
    verdict, checks = verify(base, cand)
    assert not verdict.accepted
    assert "interface=GigabitEthernet0/3" in checks[SSH_FROM_CORE["name"]].counterexample


@pytest.mark.parametrize("start", ["/.*/", "@enter(/.*/[/.*/])"])
def test_new_device_is_covered_for_multi_location_start(tmp_path, start):
    """Denetçi n1: aday ACL'siz yeni bir cihaz (branch, 10.20.40.1/24) ekliyor. Eski kodda
    fark sorgusu yalnızca daralma örnekleri döndürüyor ve öneri KABUL alıyordu."""
    wide = inv("Kullanıcılardan 10.20/16'ya SSH yok", start, "10.20.0.0/16", "blocked", "22",
               src="10.10.10.0/24")
    base, cand = pair(tmp_path, [wide], cand_files={"branch.cfg": BRANCH})
    verdict, checks = verify(base, cand)
    assert not verdict.accepted
    c = checks[wide["name"]]
    assert not c.preexisting
    assert "start=branch" in c.counterexample, c.counterexample

    if start == "/.*/":
        rc, md = check(base, cand, tmp_path / "r.md")
        assert rc == 1 and "start=branch" in md


def test_changed_source_space_on_common_location_is_covered(tmp_path):
    """Ortak konumun arayüz adresi değişiyor (kaynak uzayı değişiyor) ve yeni ağ .30:22'ye
    açılıyor. Konum iki tarafta da etkin olduğu için fark sorgusuna kalıyor. Değişmez
    src'siz ve blocked olduğu için her kaynakla (0.0.0.0/0) sınanır; bu test genişlemenin
    yeni adres bloğundan gelen akışla bulunduğunu sabitler (örnek kaynak adresini Batfish
    seçer, yalnızca blok sınanır)."""
    ssh_users = inv("Kullanıcı arayüzünden sunuculara SSH yok", USERS, "10.20.20.0/24",
                    "blocked", "22")
    readdr = (" ip address 10.10.10.1 255.255.255.0\n", " ip address 10.10.11.1 255.255.255.0\n")
    open_new = (LAST_RULE, " permit tcp 10.10.11.0 0.0.0.255 host 10.20.20.30 eq 22\n"
                + LAST_RULE)
    base, cand = pair(tmp_path, [ssh_users], cand_edits=[readdr, open_new])
    verdict, checks = verify(base, cand)
    assert not verdict.accepted
    c = checks[ssh_users["name"]]
    assert not c.preexisting
    assert "[10.10.11." in c.counterexample and "->10.20.20.30:22" in c.counterexample
    assert "(yeni ihlal)" in c.counterexample


def test_reachable_invariant_losing_a_start_location_is_rejected(tmp_path):
    """'reachable' değişmezinin bir başlangıç konumu adayda kapanıyor. Adaydaki
    reachability yalnızca kalan konumlara bakar ve kanıtlar; kayıp ayrıca ihlaldir."""
    start = "@enter(core[GigabitEthernet0/1]), @enter(core[GigabitEthernet0/3])"
    https = inv("Kullanıcılar ve LAB web sunucusuna HTTPS ile erişir", start, "10.20.20.10",
                "reachable", "443")
    lab = (BEFORE_GI2, LAB_IF + " no shutdown\n!\n" + BEFORE_GI2)
    allow_lab = (LAST_RULE, " permit tcp 10.30.30.0 0.0.0.255 host 10.20.20.10 eq 443\n"
                 + LAST_RULE)
    down = (LAB_IF + " no shutdown\n", LAB_IF + " shutdown\n")
    base, cand = pair(tmp_path, [https], [lab, allow_lab], [down])
    # Mevcut ağ değişmezi sağlıyor; yoksa test anlamsız olur.
    unchanged, _ = verify(base, base)
    assert unchanged.accepted
    verdict, checks = verify(base, cand)
    assert not verdict.accepted
    c = checks[https["name"]]
    assert not c.passed and "GigabitEthernet0/3" in c.counterexample
    assert "erişim kayboldu" in c.counterexample
