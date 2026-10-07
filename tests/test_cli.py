"""`kanit plan` çıkış kodu sözleşmesi: 0 kabul, 1 ret, 2 doğrulama çalışmadı.

Çalışmadı (2) durumlarında çıktı tek satırlık, ne yapılacağını söyleyen Türkçe bir
mesajdır; ham traceback yoktur ve rapor dosyasına "DOĞRULAMA ÇALIŞMADI" yazılır.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from kanit import cli
from kanit.models import CheckResult, Verdict
from kanit.proposer import ProposerError, ScriptedProposer

ACME = Path(__file__).parent.parent / "examples" / "acme"
BAD = ACME / "scripted" / "01-fazla-genis.json"
GOOD = ACME / "scripted" / "02-dogru.json"
INTENT = "Kullanıcı ağından veritabanı sunucusuna (10.20.20.30) tcp/5432 aç"
HOST = os.environ.get("BATFISH_HOST")


class RejectingVerifier:
    """Her adayı SSH değişmezini ihlal ediyor sayar."""

    def verify(self, base, candidate, invariants, intent_checks):
        v = Verdict()
        for inv in invariants:
            v.checks.append(CheckResult(inv, "invariant", False, "akış-x"))
        return v


class ExplodingVerifier:
    """Doğrulama sırasında Batfish istemcisinin beklenmedik istisnası."""

    def verify(self, base, candidate, invariants, intent_checks):
        raise ConnectionResetError("Connection aborted.\nRemoteDisconnected")


def kanit(*args: str, host: str = "127.0.0.2") -> subprocess.CompletedProcess:
    """CLI'yi ayrı süreçte çalıştırır; ham traceback çıktıda görünür olurdu."""
    return subprocess.run(
        [sys.executable, "-m", "kanit.cli", "plan", INTENT, "--batfish-host", host, *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def assert_not_run(stderr: str, stdout: str, report: Path, *needles: str) -> None:
    assert "Traceback" not in stderr + stdout
    lines = stderr.strip().splitlines()
    assert len(lines) == 1, lines
    for needle in needles:
        assert needle in lines[0]
    assert report.read_text().startswith("# Kanıt raporu: DOĞRULAMA ÇALIŞMADI")


# --- Y2: hata yolları 2 döner ---------------------------------------------------------


def test_missing_snapshot_exits_2_with_hint(tmp_path):
    out = tmp_path / "r.md"
    p = kanit("--snapshot", "/nonexistent", "--scripted", str(GOOD), "--out", str(out))
    assert p.returncode == 2
    assert_not_run(p.stderr, p.stdout, out, "Snapshot okunamadı", "--snapshot ile")


def test_broken_scripted_json_exits_2_with_hint(tmp_path):
    broken = tmp_path / "bozuk.json"
    broken.write_text("{bozuk")
    out = tmp_path / "r.md"
    p = kanit("--snapshot", str(ACME), "--scripted", str(broken), "--out", str(out))
    assert p.returncode == 2
    assert_not_run(p.stderr, p.stdout, out, "geçerli JSON değil", "satır 1", "düzelt")


def test_missing_scripted_file_exits_2_with_hint(tmp_path):
    out = tmp_path / "r.md"
    p = kanit("--snapshot", str(ACME), "--scripted", "/nonexistent.json", "--out", str(out))
    assert p.returncode == 2
    assert_not_run(p.stderr, p.stdout, out, "okunamadı", "dosya yok", "--scripted ile")


def test_unreachable_batfish_exits_2_quickly_and_writes_report(monkeypatch, capsys, tmp_path):
    # 127.0.0.2: macOS'ta zaman aşımı, Linux'ta bağlantı reddi; ikisi de 2 vermeli.
    monkeypatch.setattr(cli, "BATFISH_CONNECT_TIMEOUT", 0.5)
    out = tmp_path / "r.md"
    code = cli.main(
        ["plan", INTENT, "--snapshot", str(ACME), "--scripted", str(GOOD),
         "--batfish-host", "127.0.0.2", "--out", str(out)]
    )
    assert code == 2
    cap = capsys.readouterr()
    assert_not_run(cap.err, cap.out, out, "Batfish'e ulaşılamadı", "127.0.0.2", "make batfish")


def test_batfish_error_during_verification_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: ExplodingVerifier())
    out = tmp_path / "r.md"
    code = cli.main(
        ["plan", INTENT, "--snapshot", str(ACME), "--scripted", str(GOOD), "--out", str(out)]
    )
    assert code == 2
    cap = capsys.readouterr()
    assert_not_run(cap.err, cap.out, out, "Doğrulama çalışmadı", "ConnectionResetError")


# --- Y3: kayıtlı öneriler bitince son turun reddi 1, gerçek öneri hatası 2 -----------


def test_scripted_proposals_exhausted_after_rejection_exits_1(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: RejectingVerifier())
    out = tmp_path / "r.md"
    code = cli.main(
        ["plan", INTENT, "--snapshot", str(ACME), "--scripted", str(BAD), "--out", str(out)]
    )
    assert code == 1
    cap = capsys.readouterr()
    assert "Tur 1: RET" in cap.out and "Tur 2" not in cap.out
    assert "Durdu" not in cap.err
    assert out.read_text().startswith("# Kanıt raporu: REDDEDİLDİ")


def test_real_proposer_error_still_exits_2(monkeypatch, capsys, tmp_path):
    def fail(self, feedback):
        raise ProposerError("API hatası (529): overloaded")

    monkeypatch.setattr(ScriptedProposer, "propose", fail)
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: RejectingVerifier())
    out = tmp_path / "r.md"
    code = cli.main(
        ["plan", INTENT, "--snapshot", str(ACME), "--scripted", str(BAD), "--out", str(out)]
    )
    assert code == 2
    assert "Durdu: API hatası (529)" in capsys.readouterr().err
    assert "Döngü durdu" in out.read_text()


@pytest.mark.batfish
@pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil")
def test_scripted_broad_rule_against_real_batfish_exits_1(tmp_path):
    out = tmp_path / "r.md"
    p = kanit("--snapshot", str(ACME), "--scripted", str(BAD), "--out", str(out), host=HOST)
    assert p.returncode == 1, p.stderr
    assert "Traceback" not in p.stderr
    assert out.read_text().startswith("# Kanıt raporu: REDDEDİLDİ")
