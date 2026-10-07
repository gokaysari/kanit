from __future__ import annotations

import difflib

from .loop import Result, Round
from .snapshot import CONFIG_DIR


def _diff(base: dict[str, str], cand: dict[str, str]) -> str:
    chunks = []
    for name in sorted(base):
        if base[name] == cand.get(name):
            continue
        chunks.extend(
            difflib.unified_diff(
                base[name].splitlines(),
                cand[name].splitlines(),
                f"a/{CONFIG_DIR}/{name}",
                f"b/{CONFIG_DIR}/{name}",
                lineterm="",
            )
        )
    return "\n".join(chunks)


def _round(r: Round, n: int, base: dict[str, str]) -> list[str]:
    v = r.verdict
    status = "KABUL" if v.accepted else "RET"
    out = [f"## Tur {n}: {status}", ""]
    if r.usage.calls:
        out += [f"Model kullanımı: {r.usage.describe()}", ""]
    if v.error:
        return out + [f"Öneri uygulanamadı: {v.error}", ""]
    out += [r.proposal.summary, "", "```diff", _diff(base, r.candidate_configs), "```", ""]
    out += ["| Kontrol | Tür | Beklenti | Sonuç |", "|---|---|---|---|"]
    for c in v.checks:
        kind = "değişmez" if c.kind == "invariant" else "niyet"
        want = "ulaşır" if c.check.expect == "reachable" else "engellenir"
        if c.passed:
            res = "kanıtlandı"
        elif c.preexisting:
            res = f"zaten ihlalde (değişiklikten bağımsız): `{c.counterexample}`"
        else:
            res = f"**ihlal**: `{c.counterexample}`"
        out.append(f"| {c.check.name} | {kind} | {want} | {res} |")
    out.append("")
    for title, items in (
        ("Yeni ayrıştırma sorunları", v.new_parse_issues),
        ("Yeni tanımsız referanslar", v.new_undefined_refs),
        ("Davranışı değişen örnek akışlar (öncesi -> sonrası)", v.changed_flows),
    ):
        if items:
            out += [f"**{title}**", ""] + [f"- `{i}`" for i in items] + [""]
    return out


def render(result: Result) -> str:
    verdict = "KABUL EDİLDİ" if result.accepted else "REDDEDİLDİ"
    out = [
        f"# Kanıt raporu: {verdict}",
        "",
        f"**Niyet:** {result.intent}",
        "",
        f"**Tur sayısı:** {len(result.rounds)}",
        "",
    ]
    if result.usage.calls:
        out += [
            f"**Model:** {result.model} · **Toplam kullanım:** {result.usage.describe()}",
            "",
        ]
    for n, r in enumerate(result.rounds, 1):
        out += _round(r, n, result.base_configs)
    if result.error:
        out += [f"**Döngü durdu:** {result.error}", ""]
    if not result.accepted:
        out += ["Hiçbir öneri doğrulamadan geçmedi; yapılandırmaya dokunulmadı.", ""]
    return "\n".join(out)
