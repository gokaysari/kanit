"""Raporu PR yorumu olarak yazar; aynı işaretli yorum varsa yenisini açmadan günceller.

Yalnızca standart kütüphane. Ortam: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_API_URL
(varsayılan https://api.github.com). Kullanım:

    python post_comment.py --pr 12 --marker kanit-rapor rapor.md [--log komut.log]

Rapor dosyası yoksa (araç çökmüşse) doğrulamanın çalışmadığını söyleyen bir yorum yazar;
sessiz kalmaz.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

MAX_BODY = 60000  # GitHub yorum sınırı 65536 karakter
LOG_TAIL = 40
BOT_LOGIN = os.environ.get("KANIT_BOT_LOGIN", "github-actions[bot]")  # GITHUB_TOKEN'ın yazarı


def build_body(marker: str, report: Path, log: Path | None) -> str:
    tag = f"<!-- {marker} -->"
    if report.is_file() and report.read_text().strip():
        text = report.read_text()
    else:
        text = (
            "## Kanıt etki raporu: DOĞRULAMA ÇALIŞMADI\n\n"
            "Araç rapor üretemeden durdu; değişiklik doğrulanmış sayılmaz. "
            "Ayrıntı iş günlüğünde."
        )
        if log is not None and log.is_file():
            tail = "\n".join(log.read_text(errors="replace").splitlines()[-LOG_TAIL:])
            longest = max((len(m) for m in re.findall(r"`+", tail)), default=0)
            fence = "`" * max(3, longest + 1)
            text += f"\n\n{fence}\n{tail}\n{fence}"
    if len(text) > MAX_BODY:
        text = text[:MAX_BODY] + "\n\n…(rapor kısaltıldı; tamamı iş özetinde)\n"
    return f"{tag}\n{text}"


class GitHub:
    def __init__(self, token: str, repo: str, api: str):
        self.token, self.repo, self.api = token, repo, api.rstrip("/")

    def request(self, method: str, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.api}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "kanit-pr-bot",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
        return json.loads(body) if body else None

    def find_comment(self, pr: int, tag: str) -> int | None:
        page = 1
        while True:
            items = self.request(
                "GET", f"/repos/{self.repo}/issues/{pr}/comments?per_page=100&page={page}"
            )
            for c in items:
                # Yalnızca bu iş akışının (bot) yazdığı yorum güncellenir; kullanıcı
                # yorumuna işaret kopyalansa bile ona dokunulmaz.
                user = c.get("user") or {}
                if (
                    c.get("body", "").startswith(tag)
                    and user.get("type") == "Bot"
                    and user.get("login") == BOT_LOGIN
                ):
                    return c["id"]
            if len(items) < 100:
                return None
            page += 1

    def upsert(self, pr: int, tag: str, body: str) -> str:
        existing = self.find_comment(pr, tag)
        if existing is None:
            self.request("POST", f"/repos/{self.repo}/issues/{pr}/comments", {"body": body})
            return "created"
        self.request("PATCH", f"/repos/{self.repo}/issues/comments/{existing}", {"body": body})
        return "updated"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("report", type=Path)
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--marker", default="kanit-rapor")
    p.add_argument("--log", type=Path)
    args = p.parse_args(argv)

    body = build_body(args.marker, args.report, args.log)
    gh = GitHub(
        os.environ["GITHUB_TOKEN"],
        os.environ["GITHUB_REPOSITORY"],
        os.environ.get("GITHUB_API_URL", "https://api.github.com"),
    )
    action = gh.upsert(args.pr, f"<!-- {args.marker} -->", body)
    print(f"PR #{args.pr} yorumu: {'yazıldı' if action == 'created' else 'güncellendi'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
