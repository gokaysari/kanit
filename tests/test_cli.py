"""`kanit plan` çıkış kodu sözleşmesi: 0 kabul, 1 ret, 2 doğrulama çalışmadı.

Çalışmadı (2) durumlarında çıktı tek satırlık, ne yapılacağını söyleyen Türkçe bir
mesajdır; ham traceback yoktur ve rapor dosyasına "DOĞRULAMA ÇALIŞMADI" yazılır.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
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


class AcceptingVerifier:
    """Her adayı kabul eder (kontrollerin hepsi geçer)."""

    def verify(self, base, candidate, invariants, intent_checks):
        v = Verdict()
        for c in [*invariants, *intent_checks]:
            v.checks.append(CheckResult(c, "invariant", True))
        return v


class ExplodingVerifier:
    """Doğrulama sırasında Batfish istemcisinin beklenmedik istisnası."""

    def verify(self, base, candidate, invariants, intent_checks):
        raise ConnectionResetError("Connection aborted.\nRemoteDisconnected")


def kanit(*args: str, host: str = "127.0.0.2", **env: str) -> subprocess.CompletedProcess:
    """CLI'yi ayrı süreçte çalıştırır; ham traceback çıktıda görünür olurdu."""
    return subprocess.run(
        [sys.executable, "-m", "kanit.cli", "plan", INTENT, "--batfish-host", host, *args],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, **env},
    )


def acme_copy(tmp_path: Path) -> Path:
    return Path(shutil.copytree(ACME, tmp_path / "acme"))


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


def test_unreachable_batfish_exits_2_quickly_and_writes_report(tmp_path):
    # Gerçek CLI, ayrı süreç. 127.0.0.2: macOS'ta zaman aşımı, Linux'ta bağlantı reddi;
    # ikisi de kısa ön kontrolle 2 vermeli. Süre sınırı yalnızca pybatfish'in kendi
    # dakikalarca süren beklemesini yakalar; alt süreç ve içe aktarma maliyeti ortama
    # göre değiştiği için kısa zaman aşımının kullanıldığını burada değil,
    # test_preflight_uses_configured_timeout sınar.
    out = tmp_path / "r.md"
    started = time.monotonic()
    p = kanit("--snapshot", str(ACME), "--scripted", str(GOOD), "--out", str(out),
              KANIT_BATFISH_TIMEOUT="0.5")
    assert time.monotonic() - started < 20
    assert p.returncode == 2
    assert_not_run(p.stderr, p.stdout, out, "Batfish'e ulaşılamadı", "127.0.0.2", "make batfish")


@pytest.mark.parametrize(("raw", "expected"), [(None, 5.0), ("0.5", 0.5), ("4", 4.0)])
def test_preflight_uses_configured_timeout(monkeypatch, raw, expected):
    # Ağdan ve saatten bağımsız: ön kontrolün socket'e verdiği zaman aşımını yakalar,
    # zaman aşımını zorlar ve mesajın aynı süreyi söylediğini doğrular.
    if raw is None:
        monkeypatch.delenv("KANIT_BATFISH_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("KANIT_BATFISH_TIMEOUT", raw)
    seen = []

    def fake_create_connection(address, timeout=None):
        seen.append((address, timeout))
        raise TimeoutError("timed out")

    monkeypatch.setattr(cli.socket, "create_connection", fake_create_connection)
    with pytest.raises(cli._NotRun) as info:
        cli._check_batfish("127.0.0.2")
    assert seen == [(("127.0.0.2", cli.BATFISH_PORT), expected)]
    assert f"zaman aşımı, {expected:g} sn" in str(info.value)


def test_connect_timeout_reads_env(monkeypatch):
    monkeypatch.delenv("KANIT_BATFISH_TIMEOUT", raising=False)
    assert cli._connect_timeout() == cli.BATFISH_CONNECT_TIMEOUT
    monkeypatch.setenv("KANIT_BATFISH_TIMEOUT", "0.5")
    assert cli._connect_timeout() == 0.5


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "1e400", "abc", "0", "-1", "601"])
def test_invalid_connect_timeout_exits_2(tmp_path, raw):
    out = tmp_path / "r.md"
    p = kanit("--snapshot", str(ACME), "--scripted", str(GOOD), "--out", str(out),
              KANIT_BATFISH_TIMEOUT=raw)
    assert p.returncode == 2
    assert_not_run(p.stderr, p.stdout, out, "KANIT_BATFISH_TIMEOUT geçersiz", "600")


@pytest.mark.parametrize("host", ["::1", "[::1]", "fe80::1"])
def test_ipv6_batfish_host_is_rejected_with_hint(tmp_path, host):
    out = tmp_path / "r.md"
    p = kanit("--snapshot", str(ACME), "--scripted", str(GOOD), "--out", str(out), host=host)
    assert p.returncode == 2
    assert_not_run(p.stderr, p.stdout, out, "IPv6 adresi desteklenmiyor", "IPv4")


@pytest.mark.parametrize("host", ["localhost:9996", "http://localhost", "bat fish"])
def test_batfish_host_with_port_or_scheme_exits_2_with_hint(tmp_path, host):
    out = tmp_path / "r.md"
    p = kanit("--snapshot", str(ACME), "--scripted", str(GOOD), "--out", str(out), host=host)
    assert p.returncode == 2
    assert "gaierror" not in p.stderr and ":9996:9996" not in p.stderr
    assert_not_run(p.stderr, p.stdout, out, "--batfish-host geçersiz", "ana makine adı ya da IP")


def test_policy_with_unexpected_shape_exits_2(tmp_path):
    snap = acme_copy(tmp_path)
    (snap / "policy.json").write_text("[]")
    out = tmp_path / "r.md"
    p = kanit("--snapshot", str(snap), "--scripted", str(GOOD), "--out", str(out))
    assert p.returncode == 2
    assert_not_run(p.stderr, p.stdout, out, "Snapshot okunamadı", "policy.json")


@pytest.mark.parametrize("rounds", ["0", "-1", "iki"])
def test_max_rounds_below_one_exits_2(tmp_path, rounds):
    p = kanit("--snapshot", str(ACME), "--scripted", str(GOOD), "--max-rounds", rounds,
              "--out", str(tmp_path / "r.md"))
    assert p.returncode == 2
    assert "en az 1 olmalı" in p.stderr and "Traceback" not in p.stderr
    assert not (tmp_path / "r.md").exists()


def test_unwritable_report_after_acceptance_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: AcceptingVerifier())
    out = tmp_path / "yok" / "r.md"
    code = cli.main(
        ["plan", INTENT, "--snapshot", str(ACME), "--scripted", str(GOOD), "--out", str(out)]
    )
    assert code == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1
    assert "kabul edildi ama rapor yazılamadı" in err[0] and "--out" in err[0]


TWO_FILE_MARK = "! kanit-iki-dosya"
CORE_RULE = " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.30 eq 5432\n"


def two_file_proposal(tmp_path: Path) -> Path:
    """core.cfg ve edge.cfg'yi birlikte düzenleyen öneri (edge ikinci yazılır)."""
    data = json.loads(GOOD.read_text())
    data["edits"].append(
        {"file": "edge.cfg", "old": "hostname edge\n", "new": f"hostname edge\n{TWO_FILE_MARK}\n"}
    )
    path = tmp_path / "iki-dosya.json"
    path.write_text(json.dumps(data))
    return path


def snapshot_bytes(snap: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted((snap / "configs").iterdir())}


def apply_plan(snap: Path, proposal: Path, out: Path) -> int:
    return cli.main(
        ["plan", INTENT, "--snapshot", str(snap), "--scripted", str(proposal), "--out", str(out),
         "--apply"]
    )


def single_err_line(capsys) -> str:
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1, err
    assert "yeniden çalıştır" not in err[0]  # tekrar uygulamaya yönlendirmez
    return err[0]


def test_unwritable_apply_after_acceptance_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: AcceptingVerifier())
    snap = acme_copy(tmp_path)
    for cfg in (snap / "configs").iterdir():
        cfg.chmod(stat.S_IRUSR)
    before = snapshot_bytes(snap)
    out = tmp_path / "r.md"
    assert apply_plan(snap, GOOD, out) == 2
    err = single_err_line(capsys)
    assert "kabul edildi ama snapshot'a yazılamadı" in err and "erişim izni yok" in err
    assert "hiçbir dosya değişmedi" in err
    assert out.read_text().startswith("# Kanıt raporu: KABUL EDİLDİ")
    assert snapshot_bytes(snap) == before


def test_two_file_apply_with_readonly_second_file_is_all_or_nothing(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: AcceptingVerifier())
    snap = acme_copy(tmp_path)
    proposal = two_file_proposal(tmp_path)
    edge = snap / "configs" / "edge.cfg"
    edge.chmod(stat.S_IRUSR)  # gerçek dosya izni: ikinci dosya salt okunur
    before = snapshot_bytes(snap)
    out = tmp_path / "r.md"

    assert apply_plan(snap, proposal, out) == 2
    err = single_err_line(capsys)
    assert "edge.cfg" in err and "hiçbir dosya değişmedi" in err
    assert snapshot_bytes(snap) == before  # iki dosyanın baytları da aynı

    # İzin düzeltilip yeniden uygulanınca düzenleme yalnızca bir kez görünür.
    edge.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert apply_plan(snap, proposal, out) == 0
    assert (snap / "configs" / "core.cfg").read_text().count(CORE_RULE) == 1
    assert edge.read_text().count(TWO_FILE_MARK) == 1
    assert not [p for p in (snap / "configs").iterdir() if p.name.startswith(".")]


def failing_replace(monkeypatch, fail_from: int, fail_to: int | None = None) -> None:
    """os.replace'in fail_from..fail_to (dahil; None: sonuna kadar) çağrılarını bozar."""
    real = os.replace
    calls = {"n": 0}

    def replace(src, dst):
        calls["n"] += 1
        if calls["n"] >= fail_from and (fail_to is None or calls["n"] <= fail_to):
            raise OSError(5, "G/Ç hatası (enjekte)")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", replace)


def test_apply_rolls_back_first_file_when_second_replace_fails(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: AcceptingVerifier())
    snap = acme_copy(tmp_path)
    proposal = two_file_proposal(tmp_path)
    before = snapshot_bytes(snap)
    # 1: core.cfg yazılır, 2: edge.cfg başarısız, 3: core.cfg geri yüklenir
    failing_replace(monkeypatch, fail_from=2, fail_to=2)

    assert apply_plan(snap, proposal, tmp_path / "r.md") == 2
    err = single_err_line(capsys)
    assert "geri yüklendi" in err and "snapshot olduğu gibi" in err
    assert snapshot_bytes(snap) == before
    assert not [p for p in (snap / "configs").iterdir() if p.name.startswith(".")]


def test_apply_reports_inconsistent_snapshot_and_backup_when_rollback_fails(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(cli, "BatfishVerifier", lambda host: AcceptingVerifier())
    snap = acme_copy(tmp_path)
    proposal = two_file_proposal(tmp_path)
    original_core = (snap / "configs" / "core.cfg").read_bytes()
    failing_replace(monkeypatch, fail_from=2)  # geri yükleme de os.replace kullanır

    assert apply_plan(snap, proposal, tmp_path / "r.md") == 2
    err = single_err_line(capsys)
    assert "TUTARSIZ" in err and "şu dosyalar değişti: core.cfg" in err
    backup = Path(re.search(r"(\S*kanit-yedek-\S+?) yedeğinden", err).group(1))
    assert (backup / "core.cfg").read_bytes() == original_core
    shutil.rmtree(backup)


def test_unexpected_exception_exits_2_without_traceback(monkeypatch, capsys, tmp_path):
    def boom(args):
        raise RuntimeError("beklenmedik\ndurum")

    monkeypatch.setattr(cli, "_plan", boom)
    monkeypatch.delenv("KANIT_DEBUG", raising=False)
    argv = ["plan", INTENT, "--snapshot", str(ACME), "--out", str(tmp_path / "r.md")]
    assert cli.main(argv) == 2
    cap = capsys.readouterr()
    assert "Traceback" not in cap.err + cap.out
    err = cap.err.strip().splitlines()
    assert err == ["Beklenmeyen hata: RuntimeError: beklenmedik durum; hata raporu için "
                   "KANIT_DEBUG=1 ile çalıştır."]

    monkeypatch.setenv("KANIT_DEBUG", "1")
    assert cli.main(argv) == 2
    assert "Traceback" in capsys.readouterr().err


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
