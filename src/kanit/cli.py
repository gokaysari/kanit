from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import loop, report
from .proposer import ClaudeProposer, ScriptedProposer
from .snapshot import CONFIG_DIR, read_configs, read_invariants
from .verifier import BatfishVerifier


def main(argv: list[str] | None = None) -> int:
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
    plan.add_argument("--max-rounds", type=int, default=3)
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
    args = p.parse_args(argv)

    if args.scripted:
        proposer = ScriptedProposer(args.scripted)
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY tanımlı değil (ya da --scripted kullan).", file=sys.stderr)
            return 2
        proposer = ClaudeProposer(
            args.intent,
            read_configs(args.snapshot),
            read_invariants(args.snapshot),
            model=args.model,
        )

    result = loop.run(
        args.intent,
        args.snapshot,
        proposer,
        BatfishVerifier(args.batfish_host),
        max_rounds=args.max_rounds,
    )
    args.out.write_text(report.render(result))
    for n, r in enumerate(result.rounds, 1):
        print(f"Tur {n}: {'KABUL' if r.verdict.accepted else 'RET'}")
        if not r.verdict.accepted:
            print("  " + r.verdict.feedback().replace("\n", "\n  "))
    print(f"Rapor: {args.out}")

    if result.accepted and args.apply:
        for name, text in result.final.candidate_configs.items():
            (args.snapshot / CONFIG_DIR / name).write_text(text)
        print("Değişiklik snapshot'a yazıldı.")
    return 0 if result.accepted else 1


if __name__ == "__main__":
    sys.exit(main())
