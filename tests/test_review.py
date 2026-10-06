"""`kanit check` (model olmadan yalnızca doğrulama) için Batfish'siz birim testleri."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kanit import cli, review
from kanit.models import CheckResult, FlowCheck, Proposal, Verdict
from kanit.snapshot import POLICY_FILE, apply_edits, read_configs

ACME = Path(__file__).parent.parent / "examples" / "acme"
SCRIPTED = ACME / "scripted"


def make_snapshot(tmp_path: Path, name: str, scripted: str | None = None) -> Path:
    """examples/acme kopyası; scripted verilirse o önerinin düzenlemeleri uygulanmış."""
    dest = tmp_path / name
    shutil.copytree(ACME, dest)
    if scripted:
        proposal = Proposal.from_dict(json.loads((SCRIPTED / scripted).read_text()))
        for fname, text in apply_edits(read_configs(dest), proposal).items():
            (dest / "configs" / fname).write_text(text)
    return dest


class RecordingVerifier:
    """'permit ip 10.10.10.0' içeren adayı SSH değişmezini ihlal ediyor sayar."""

    def __init__(self, fail_with: Exception | None = None):
        self.calls: list[tuple] = []
        self.fail_with = fail_with

    def verify(self, base, candidate, invariants, intent_checks):
        layout = sorted(p.name for p in candidate.iterdir())
        self.calls.append((layout, candidate, list(invariants), list(intent_checks)))
        if self.fail_with:
            raise self.fail_with
        text = (candidate / "configs" / "core.cfg").read_text()
        broad = "permit ip 10.10.10.0" in text
        v = Verdict()
        for inv in invariants:
            bad = broad and inv.dst_ports == "22"
            v.checks.append(CheckResult(inv, "invariant", not bad, "akış|`x`" if bad else None))
        return v


def test_narrow_change_is_accepted(tmp_path):
    verifier = RecordingVerifier()
    r = review.run_check(ACME, make_snapshot(tmp_path, "pr", "02-dogru.json"), verifier)
    assert r.accepted and r.exit_code == 0
    (layout, _, invariants, intent), = verifier.calls
    assert len(invariants) == 3 and intent == []
    # Doğrulanan dizinde yalnızca configs/ var: raporlanan fark ile doğrulanan aynı.
    assert layout == ["configs"]
    md = review.render(r)
    assert "KABUL EDİLDİ" in md and "+ permit tcp 10.10.10.0" in md
    assert "3 değişmez, 3 kanıtlandı, 0 ihlal" in md


def test_broad_change_is_rejected_with_counterexample(tmp_path):
    r = review.run_check(ACME, make_snapshot(tmp_path, "pr", "01-fazla-genis.json"), RecordingVerifier())
    assert not r.accepted and r.exit_code == 1
    md = review.render(r)
    assert "REDDEDİLDİ" in md and "**ihlal**" in md
    # Karşı örnekteki '|' ve ters tırnak tabloyu bozmamalı.
    row = next(line for line in md.splitlines() if "SSH yapamaz" in line)
    assert row.count(" | ") == 2 and "`` akış¦`x` ``" in row


def test_no_change_skips_batfish(tmp_path):
    verifier = RecordingVerifier()
    r = review.run_check(ACME, make_snapshot(tmp_path, "pr"), verifier)
    assert r.accepted and r.exit_code == 0 and r.verdict is None
    assert verifier.calls == []
    assert "YAPILANDIRMA DEĞİŞMEDİ" in review.render(r)


def test_dropping_an_invariant_in_the_pr_does_not_weaken_the_check(tmp_path):
    """PR hem geniş kural ekleyip hem de SSH değişmezini silerse yine reddedilir."""
    cand = make_snapshot(tmp_path, "pr", "01-fazla-genis.json")
    policy = json.loads((cand / POLICY_FILE).read_text())
    policy["invariants"] = [i for i in policy["invariants"] if i.get("dst_ports") != "22"]
    (cand / POLICY_FILE).write_text(json.dumps(policy))

    r = review.run_check(ACME, cand, RecordingVerifier())
    assert not r.accepted and r.exit_code == 1
    assert [c.name for c in r.dropped_invariants] == ["Kullanıcılar veritabanı sunucusuna SSH yapamaz"]
    md = review.render(r)
    assert "Ret sebebi" in md and "SSH yapamaz' silindi" in md


def test_invariant_added_in_pr_is_also_checked(tmp_path):
    cand = make_snapshot(tmp_path, "pr")
    policy = json.loads((cand / POLICY_FILE).read_text())
    extra = {
        "name": "Kullanıcılar veritabanına 5432 ile erişir",
        "start": "@enter(core[GigabitEthernet0/1])",
        "src": "10.10.10.0/24",
        "dst": "10.20.20.30",
        "protocol": "TCP",
        "dst_ports": "5432",
        "expect": "reachable",
    }
    policy["invariants"].append(extra)
    (cand / POLICY_FILE).write_text(json.dumps(policy))

    verifier = RecordingVerifier()
    r = review.run_check(ACME, cand, verifier)
    (_, _, invariants, _), = verifier.calls
    assert len(invariants) == 4 and invariants[-1] == FlowCheck.from_dict(extra)
    assert "(bu PR'da eklendi)" in review.render(r)


def test_broken_candidate_policy_is_rejected_not_ignored(tmp_path):
    cand = make_snapshot(tmp_path, "pr", "02-dogru.json")
    (cand / POLICY_FILE).write_text('{"invariants": [{"name": "eksik"}]}')
    verifier = RecordingVerifier()
    r = review.run_check(ACME, cand, verifier)
    assert r.exit_code == 1 and verifier.calls == []
    assert "PR'daki snapshot okunamadı" in review.render(r)


def test_missing_base_snapshot_is_an_error(tmp_path):
    r = review.run_check(tmp_path / "yok", ACME, RecordingVerifier())
    assert r.exit_code == 2 and not r.accepted
    assert "DOĞRULAMA ÇALIŞMADI" in review.render(r)


def test_verifier_failure_is_reported_as_error(tmp_path):
    verifier = RecordingVerifier(fail_with=ConnectionError("bağlantı reddedildi"))
    r = review.run_check(ACME, make_snapshot(tmp_path, "pr", "02-dogru.json"), verifier)
    assert r.exit_code == 2 and not r.accepted
    md = review.render(r)
    assert "DOĞRULAMA ÇALIŞMADI" in md and "bağlantı reddedildi" in md


def test_diff_fence_survives_backticks_in_config(tmp_path):
    cand = make_snapshot(tmp_path, "pr")
    core = cand / "configs" / "core.cfg"
    core.write_text(core.read_text().replace("description USERS", "description ```x```"))
    md = review.render(review.run_check(ACME, cand, RecordingVerifier()))
    assert "````diff" in md


def test_cli_check_subcommand(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        review, "main", lambda args: calls.append((args.base, args.candidate)) or 7
    )
    rc = cli.main(["check", "--base", "a", "--candidate", "b"])
    assert rc == 7 and calls == [(Path("a"), Path("b"))]


def test_check_main_writes_report_and_exit_code(tmp_path, capsys):
    out = tmp_path / "rapor.md"
    args = cli_args(ACME, make_snapshot(tmp_path, "pr", "01-fazla-genis.json"), out)
    assert review.main(args, verifier=RecordingVerifier()) == 1
    assert "REDDEDİLDİ" in out.read_text()
    assert "DEĞİŞMEZ İHLALİ" in capsys.readouterr().out


def cli_args(base, cand, out):
    p = argparse.ArgumentParser()
    review.add_subparser(p.add_subparsers(dest="cmd"))
    return p.parse_args(["check", "--base", str(base), "--candidate", str(cand), "--out", str(out)])


def test_pr_that_only_drops_an_invariant_is_rejected(tmp_path, capsys):
    """İki adımlı kaçış: önce değişmezi tek başına sil, sonra ihlal et. İlk adım kırmızı."""
    cand = make_snapshot(tmp_path, "pr")
    policy = json.loads((cand / POLICY_FILE).read_text())
    policy["invariants"] = [i for i in policy["invariants"] if i.get("dst_ports") != "22"]
    (cand / POLICY_FILE).write_text(json.dumps(policy))
    verifier = RecordingVerifier()
    out = tmp_path / "r.md"
    assert review.main(cli_args(ACME, cand, out), verifier=verifier) == 1
    assert verifier.calls == []
    md = out.read_text()
    assert "Kanıt etki raporu: REDDEDİLDİ" in md and "DEĞİŞMEDİ" not in md
    assert "'Kullanıcılar veritabanı sunucusuna SSH yapamaz' silindi" in md
    assert "DEĞİŞMEZ SİLİNDİ/DEĞİŞTİ" in capsys.readouterr().out


@pytest.mark.parametrize(
    "field,value",
    [
        ("expect", "reachable"),
        ("src", "10.10.10.0/32"),
        ("dst", "10.20.20.31"),
        ("protocol", "UDP"),
        ("dst_ports", "2222"),
        ("start", "@enter(core[GigabitEthernet0/2])"),
    ],
)
def test_pr_that_weakens_an_invariant_is_rejected(tmp_path, field, value):
    cand = make_snapshot(tmp_path, "pr")
    policy = json.loads((cand / POLICY_FILE).read_text())
    ssh = next(i for i in policy["invariants"] if i.get("dst_ports") == "22")
    old = ssh[field]
    ssh[field] = value
    (cand / POLICY_FILE).write_text(json.dumps(policy))

    r = review.run_check(ACME, cand, RecordingVerifier())
    assert r.exit_code == 1
    md = review.render(r)
    assert "REDDEDİLDİ" in md and "Ret sebebi" in md
    assert f"değiştirildi ({field}: {old} -> {value})" in md


@pytest.mark.parametrize(
    "policy",
    [
        "[1, 2]",  # kök liste
        '{"invariants": [5]}',  # öğe sayı
        '{"invariants": 5}',  # liste değil
        "{bozuk json",
    ],
)
def test_broken_candidate_policy_is_rejected_with_report(tmp_path, policy):
    cand = make_snapshot(tmp_path, "pr", "02-dogru.json")
    (cand / POLICY_FILE).write_text(policy)
    out = tmp_path / "r.md"
    assert review.main(cli_args(ACME, cand, out), verifier=RecordingVerifier()) == 1
    md = out.read_text()
    assert "REDDEDİLDİ" in md and "PR'daki snapshot okunamadı" in md


@pytest.mark.parametrize("policy", ["[1, 2]", '{"invariants": [5]}', "{bozuk json"])
def test_broken_base_policy_means_verification_did_not_run(tmp_path, policy):
    base = make_snapshot(tmp_path, "base")
    (base / POLICY_FILE).write_text(policy)
    out = tmp_path / "r.md"
    rc = review.main(
        cli_args(base, make_snapshot(tmp_path, "pr", "02-dogru.json"), out),
        verifier=RecordingVerifier(),
    )
    assert rc == 2
    md = out.read_text()
    assert "DOĞRULAMA ÇALIŞMADI" in md and "Hedef daldaki snapshot okunamadı" in md


SECRET = "sk-ant-GIZLI-ANAHTAR-123"


@pytest.mark.parametrize("target", ["configs/core.cfg", "policy.json", "configs"])
def test_symlink_in_candidate_is_rejected_without_reading_it(tmp_path, target):
    secret = tmp_path / "gizli.txt"
    secret.write_text(f"ANTHROPIC_API_KEY={SECRET}\n")
    cand = make_snapshot(tmp_path, "pr")
    path = cand / target
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    path.symlink_to(secret if target != "configs" else tmp_path)
    verifier = RecordingVerifier()
    out = tmp_path / "r.md"
    assert review.main(cli_args(ACME, cand, out), verifier=verifier) == 1
    assert verifier.calls == []
    md = out.read_text()
    assert "REDDEDİLDİ" in md and "sembolik bağlantı" in md
    assert SECRET not in md


def test_symlinked_snapshot_root_is_rejected(tmp_path, monkeypatch):
    real = make_snapshot(tmp_path, "gercek", "02-dogru.json")
    monkeypatch.chdir(tmp_path)
    Path("examples").mkdir()
    Path("examples/acme").symlink_to(real)
    r = review.run_check(ACME, Path("examples/acme"), RecordingVerifier())
    assert r.exit_code == 1 and "examples/acme" in r.verdict.error


def test_absolute_candidate_with_symlinked_middle_component_is_rejected(tmp_path, monkeypatch):
    """<cwd>/a/acme ve 'a' bağlantı: mutlak yol cwd'ye göre göreli denetlenir."""
    outside = make_snapshot(tmp_path / "disari", "acme", "02-dogru.json").parent
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.chdir(ws)
    Path("a").symlink_to(outside)
    verifier = RecordingVerifier()
    r = review.run_check(ACME, Path.cwd() / "a" / "acme", verifier)
    assert r.exit_code == 1 and verifier.calls == []
    assert "sembolik bağlantı" in r.verdict.error and "a" in r.verdict.error


@pytest.mark.parametrize("target", ["/proc/self/environ", "dosya"])
def test_linked_config_content_never_reaches_any_output(tmp_path, target):
    """configs/x.cfg -> /proc/self/environ: ortamdaki anahtar rapora ve çıktıya düşmez.

    macOS'ta /proc yoktur (bağlantı boşa gösterir); 'dosya' durumu aynı yolu gerçek bir
    gizli dosyayla sınar. Linux CI'da /proc/self/environ gerçekten anahtarı içerir.
    """
    secret_file = tmp_path / "gizli.txt"
    secret_file.write_text(f"ANTHROPIC_API_KEY={SECRET}\n")
    cand = make_snapshot(tmp_path, "pr")
    (cand / "configs" / "x.cfg").symlink_to(secret_file if target == "dosya" else target)
    out = tmp_path / "r.md"
    proc = subprocess.run(
        [sys.executable, "-m", "kanit.cli", "check", "--base", str(ACME),
         "--candidate", str(cand), "--out", str(out), "--batfish-host", "127.0.0.1"],
        env={**os.environ, "ANTHROPIC_API_KEY": SECRET},
        capture_output=True, text=True,
    )
    assert proc.returncode == 1, proc.stderr
    report = out.read_text()
    for text in (proc.stdout, proc.stderr, report):
        assert SECRET not in text
    assert "x.cfg" in report


@pytest.mark.parametrize(
    "field,value", [("src", {"ip": "10.0.0.1"}), ("src", ["10.0.0.1"]), ("dst", 5)]
)
def test_added_invariant_with_wrong_field_type_is_the_prs_fault(tmp_path, field, value):
    cand = make_snapshot(tmp_path, "pr")
    policy = json.loads((cand / POLICY_FILE).read_text())
    extra = {"name": "yeni", "start": "@enter(core[GigabitEthernet0/1])",
             "dst": "10.20.20.30", "expect": "blocked", field: value}
    policy["invariants"].append(extra)
    (cand / POLICY_FILE).write_text(json.dumps(policy))
    verifier = RecordingVerifier()
    r = review.run_check(ACME, cand, verifier)
    assert r.exit_code == 1 and verifier.calls == []
    assert f"'{field}' metin olmalı" in review.render(r)


def test_added_invariant_already_violated_by_base_is_visible_in_report(tmp_path):
    """Mevcut kural (Verdict.accepted): mevcut yapılandırmanın da ihlal ettiği eklenmiş
    değişmez kabulü engellemez; ama raporda açıkça görünür."""
    cand = make_snapshot(tmp_path, "pr")
    policy = json.loads((cand / POLICY_FILE).read_text())
    name = "Kullanıcılar 10.20.20.20'ye SSH yapamaz"
    policy["invariants"].append(
        {"name": name, "start": "@enter(core[GigabitEthernet0/1])", "src": "10.10.10.0/24",
         "dst": "10.20.20.20", "protocol": "TCP", "dst_ports": "22", "expect": "blocked"}
    )
    (cand / POLICY_FILE).write_text(json.dumps(policy))

    class PreexistingVerifier:
        def verify(self, base, candidate, invariants, intent_checks):
            return Verdict(checks=[
                CheckResult(c, "invariant", c.name != name,
                            "akış" if c.name == name else None, preexisting=c.name == name)
                for c in invariants
            ])

    r = review.run_check(ACME, cand, PreexistingVerifier())
    assert r.accepted
    row = next(line for line in review.render(r).splitlines() if name in line)
    assert "(bu PR'da eklendi)" in row and "zaten ihlalde" in row

