"""Model çağrısı olmadan yalnızca doğrulama: PR'daki snapshot aday, hedef dal mevcut.

`kanit check --base <hedef dal snapshot> --candidate <PR snapshot>` iki snapshot'ın
yapılandırmalarını Batfish'e yükler, değişmezleri aday üzerinde kanıtlar ve etki raporu
yazar. Çıkış kodu: 0 kabul (ya da değişiklik yok), 1 ret, 2 doğrulama çalışmadı.

Değişmezler hedef daldaki `policy.json`'dan okunur; PR bir değişmezi silse ya da
gevşetse bile hedef daldaki hâli uygulanır. PR'ın eklediği yeni değişmezler de
kontrol edilir (yalnızca sıkılaştırabilir).
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .models import FlowCheck, ProposalError, Verdict
from .snapshot import CONFIG_DIR, POLICY_FILE, read_configs, read_invariants, write_candidate
from .verifier import Verifier

EXIT_ACCEPTED, EXIT_REJECTED, EXIT_ERROR = 0, 1, 2


@dataclass
class Review:
    base_configs: dict[str, str]
    cand_configs: dict[str, str]
    base_policy: str = ""
    cand_policy: str = ""
    invariants: list[FlowCheck] = field(default_factory=list)
    added_invariants: list[FlowCheck] = field(default_factory=list)
    dropped_invariants: list[FlowCheck] = field(default_factory=list)
    verdict: Verdict | None = None  # None: yapılandırma ve değişmezler değişmedi
    error: str | None = None  # doğrulama çalışmadı (altyapı ya da hedef dal sorunu)

    @property
    def changed(self) -> bool:
        return self.base_configs != self.cand_configs or bool(self.added_invariants)

    @property
    def accepted(self) -> bool:
        if self.error:
            return False
        return self.verdict is None or self.verdict.accepted

    @property
    def exit_code(self) -> int:
        if self.error:
            return EXIT_ERROR
        return EXIT_ACCEPTED if self.accepted else EXIT_REJECTED


def _read_policy(snapshot: Path) -> str:
    path = snapshot / POLICY_FILE
    return path.read_text() if path.exists() else ""


def run_check(base: Path, candidate: Path, verifier: Verifier) -> Review:
    """Hedef daldaki değişmezlerle adayı doğrular. Kabul kuralı Verdict.accepted'dır."""
    try:
        review = Review(read_configs(base), {}, base_policy=_read_policy(base))
        review.invariants = read_invariants(base)
    except (OSError, ValueError, ProposalError) as exc:
        return Review({}, {}, error=f"Hedef daldaki snapshot okunamadı: {exc}")

    try:
        review.cand_configs = read_configs(candidate)
        review.cand_policy = _read_policy(candidate)
        cand_invariants = read_invariants(candidate)
    except (OSError, ValueError, ProposalError) as exc:
        # PR'ın bozduğu snapshot reddedilir; doğrulanamayan değişiklik kabul edilmez.
        review.verdict = Verdict(error=f"PR'daki snapshot okunamadı: {exc}")
        return review

    review.added_invariants = [c for c in cand_invariants if c not in review.invariants]
    review.dropped_invariants = [c for c in review.invariants if c not in cand_invariants]
    if not review.changed:
        return review

    with tempfile.TemporaryDirectory(prefix="kanit-check-") as tmp:
        # Yalnızca configs/ doğrulanır; raporlanan fark ile doğrulanan şey aynı olsun.
        base_dir = write_candidate(review.base_configs, Path(tmp) / "base")
        cand_dir = write_candidate(review.cand_configs, Path(tmp) / "cand")
        checks = review.invariants + review.added_invariants
        try:
            review.verdict = verifier.verify(base_dir, cand_dir, checks, [])
        except Exception as exc:  # noqa: BLE001 - raporda gösterilir, çıkış kodu 2
            review.error = f"Batfish doğrulaması çalışmadı: {type(exc).__name__}: {exc}"
    return review


# --- rapor -------------------------------------------------------------------------

_LONGEST_TICKS = re.compile(r"`+")


def _fence(text: str) -> str:
    longest = max((len(m) for m in _LONGEST_TICKS.findall(text)), default=0)
    return "`" * max(3, longest + 1)


def _code(text: str) -> str:
    """Satır içi kod; içerik ters tırnak içerse de dışarı taşmaz."""
    text = " ".join(str(text).split())
    longest = max((len(m) for m in _LONGEST_TICKS.findall(text)), default=0)
    ticks = "`" * (longest + 1)
    return f"{ticks} {text.replace('|', '¦')} {ticks}"


def _cell(text: str) -> str:
    """Tablo hücresi: yapılandırmadan ya da PR'dan gelen metin tabloyu bozamaz."""
    text = " ".join(str(text).split())
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;")


def _diff(base: dict[str, str], cand: dict[str, str], prefix: str) -> list[str]:
    out: list[str] = []
    for name in sorted(set(base) | set(cand)):
        old, new = base.get(name), cand.get(name)
        if old == new:
            continue
        out.extend(
            difflib.unified_diff(
                (old or "").splitlines(),
                (new or "").splitlines(),
                f"a/{prefix}{name}" if old is not None else "/dev/null",
                f"b/{prefix}{name}" if new is not None else "/dev/null",
                lineterm="",
            )
        )
    return out


def render(review: Review, base_label: str = "hedef dal", cand_label: str = "PR") -> str:
    if review.error:
        status = "DOĞRULAMA ÇALIŞMADI"
    elif review.verdict is None:
        status = "YAPILANDIRMA DEĞİŞMEDİ"
    else:
        status = "KABUL EDİLDİ" if review.accepted else "REDDEDİLDİ"
    out = [
        f"## Kanıt etki raporu: {status}",
        "",
        f"**Mevcut:** {_cell(base_label)} · **Aday:** {_cell(cand_label)}",
        "",
    ]
    if review.error:
        out += [
            f"Değişiklik doğrulanamadı; kabul edilmiş sayılmaz. {_cell(review.error)}",
            "",
        ]

    diff = _diff(review.base_configs, review.cand_configs, f"{CONFIG_DIR}/")
    diff += _diff(
        {POLICY_FILE: review.base_policy} if review.base_policy else {},
        {POLICY_FILE: review.cand_policy} if review.cand_policy else {},
        "",
    )
    if diff:
        body = "\n".join(diff)
        fence = _fence(body)
        out += ["### Değişiklik", "", f"{fence}diff", body, fence, ""]
    elif not review.error:
        out += ["Bu PR snapshot'taki yapılandırmalara ya da değişmezlere dokunmuyor.", ""]

    v = review.verdict
    if v is not None and v.error:
        out += [f"**Aday doğrulamaya gönderilemedi:** {_cell(v.error)}", ""]
    elif v is not None:
        failed = len(v.failures)
        proven = sum(1 for c in v.checks if c.passed)
        out += [
            f"**Kontroller:** {len(v.checks)} değişmez, {proven} kanıtlandı, {failed} ihlal.",
            "",
            "| Değişmez | Beklenti | Sonuç |",
            "|---|---|---|",
        ]
        added = set(review.added_invariants)
        for c in v.checks:
            want = "ulaşır" if c.check.expect == "reachable" else "engellenir"
            name = _cell(c.check.name) + (" (bu PR'da eklendi)" if c.check in added else "")
            if c.passed:
                res = "kanıtlandı"
            elif c.preexisting:
                res = f"zaten ihlalde (değişiklikten bağımsız): {_code(c.counterexample)}"
            else:
                res = f"**ihlal**, karşı örnek: {_code(c.counterexample)}"
            out.append(f"| {name} | {want} | {res} |")
        out.append("")
        for title, items in (
            ("Yeni ayrıştırma sorunları", v.new_parse_issues),
            ("Yeni tanımsız referanslar", v.new_undefined_refs),
            ("Davranışı değişen örnek akışlar (öncesi -> sonrası)", v.changed_flows),
        ):
            if items:
                out += [f"**{title}**", ""] + [f"- {_code(i)}" for i in items] + [""]

    if review.dropped_invariants:
        out += [
            "**Uyarı:** bu PR değişmez dosyasından şu kuralları siliyor ya da değiştiriyor. "
            "Doğrulama hedef daldaki hâlleriyle yapıldı; kaldırılmaları ayrıca insan onayı "
            "ister:",
            "",
        ] + [f"- {_cell(c.name)}" for c in review.dropped_invariants] + [""]

    out += [
        "<sub>Model çağrısı yapılmadı; yalnızca Batfish doğrulaması. Değişmezler hedef "
        f"daldaki <code>{POLICY_FILE}</code> dosyasından okunur. Araç hiçbir cihaza "
        "bağlanmaz.</sub>",
        "",
    ]
    return "\n".join(out)


# --- komut satırı ---------------------------------------------------------------------


def add_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "check",
        help="Model olmadan yalnızca doğrula: PR snapshot'ı aday, hedef dal mevcut",
    )
    p.add_argument("--base", type=Path, required=True, help="Hedef daldaki snapshot klasörü")
    p.add_argument("--candidate", type=Path, required=True, help="PR'daki snapshot klasörü")
    p.add_argument("--batfish-host", default=os.environ.get("BATFISH_HOST", "localhost"))
    p.add_argument("--out", type=Path, default=Path("kanit-rapor.md"))
    p.add_argument("--base-label", default="hedef dal", help="Raporda mevcut için ad")
    p.add_argument("--candidate-label", default="PR", help="Raporda aday için ad")


def main(args: argparse.Namespace, verifier: Verifier | None = None) -> int:
    if verifier is None:
        from .verifier import BatfishVerifier

        verifier = BatfishVerifier(args.batfish_host)
    review = run_check(args.base, args.candidate, verifier)
    args.out.write_text(render(review, args.base_label, args.candidate_label))
    if review.error:
        print(review.error, file=sys.stderr)
    elif review.verdict is None:
        print("Yapılandırma değişmedi.")
    else:
        print("KABUL" if review.accepted else "RET")
        if not review.accepted:
            print("  " + review.verdict.feedback().replace("\n", "\n  "))
    print(f"Rapor: {args.out}")
    return review.exit_code

