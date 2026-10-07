from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import shutil
import socket
import sys
import tempfile
import traceback
from pathlib import Path

from . import loop, report
from . import review
from . import verifier as _verifier
from .proposer import ClaudeProposer, ScriptedProposer
from .snapshot import CONFIG_DIR, read_configs, read_invariants
from .verifier import BatfishVerifier

# Batfish'in pybatfish (v2) portu ve ön kontrol için bağlantı süresi (saniye).
# pybatfish kendi başına 30 sn x yeniden deneme bekler; ön kontrol bunu kısaltır.
# KANIT_BATFISH_TIMEOUT ile değiştirilebilir (ör. testlerde 0.5).
BATFISH_PORT = 9996
BATFISH_CONNECT_TIMEOUT = 5.0
BATFISH_CONNECT_TIMEOUT_MAX = 600.0


class _NotRun(Exception):
    """Doğrulama çalışamadı (çıkış kodu 2); mesaj tek satır ve ne yapılacağını söyler."""


def _one_line(text: object) -> str:
    return " ".join(str(text).split())


def _os_reason(exc: OSError) -> str:
    if isinstance(exc, FileNotFoundError):
        return "dosya yok"
    if isinstance(exc, IsADirectoryError):
        return "dosya değil, klasör"
    if isinstance(exc, PermissionError):
        return "erişim izni yok"
    if isinstance(exc, TimeoutError):
        return "zaman aşımı"
    if isinstance(exc, ConnectionRefusedError):
        return "bağlantı reddedildi"
    if isinstance(exc, socket.gaierror):
        return "ana makine adı çözülemedi"
    return _one_line(exc) or type(exc).__name__


def _check_snapshot(snapshot: Path) -> None:
    try:
        read_configs(snapshot)
        read_invariants(snapshot)
    except Exception as exc:  # noqa: BLE001 - her okuma hatası "çalışmadı" (2) sayılır
        reason = _os_reason(exc) if isinstance(exc, OSError) else _one_line(exc)
        raise _NotRun(
            f"Snapshot okunamadı ({snapshot}): {type(exc).__name__}: {reason}. --snapshot ile "
            f"'{CONFIG_DIR}/' klasörü ve geçerli policy.json içeren klasörü ver."
        ) from None


def _scripted(paths: list[Path]) -> ScriptedProposer:
    for path in paths:
        try:
            json.loads(path.read_text())
        except OSError as exc:
            raise _NotRun(
                f"Kayıtlı öneri dosyası okunamadı ({path}): {_os_reason(exc)}. "
                "--scripted ile var olan JSON dosyalarını ver."
            ) from None
        except UnicodeDecodeError:
            raise _NotRun(
                f"Kayıtlı öneri dosyası UTF-8 metin değil ({path}). "
                "--scripted ile JSON dosyası ver."
            ) from None
        except json.JSONDecodeError as exc:
            raise _NotRun(
                f"Kayıtlı öneri dosyası geçerli JSON değil ({path}, satır {exc.lineno}, "
                f"sütun {exc.colno}). "
                "Dosyayı düzelt ya da başka bir kayıtlı öneri ver."
            ) from None
    return ScriptedProposer(paths)


def _check_batfish_host(host: str) -> None:
    """pybatfish yalnızca ana makine adı ya da IP alır; port ve şema sabittir."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if isinstance(addr, ipaddress.IPv6Address) or host.startswith("["):
        # pybatfish URL'yi f"{host}:{port}" diye kurar; '::1' InvalidURL verir.
        raise _NotRun(
            f"--batfish-host geçersiz ({host!r}): IPv6 adresi desteklenmiyor; "
            "ana makine adı ya da IPv4 ver. Örn. --batfish-host localhost"
        )
    if addr is not None:
        return
    if not host or any(ch in host for ch in ":/@ "):
        raise _NotRun(
            f"--batfish-host geçersiz ({host!r}): yalnızca ana makine adı ya da IP olmalı "
            f"(şema ve port yazma; port {BATFISH_PORT} sabit). Örn. --batfish-host localhost"
        )


def _connect_timeout() -> float:
    raw = os.environ.get("KANIT_BATFISH_TIMEOUT")
    if raw is None:
        return BATFISH_CONNECT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and 0 < value <= BATFISH_CONNECT_TIMEOUT_MAX):
        raise _NotRun(
            f"KANIT_BATFISH_TIMEOUT geçersiz ({raw!r}): 0'dan büyük, en çok "
            f"{BATFISH_CONNECT_TIMEOUT_MAX:g} saniyelik bir sayı ver (varsayılan "
            f"{BATFISH_CONNECT_TIMEOUT:g})."
        )
    return value


def _check_batfish(host: str) -> None:
    """Batfish'e kısa süreli TCP ön kontrolü; ulaşılamazsa uzun bekleme yerine hemen durur."""
    _check_batfish_host(host)
    try:
        socket.create_connection((host, BATFISH_PORT), timeout=_connect_timeout()).close()
    except OSError as exc:
        raise _NotRun(
            f"Batfish'e ulaşılamadı ({host}:{BATFISH_PORT}, {_os_reason(exc)}). "
            "Batfish'i başlat (make batfish) ya da --batfish-host / BATFISH_HOST ile "
            "doğru adresi ver."
        ) from None


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"en az 1 olmalı: {text!r}")
    return value


def main(argv: list[str] | None = None) -> int:
    """Güvenlik ağı: beklenmeyen her istisna tek satır mesaj ve 2 olur (ret değil).

    argparse'ın kendi çıkışları (SystemExit) ve KeyboardInterrupt Exception değildir,
    olduğu gibi geçer. KANIT_DEBUG=1 ise traceback da yazılır.
    """
    try:
        return _main(argv)
    except Exception as exc:  # noqa: BLE001 - çıkış kodu sözleşmesi: çalışmadı = 2
        if os.environ.get("KANIT_DEBUG") == "1":
            traceback.print_exc()
        print(
            f"Beklenmeyen hata: {type(exc).__name__}: {_one_line(exc)}; hata raporu için "
            "KANIT_DEBUG=1 ile çalıştır.",
            file=sys.stderr,
        )
        return 2


def _main(argv: list[str] | None) -> int:
    p = argparse.ArgumentParser(
        prog="kanit", description="Ağ değişikliğini Claude yazar, Batfish doğrular."
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan", help="Niyetten doğrulanmış değişiklik üret")
    plan.add_argument("intent", help="Düz dille değişiklik isteği")
    plan.add_argument("--snapshot", type=Path, required=True, help="configs/ içeren klasör")
    plan.add_argument(
        "--batfish-host", default=os.environ.get("BATFISH_HOST", "localhost")
    )
    plan.add_argument("--max-rounds", type=_positive_int, default=3)
    plan.add_argument("--model", default=None, help="Varsayılan: KANIT_MODEL ya da sonnet")
    plan.add_argument(
        "--scripted",
        type=Path,
        nargs="+",
        metavar="JSON",
        help="Claude yerine kayıtlı önerileri sırayla kullan (API anahtarı gerekmez)",
    )
    plan.add_argument("--out", type=Path, default=Path("kanit-rapor.md"))
    plan.add_argument(
        "--apply", action="store_true", help="Kabul edilen değişikliği snapshot'a yaz"
    )
    review.add_subparser(sub)
    args = p.parse_args(argv)
    if args.cmd == "check":
        return review.main(args)

    try:
        result = _plan(args)
    except _NotRun as exc:
        message = str(exc)
        print(message, file=sys.stderr)
        try:
            args.out.write_text(report.render_failure(args.intent, message))
            print(f"Rapor: {args.out}")
        except OSError:
            pass
        return 2
    if result is None:
        return 2
    decision = "kabul edildi" if result.accepted else "reddedildi"
    if result.error:
        decision = "doğrulama tamamlanmadı"
    try:
        args.out.write_text(report.render(result))
    except OSError as exc:
        print(
            f"Değişiklik {decision} ama rapor yazılamadı ({args.out}: {_os_reason(exc)}). "
            "Snapshot'a dokunulmadı; --out ile yazılabilir bir yol ver.",
            file=sys.stderr,
        )
        return 2
    for n, r in enumerate(result.rounds, 1):
        spent = f" ({r.usage.describe()})" if r.usage.calls else ""
        print(f"Tur {n}: {'KABUL' if r.verdict.accepted else 'RET'}{spent}")
        if not r.verdict.accepted:
            print("  " + r.verdict.feedback().replace("\n", "\n  "))
    if result.usage.calls:
        print(f"Toplam model kullanımı ({result.model}): {result.usage.describe()}")
    print(f"Rapor: {args.out}")
    if result.error:
        print(f"Durdu: {result.error}", file=sys.stderr)
        return 2

    if result.accepted and args.apply:
        try:
            changed = _apply_atomic(args.snapshot / CONFIG_DIR, result.final.candidate_configs)
        except _ApplyFailed as exc:
            print(f"Değişiklik kabul edildi ama {exc} Fark raporda: {args.out}", file=sys.stderr)
            return 2
        names = ", ".join(changed) or "değişen dosya yok"
        print(f"Değişiklik snapshot'a yazıldı ({names}).")
    return 0 if result.accepted else 1


class _ApplyFailed(Exception):
    """--apply teslim edilemedi; mesaj snapshot'ın son durumunu açıkça söyler."""


def _write_atomic(target: Path, data: bytes) -> None:
    """Aynı dizinde geçici dosyaya yazar ve os.replace ile değiştirir (izinler korunur)."""
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".kanit")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if target.exists():
            shutil.copymode(target, tmp)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _apply_atomic(cfg_dir: Path, configs: dict[str, str]) -> list[str]:
    """Kabul edilen yapılandırmaları ya hep ya hiç yazar; değişen dosya adlarını döndürür.

    Önce her hedef okunur ve yazılabilirliği sınanır (salt okunur dosya yazılmaz).
    Sonra dosyalar tek tek değiştirilir; biri başarısız olursa önceki değişiklikler
    özgün baytlarıyla geri yüklenir. Geri yükleme de başarısız olursa özgün içerikler
    bir yedek klasörüne yazılır ve mesaj snapshot'ın tutarsız olduğunu söyler.
    """
    originals: dict[str, bytes | None] = {}
    pending: dict[str, bytes] = {}
    try:
        for name, text in configs.items():
            target = cfg_dir / name
            old = target.read_bytes() if target.exists() else None
            new = text.encode("utf-8")
            if old == new:
                continue
            if old is not None and not os.access(target, os.W_OK):
                raise PermissionError(13, "erişim izni yok", str(target))
            originals[name], pending[name] = old, new
        if pending and not os.access(cfg_dir, os.W_OK):
            raise PermissionError(13, "erişim izni yok", str(cfg_dir))
    except OSError as exc:
        where = exc.filename or cfg_dir
        raise _ApplyFailed(
            f"snapshot'a yazılamadı ({where}: {_os_reason(exc)}); hiçbir dosya "
            "değişmedi, snapshot olduğu gibi."
        ) from None

    done: list[str] = []
    for name, data in pending.items():
        try:
            _write_atomic(cfg_dir / name, data)
        except OSError as exc:
            failure = f"{cfg_dir / name}: {_os_reason(exc)}"
            break
        done.append(name)
    else:
        return done

    not_restored = []
    for name in reversed(done):
        try:
            if originals[name] is None:
                (cfg_dir / name).unlink()
            else:
                _write_atomic(cfg_dir / name, originals[name])
        except OSError:
            not_restored.append(name)
    if not not_restored:
        raise _ApplyFailed(
            f"snapshot'a yazılamadı ({failure}); yazılan {len(done)} dosya özgün "
            "içeriğine geri yüklendi, snapshot olduğu gibi."
        )
    try:
        backup = Path(tempfile.mkdtemp(prefix="kanit-yedek-"))
        for name in not_restored:
            if originals[name] is not None:
                (backup / name).write_bytes(originals[name])
        where = f"özgün içerikleri {backup} yedeğinden geri al"
    except OSError as exc:
        where = (
            f"yedek de yazılamadı ({_os_reason(exc)}); özgün içerikleri sürüm "
            "denetiminden geri al"
        )
    raise _ApplyFailed(
        f"snapshot'a yazılamadı ({failure}) ve geri yükleme başarısız: snapshot TUTARSIZ; "
        f"şu dosyalar değişti: {', '.join(sorted(not_restored))}; {where}."
    )


def _plan(args: argparse.Namespace) -> loop.Result | None:
    """Girdileri ve Batfish'i önceden sınar, döngüyü çalıştırır. Çalışamazsa _NotRun."""
    max_rounds = args.max_rounds
    if args.scripted:
        _check_snapshot(args.snapshot)
        proposer = _scripted(args.scripted)
        # Kayıtlı öneriler bitince döngü durur: bu bir araç hatası değil, son turun
        # kararı geçerlidir. Bu yüzden tur sayısı öneri sayısıyla sınırlanır.
        max_rounds = min(max_rounds, len(args.scripted))
    else:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            print(
                "ANTHROPIC_API_KEY tanımlı değil. Anahtarı ortam değişkeni olarak ver "
                "ya da anahtarsız demo için --scripted kullan.",
                file=sys.stderr,
            )
            return None
        _check_snapshot(args.snapshot)
        proposer = ClaudeProposer(
            args.intent,
            read_configs(args.snapshot),
            read_invariants(args.snapshot),
            model=args.model,
        )

    verifier = BatfishVerifier(args.batfish_host)
    if isinstance(verifier, _verifier.BatfishVerifier):
        _check_batfish(args.batfish_host)
    try:
        return loop.run(args.intent, args.snapshot, proposer, verifier, max_rounds=max_rounds)
    except Exception as exc:  # noqa: BLE001 - doğrulama çalışmadı, çıkış kodu 2
        raise _NotRun(
            f"Doğrulama çalışmadı: {type(exc).__name__}: {_one_line(exc)}. Batfish'in "
            "çalıştığını denetle (docker compose logs batfish) ve yeniden dene."
        ) from None


if __name__ == "__main__":
    sys.exit(main())
