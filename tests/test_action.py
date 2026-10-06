"""GitHub Action'ı (.github/actions/kanit-check) yerelde, gerçek Batfish'e karşı koşar.

GitHub'ın yaptığını küçük ölçekte taklit eder: action.yml'deki bash adımlarını sırayla,
`if:` koşulları ve `${{ }}` ifadeleriyle çalıştırır. Çalışma alanı, PR birleştirme
commit'i (refs/pull/N/merge, fetch-depth: 2) olan geçici bir git deposudur. GitHub API'si
yerine yorumları kaydeden sahte bir sunucu kullanılır.

Çalıştırılmayan adımlar: `uses:` adımları (setup-python) ve Kanıt'ın kurulumu (paket test
ortamında zaten kurulu).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from kanit.models import Proposal
from kanit.snapshot import apply_edits, read_configs

ROOT = Path(__file__).parent.parent
ACME = ROOT / "examples" / "acme"
ACTION_DIR = ROOT / ".github" / "actions" / "kanit-check"
HOST = os.environ.get("BATFISH_HOST")
REPO = "acme/ag-yapilandirma"
TOKEN = "test-belirteci"
SKIPPED_STEPS = {"Kanıt'ı kur"}


# --- sahte GitHub API ------------------------------------------------------------


class FakeGitHub:
    def __init__(self):
        self.comments: dict[int, dict] = {}
        self.requests: list[tuple[str, str]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, payload):
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _handle(self, method):
                fake.requests.append((method, self.path))
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._reply(401, {"message": "Bad credentials"})
                length = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(length)) if length else None
                m = re.fullmatch(rf"/repos/{REPO}/issues/(\d+)/comments(\?.*)?", self.path)
                if m and method == "GET":
                    pr = int(m.group(1))
                    items = [c for c in fake.comments.values() if c["pr"] == pr]
                    return self._reply(200, items)
                if m and method == "POST":
                    cid = len(fake.comments) + 1
                    fake.comments[cid] = {
                        "id": cid,
                        "pr": int(m.group(1)),
                        "body": data["body"],
                        "user": {"login": "github-actions[bot]", "type": "Bot"},
                    }
                    return self._reply(201, fake.comments[cid])
                m = re.fullmatch(rf"/repos/{REPO}/issues/comments/(\d+)", self.path)
                if m and method == "PATCH":
                    fake.comments[int(m.group(1))]["body"] = data["body"]
                    return self._reply(200, fake.comments[int(m.group(1))])
                return self._reply(404, {"message": "Not Found"})

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_PATCH(self):
                self._handle("PATCH")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def github():
    fake = FakeGitHub()
    yield fake
    fake.close()


# --- PR deposunu kur -------------------------------------------------------------


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def apply_scripted(snapshot: Path, scripted: str) -> None:
    raw = json.loads((ACME / "scripted" / scripted).read_text())
    for name, text in apply_edits(read_configs(snapshot), Proposal.from_dict(raw)).items():
        (snapshot / "configs" / name).write_text(text)


class PullRequest:
    """main dalı + PR dalı; çalışma alanı GitHub'daki gibi birleştirme commit'inde."""

    def __init__(self, root: Path):
        self.repo = root / "repo"
        shutil.copytree(ACME, self.repo / "examples" / "acme")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "temel")
        self.pr_base_sha = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-qb", "pr")
        # PR açıldıktan sonra main ilerlesin: mevcut snapshot HEAD^1'den gelmeli.
        git(self.repo, "checkout", "-q", "main")
        (self.repo / "README.md").write_text("ilgisiz değişiklik\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "main ilerledi")
        self.main_sha = git(self.repo, "rev-parse", "HEAD")

    def push(self, scripted: str) -> None:
        """PR dalına bir değişiklik ekler ve refs/pull/N/merge benzeri commit'e geçer."""
        git(self.repo, "checkout", "-q", "pr")
        apply_scripted(self.repo / "examples" / "acme", scripted)
        git(self.repo, "commit", "-qam", scripted)
        self.head_sha = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-q", "--detach", self.main_sha)
        git(self.repo, "merge", "-q", "--no-ff", "-m", "merge", self.head_sha)


# --- action.yml çalıştırıcısı ----------------------------------------------------

EXPR = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")
CONTEXT_REF = re.compile(r"\b(?:inputs|github|steps)(?:\.[A-Za-z0-9_-]+)+")


def evaluate(expr: str, ctx: dict[str, str]):
    """GitHub ifadelerinin bu action'da kullanılan alt kümesi."""
    py = CONTEXT_REF.sub(lambda m: repr(ctx.get(m.group(0), "")), expr)
    py = py.replace("always()", "True").replace("&&", " and ").replace("||", " or ")
    return eval(py, {"__builtins__": {}})  # noqa: S307 - yalnızca action.yml'deki ifadeler


def substitute(value: str, ctx: dict[str, str]) -> str:
    return EXPR.sub(lambda m: str(evaluate(m.group(1), ctx)), str(value))


def run_action(pr: PullRequest, github: FakeGitHub, tmp: Path, head_repo: str = REPO):
    action = yaml.safe_load((ACTION_DIR / "action.yml").read_text())
    ctx = {
        "github.token": TOKEN,
        "github.repository": REPO,
        "github.base_ref": "main",
        "github.event.pull_request.number": "7",
        "github.event.pull_request.base.sha": pr.pr_base_sha,
        "github.event.pull_request.head.sha": pr.head_sha,
        "github.event.pull_request.head.repo.full_name": head_repo,
    }
    with_ = {"snapshot": "examples/acme", "batfish-host": HOST}
    for name, spec in action["inputs"].items():
        ctx[f"inputs.{name}"] = substitute(with_.get(name, spec.get("default", "")), ctx)

    summary = tmp / "summary.md"
    summary.write_text("")
    runner_temp = tmp / "runner"
    runner_temp.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_ACTION_PATH": str(ACTION_DIR),
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_API_URL": github.url,
        "GITHUB_WORKSPACE": str(pr.repo),
        "GITHUB_STEP_SUMMARY": str(summary),
        "RUNNER_TEMP": str(runner_temp),
    }

    failed, ran, last_rc, logs = False, [], 0, []
    for i, step in enumerate(action["runs"]["steps"]):
        if "uses" in step or step.get("name") in SKIPPED_STEPS:
            continue
        cond = step.get("if")
        if cond is None and failed:
            continue
        if cond is not None and (failed and "always()" not in cond or not evaluate(cond, ctx)):
            continue
        output = tmp / f"output-{i}"
        output.write_text("")
        step_env = {**env, "GITHUB_OUTPUT": str(output)}
        step_env.update({k: substitute(v, ctx) for k, v in step.get("env", {}).items()})
        script = tmp / f"step-{i}.sh"
        script.write_text(step["run"])
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
            cwd=pr.repo, env=step_env, capture_output=True, text=True,
        )
        ran.append(step["name"])
        logs.append(f"--- {step['name']} (rc={proc.returncode})\n{proc.stdout}{proc.stderr}")
        for line in output.read_text().splitlines():
            k, _, v = line.partition("=")
            ctx[f"steps.{step.get('id')}.outputs.{k}"] = v
        last_rc = proc.returncode
        if proc.returncode != 0:
            failed = True
    log = "\n".join(logs)
    print(log)
    return {"failed": failed, "rc": last_rc, "ran": ran, "ctx": ctx, "log": log,
            "summary": summary.read_text()}


# --- testler ---------------------------------------------------------------------

@pytest.mark.batfish
@pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil")
def test_violating_pr_turns_red_then_fix_turns_green_with_one_comment(tmp_path, github):
    pr = PullRequest(tmp_path)

    # 1. push: 'permit ip' SSH değişmezini bozar -> kontrol kırmızı, yorum açılır.
    pr.push("01-fazla-genis.json")
    run = run_action(pr, github, tmp_path)
    assert run["failed"] and run["rc"] == 1
    assert run["ctx"]["steps.check.outputs.result"] == "rejected"
    assert "Raporu PR yorumu olarak yaz" in run["ran"]
    (comment,) = github.comments.values()
    body = comment["body"]
    assert comment["pr"] == 7 and body.startswith("<!-- kanit-rapor -->\n")
    assert "Kanıt etki raporu: REDDEDİLDİ" in body
    assert "**ihlal**" in body and "10.20.20.30:22" in body
    # Mevcut snapshot, PR açılışındaki commit değil, birleştirmenin ilk ebeveyni.
    assert f"main @ {pr.main_sha[:7]}" in body
    assert f"PR #7 @ {pr.head_sha[:7]}" in body
    assert "REDDEDİLDİ" in run["summary"]

    # 2. push: yalnızca tcp/5432 -> kontrol yeşil, aynı yorum güncellenir.
    git(pr.repo, "checkout", "-q", "pr")
    git(pr.repo, "revert", "--no-edit", "HEAD")
    pr.push("02-dogru.json")
    run = run_action(pr, github, tmp_path)
    assert not run["failed"] and run["rc"] == 0
    assert run["ctx"]["steps.check.outputs.result"] == "accepted"
    assert len(github.comments) == 1
    body = github.comments[1]["body"]
    assert "Kanıt etki raporu: KABUL EDİLDİ" in body
    assert "3 değişmez, 3 kanıtlandı, 0 ihlal" in body
    assert ("PATCH", f"/repos/{REPO}/issues/comments/1") in github.requests


@pytest.mark.batfish
@pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil")
def test_fork_pr_gets_no_comment_but_still_turns_red(tmp_path, github):
    pr = PullRequest(tmp_path)
    pr.push("01-fazla-genis.json")
    run = run_action(pr, github, tmp_path, head_repo="yabanci/ag-yapilandirma")
    assert run["failed"] and run["rc"] == 1
    assert github.requests == [] and github.comments == {}
    assert "Fork PR'ı: yorum yazılmadı" in run["log"]
    assert "REDDEDİLDİ" in run["summary"]


def test_comment_script_reports_missing_report_instead_of_staying_silent(tmp_path, github):
    """Araç çökerse (rapor yok) yorum yine düşer ve günlüğün sonunu gösterir."""
    log = tmp_path / "kanit.log"
    log.write_text("Traceback ...\nConnectionError: Batfish yok\n")
    env = {**os.environ, "GITHUB_TOKEN": TOKEN, "GITHUB_REPOSITORY": REPO,
           "GITHUB_API_URL": github.url}
    subprocess.run(
        [sys.executable, str(ACTION_DIR / "post_comment.py"), str(tmp_path / "yok.md"),
         "--pr", "3", "--log", str(log)],
        env=env, check=True, capture_output=True,
    )
    (comment,) = github.comments.values()
    assert "DOĞRULAMA ÇALIŞMADI" in comment["body"]
    assert "ConnectionError: Batfish yok" in comment["body"]


@pytest.mark.parametrize(
    "user",
    [
        {"login": "biri", "type": "User"},
        {"login": "baska-bot[bot]", "type": "Bot"},  # başka bir uygulamanın yorumu
    ],
)
def test_comment_script_only_updates_its_own_comment(tmp_path, github, user):
    github.comments[1] = {"id": 1, "pr": 3, "body": "<!-- kanit-rapor -->\nbaşkasının",
                          "user": user}
    report = tmp_path / "r.md"
    report.write_text("## Kanıt etki raporu: KABUL EDİLDİ\n")
    env = {**os.environ, "GITHUB_TOKEN": TOKEN, "GITHUB_REPOSITORY": REPO,
           "GITHUB_API_URL": github.url}
    subprocess.run(
        [sys.executable, str(ACTION_DIR / "post_comment.py"), str(report), "--pr", "3"],
        env=env, check=True, capture_output=True,
    )
    assert github.comments[1]["body"].endswith("başkasının")
    assert "KABUL EDİLDİ" in github.comments[2]["body"]


@pytest.mark.batfish
@pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil")
def test_pr_that_only_drops_an_invariant_turns_red(tmp_path, github):
    """İki adımlı kaçışın ilk adımı (yalnızca policy.json) eylemde de kırmızı."""
    pr = PullRequest(tmp_path)
    git(pr.repo, "checkout", "-q", "pr")
    policy_path = pr.repo / "examples" / "acme" / "policy.json"
    policy = json.loads(policy_path.read_text())
    policy["invariants"] = [i for i in policy["invariants"] if i.get("dst_ports") != "22"]
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2))
    git(pr.repo, "commit", "-qam", "değişmezi sil")
    pr.head_sha = git(pr.repo, "rev-parse", "HEAD")
    git(pr.repo, "checkout", "-q", "--detach", pr.main_sha)
    git(pr.repo, "merge", "-q", "--no-ff", "-m", "merge", pr.head_sha)

    run = run_action(pr, github, tmp_path)
    assert run["failed"] and run["rc"] == 1
    assert run["ctx"]["steps.check.outputs.result"] == "rejected"
    (comment,) = github.comments.values()
    assert "Kanıt etki raporu: REDDEDİLDİ" in comment["body"]
    assert "SSH yapamaz' silindi" in comment["body"]


def test_workflows_follow_security_limits():
    """pull_request_target yok; izinler dar; plan akışı fork'ta sırra ulaşmadan durur."""
    wf_dir = ROOT / ".github" / "workflows"
    for path in wf_dir.glob("*.yml"):
        wf = yaml.safe_load(path.read_text())
        triggers = wf.get("on", wf.get(True))  # YAML 1.1: 'on' anahtarı True olur
        assert "pull_request_target" not in triggers, path.name

    pr_wf = yaml.safe_load((wf_dir / "kanit-pr.yml").read_text())
    assert pr_wf["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert "secrets." not in (wf_dir / "kanit-pr.yml").read_text()
    assert "secrets." not in (ACTION_DIR / "action.yml").read_text()

    plan_text = (wf_dir / "kanit-plan.yml").read_text()
    plan = yaml.safe_load(plan_text)
    assert plan["permissions"] == {}
    job = plan["jobs"]["plan"]
    assert job["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert "author_association" in job["if"]
    names = [s.get("name", s.get("uses")) for s in job["steps"]]
    secret_steps = [i for i, s in enumerate(job["steps"]) if "secrets." in json.dumps(s)]
    fork_gate = names.index("PR'ın kaynağını denetle (fork ise dur)")
    assert secret_steps and all(i > fork_gate for i in secret_steps)
    link_gate = names.index(PLAN_GATE)
    assert all(i > link_gate for i in secret_steps)
    # Yorum metni kabuğa doğrudan gömülmez, ortam değişkeniyle geçer.
    for step in job["steps"]:
        assert "github.event.comment.body" not in step.get("run", "")


# --- kanit-plan: PR snapshot'ı denetimi (sır kullanan adımdan önce) ---------------

PLAN_GATE = "PR snapshot'ını denetle ve hazırla"


def run_plan_gate(ws: Path) -> subprocess.CompletedProcess:
    """kanit-plan.yml'deki denetim adımını GitHub'ın bash çağrısıyla koşar."""
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "kanit-plan.yml").read_text())
    (step,) = [s for s in wf["jobs"]["plan"]["steps"] if s.get("name") == PLAN_GATE]
    script = ws / "gate.sh"
    script.write_text(step["run"])
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        cwd=ws, env={**os.environ, "SNAPSHOT": wf["env"]["SNAPSHOT"]},
        capture_output=True, text=True,
    )


@pytest.fixture
def plan_ws(tmp_path):
    """Varsayılan dal çalışma alanı + .kanit-pr altında PR checkout'u."""
    ws = tmp_path / "ws"
    shutil.copytree(ACME, ws / "examples" / "acme")
    shutil.copytree(ACTION_DIR, ws / ".github" / "actions" / "kanit-check")
    shutil.copytree(ACME, ws / ".kanit-pr" / "examples" / "acme")
    return ws


def test_plan_gate_copies_default_branch_policy_into_clean_pr_snapshot(plan_ws):
    pr_policy = plan_ws / ".kanit-pr" / "examples" / "acme" / "policy.json"
    pr_policy.write_text('{"invariants": []}')
    proc = run_plan_gate(plan_ws)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert pr_policy.read_text() == (ACME / "policy.json").read_text()


@pytest.mark.parametrize("target", ["policy.json", "configs/core.cfg", "snapshot"])
def test_plan_gate_stops_on_symlink_before_secret_step(plan_ws, target):
    victim = plan_ws / ".github" / "actions" / "kanit-check" / "post_comment.py"
    before = victim.read_text()
    snap = plan_ws / ".kanit-pr" / "examples" / "acme"
    if target == "snapshot":
        real = plan_ws / ".kanit-pr" / "baska"
        snap.rename(real)
        snap.symlink_to(real)
    else:
        (snap / target).unlink()
        # Denetçinin gösterdiği saldırı: cp bağlantının hedefine yazardı.
        (snap / target).symlink_to(Path("../../../.github/actions/kanit-check/post_comment.py")
                                   if target == "policy.json" else Path("/proc/self/environ"))
    proc = run_plan_gate(plan_ws)
    assert proc.returncode == 1
    assert "::error::" in proc.stdout and "sembolik bağlantı" in proc.stdout
    assert victim.read_text() == before
    assert "reddedildi" in (plan_ws / "kanit-plan.log").read_text()
