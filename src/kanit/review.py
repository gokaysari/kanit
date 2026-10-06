"""Model çağrısı olmadan yalnızca doğrulama: PR'daki snapshot aday, hedef dal mevcut.

`kanit check --base <hedef dal snapshot> --candidate <PR snapshot>` iki snapshot'ın
yapılandırmalarını Batfish'e yükler, değişmezleri aday üzerinde kanıtlar ve etki raporu
yazar. Çıkış kodu: 0 kabul (ya da değişiklik yok), 1 ret, 2 doğrulama çalışmadı.

Değişmezler hedef daldaki `policy.json`'dan okunur ve PR'ın eklediği yeni değişmezler
de kontrol edilir (yalnızca sıkılaştırabilir). Hedef daldaki bir değişmezi silen ya da
değiştiren PR, yapılandırması ne olursa olsun reddedilir: aksi hâlde değişmez önce tek
başına silinip sonraki PR'da ihlal edilebilirdi.
"""

from __future__ import annotations

import argparse
import difflib
import json
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
    cand_invariants: list[FlowCheck] = field(default_factory=list)
    verdict: Verdict | None = None  # None: yapılandırma ve değişmezler değişmedi
    error: str | None = None  # doğrulama çalışmadı (altyapı ya da hedef dal sorunu)

    @property
    def changed(self) -> bool:
        return self.base_configs != self.cand_configs or bool(self.added_invariants)

    @property
    def accepted(self) -> bool:
        if self.error or self.dropped_invariants:
            return False
        return self.verdict is None or self.verdict.accepted

    def dropped_reasons(self) -> list[str]:
        """Hedef daldaki her silinen ya da değiştirilen değişmez için açıklama."""
        by_name = {c.name: c for c in self.cand_invariants}
        out = []
        for old in self.dropped_invariants:
            new = by_name.get(old.name)
            if new is None:
                out.append(f"'{old.name}' silindi")
                continue
            fields = ("start", "src", "dst", "protocol", "dst_ports", "expect")
            diffs = [
                f"{f}: {getattr(old, f) or '-'} -> {getattr(new, f) or '-'}"
                for f in fields
                if getattr(old, f) != getattr(new, f)
            ]
            out.append(f"'{old.name}' değiştirildi ({'; '.join(diffs)})")
        return out

    @property
    def exit_code(self) -> int:
        if self.error:
            return EXIT_ERROR
        return EXIT_ACCEPTED if self.accepted else EXIT_REJECTED


# policy.json'un kökü liste ya da öğesi sayı olduğunda read_invariants AttributeError /
# TypeError atar; bunlar da okuma hatasıdır, ham traceback değil.
_READ_ERRORS = (OSError, ValueError, ProposalError, AttributeError, TypeError)


def _why(exc: Exception) -> str:
    if isinstance(exc, (AttributeError, TypeError)):
        return f"{POLICY_FILE} beklenen biçimde değil ({{\"invariants\": [...]}}): {exc}"
    return str(exc)


def _read_policy(snapshot: Path) -> str:
    path = snapshot / POLICY_FILE
    return path.read_text() if path.exists() else ""


def unsafe_paths(snapshot: Path) -> list[str]:
    """Snapshot ağacındaki sembolik bağlantılar ve kök dışına çıkan yollar.

    PR'dan gelen bir bağlantı (ör. configs/x.cfg -> /proc/self/environ) okunursa
    snapshot dışındaki içerik rapora, PR yorumuna ya da modele gidebilir. Bu yüzden
    hiçbir şey okunmadan önce reddedilir.

    - '..' bileşeni içeren yol (göreli ya da mutlak) doğrudan reddedilir: '..' metin
      üzerinde çözülürse denetlenen yol ile fiziksel olarak okunan yol ayrışır.
    - Göreli yolda ve çalışma dizini altındaki mutlak yolda (cwd'ye göre göreli hâle
      getirilerek) yolun her bileşeni denetlenir.
    - Çalışma dizini dışındaki mutlak yolda yalnızca son bileşen denetlenir (macOS'ta
      /var gibi sistem bağlantıları yüzünden); eylem bu yüzden mutlak yolu kabul etmez.
    - Kök altında configs/, içindeki her dosya ve policy.json denetlenir.
    """
    if ".." in snapshot.parts:
        return [f"{snapshot} ('..' içeriyor)"]
    found: list[str] = []
    walked = Path()
    if snapshot.is_absolute():
        try:
            parts = snapshot.relative_to(Path.cwd()).parts
        except ValueError:
            parts = (str(snapshot),)
    else:
        parts = snapshot.parts
    for part in parts:
        walked = walked / part
        if walked.is_symlink():
            found.append(str(walked))
    if found:
        return found
    root = snapshot.resolve()
    cfg = snapshot / CONFIG_DIR
    targets = [cfg, snapshot / POLICY_FILE]
    if cfg.is_dir() and not cfg.is_symlink():
        targets += sorted(cfg.iterdir())
    for path in targets:
        if path.is_symlink():
            found.append(str(path))
        elif path.exists() and not path.resolve().is_relative_to(root):
            found.append(str(path))
    return found


_CHECK_FIELDS = ("name", "start", "dst", "expect", "src", "protocol", "dst_ports")


def _field_type_errors(policy_text: str) -> list[str]:
    """PR'daki değişmezlerde metin olmayan alanlar; Batfish'e gitmeden PR hatası sayılır."""
    if not policy_text:
        return []
    errors = []
    for n, item in enumerate(json.loads(policy_text).get("invariants", []), 1):
        for key in _CHECK_FIELDS:
            value = item.get(key)
            if value is not None and not isinstance(value, str):
                errors.append(
                    f"{n}. değişmezde '{key}' metin olmalı, {type(value).__name__} verildi"
                )
    return errors


def run_check(base: Path, candidate: Path, verifier: Verifier) -> Review:
    """Hedef daldaki değişmezlerle adayı doğrular. Kabul kuralı Verdict.accepted'dır."""
    links = unsafe_paths(base)
    if links:
        return Review(
            {}, {}, error=f"Hedef daldaki snapshot'ta sembolik bağlantı var: {', '.join(links)}"
        )
    try:
        review = Review(read_configs(base), {}, base_policy=_read_policy(base))
        review.invariants = read_invariants(base)
    except _READ_ERRORS as exc:
        return Review({}, {}, error=f"Hedef daldaki snapshot okunamadı: {_why(exc)}")

    links = unsafe_paths(candidate)
    if links:
        # Hiçbir şey okunmadan durulur; bağlantının hedefi rapora düşmez.
        review.verdict = Verdict(
            error="PR'daki snapshot sembolik bağlantı ya da snapshot dışına çıkan yol "
            f"içeriyor; okunmadı: {', '.join(links)}"
        )
        return review
    try:
        review.cand_configs = read_configs(candidate)
        review.cand_policy = _read_policy(candidate)
        review.cand_invariants = cand_invariants = read_invariants(candidate)
        type_errors = _field_type_errors(review.cand_policy)
        if type_errors:
            raise ProposalError("; ".join(type_errors))
    except _READ_ERRORS as exc:
        # PR'ın bozduğu snapshot reddedilir; doğrulanamayan değişiklik kabul edilmez.
        review.verdict = Verdict(error=f"PR'daki snapshot okunamadı: {_why(exc)}")
        return review

    review.added_invariants = [c for c in cand_invariants if c not in review.invariants]
    review.dropped_invariants = [c for c in review.invariants if c not in cand_invariants]
    if not review.changed:
        # Yalnızca değişmez silen PR da buraya gelir; Batfish gerekmez, kabul edilmez.
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
    elif not review.accepted:
        status = "REDDEDİLDİ"
    elif review.verdict is None:
        status = "YAPILANDIRMA DEĞİŞMEDİ"
    else:
        status = "KABUL EDİLDİ"
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
    if review.dropped_invariants:
        out += [
            "**Ret sebebi: bu PR hedef daldaki değişmezleri siliyor ya da değiştiriyor.** "
            "Değişmezin kaldırılması ya da gevşetilmesi bu kontrolden geçemez; "
            "yapılandırma değişikliğinden ayrı, insan kararıyla yapılmalıdır.",
            "",
        ] + [f"- {_cell(r)}" for r in review.dropped_reasons()] + [""]

    unreadable = review.verdict is not None and review.verdict.error is not None
    diff: list[str] = []
    if not unreadable:  # aday okunamadıysa fark "her şey silindi" gibi görünürdü
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
    elif not review.error and not unreadable:
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
    else:
        print("KABUL" if review.accepted else "RET")
        for reason in review.dropped_reasons():
            print(f"  DEĞİŞMEZ SİLİNDİ/DEĞİŞTİ: {reason}")
        if review.verdict is None:
            print("  Yapılandırma değişmedi.")
        elif not review.verdict.accepted:
            print("  " + review.verdict.feedback().replace("\n", "\n  "))
    print(f"Rapor: {args.out}")
    return review.exit_code

