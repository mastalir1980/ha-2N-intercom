"""Hermetic regressions for the headless coder's owned-clone lifecycle."""

from __future__ import annotations

import csv
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest


CODER_DIR = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/mastalir1980/ha-2N-intercom.git"

STUB = """\
import json
import os
from pathlib import Path
import re
import subprocess
import sys

root = Path(os.environ["HA2N_CODER_TEST_ROOT"])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.log").open("a") as log:
    log.write(name + " " + " ".join(args) + "\\n")

if name == "id" and args == ["-un"]:
    print("wrong-user" if (root / "wrong-user").exists() else "ha2n-coder")
elif name == "getent" and args == ["passwd", "ha2n-coder"]:
    print(f"ha2n-coder:x:1000:1000:Test:{root / 'home'}:/bin/bash")
elif name == "sudo" and args[:3] == ["-n", "-u", "ha2n-copilot"]:
    expected = root / "usr/local/lib/ha2n-coder/sandbox.sh"
    if len(args) < 5 or args[3] != str(expected):
        sys.exit("unexpected sandbox invocation")
    os.execv(args[3], args[3:])
elif name == "backlog" and args[:2] == ["task", "view"] and "--json" in args:
    # backlog.md 1.53+ only; without the switch the stub behaves like 1.48 ("unknown option")
    fixture = root / "tasks" / f"{args[2]}.json"
    if not (root / "backlog-json").exists() or not fixture.exists():
        print("error: unknown option '--json'", file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(fixture.read_text(encoding="utf-8"))
elif name == "backlog" and args == ["task", "view", "TASK-34", "--plain"]:
    print("Task TASK-34 - Test clone recovery")
    task = Path("backlog/task-34.md")
    status = re.search(r"^Status: (.+)$", task.read_text(), re.M).group(1) if task.exists() else "To Do"
    print("Status: " + status)
    print("Assignee: @copilot")
    if (root / "task-labels").exists():
        print("Labels: " + (root / "task-labels").read_text().strip())
    print("Description:")
    print("Hermetic fixture")
    print("Acceptance Criteria:")
    criteria = root / "task-criteria"
    changed = root / "task-close-criteria"
    if changed.exists() and Path("plain.txt").read_text() == "accepted change\\n":
        criteria = changed
    print(criteria.read_text().strip() if criteria.exists() else "- [ ] #1 Fixture criterion")
    print("Definition of Done:")
    print("- [ ] #1 A separate definition-of-done item, not an acceptance criterion")
elif name == "backlog" and args[:3] == ["task", "edit", "TASK-34"]:
    if (root / "backlog-edit-fails").exists():
        sys.exit("Fixture backlog edit failure")
    Path("backlog").mkdir(exist_ok=True)
    status = args[args.index("-s") + 1]
    criteria = root / "task-criteria"
    text = criteria.read_text() if criteria.exists() else "- [ ] #1 Fixture criterion\\n"
    for index, arg in enumerate(args):
        if arg == "--check-ac":
            text = text.replace("- [ ] #" + args[index + 1] + " ", "- [x] #" + args[index + 1] + " ")
    summary = args[args.index("--final-summary") + 1]
    Path("backlog/task-34.md").write_text(f"Status: {status}\\n{text}\\nFinal Summary:\\n{summary}\\n")
    if (root / "backlog-edit-outside").exists():
        Path("outside-backlog.txt").write_text("Unexpected edit\\n")
elif name == "backlog" and args[:2] == ["task", "view"] and len(args) == 4 and (root / "tasks" / f"{args[2]}.txt").exists():
    sys.stdout.write((root / "tasks" / f"{args[2]}.txt").read_text(encoding="utf-8"))
elif name == "backlog" and args[:2] == ["task", "list"]:
    print("To Do:")
    for path in sorted((root / "tasks").glob("TASK-*.txt")):
        head = path.read_text(encoding="utf-8").split("Description:")[0]
        if re.search("^Status: .*To Do", head, re.M) is None:
            continue
        priority = re.search("^Priority: ([A-Za-z]+)", head, re.M).group(1)
        task_id, title = re.search("^Task (TASK-[^ ]+) - (.*)$", head, re.M).groups()
        print(f"  [{priority.upper()}] {task_id} - {title}")
elif name == "backlog" and args[:2] == ["milestone", "list"]:
    sys.stdout.write((root / "milestones.txt").read_text(encoding="utf-8"))
elif name == "sleep":
    pass
elif name == "gh" and (root / "gh-ok").exists():
    if args[:2] == ["label", "create"]:
        pass
    elif args[:2] == ["pr", "create"]:
        print("https://github.com/mastalir1980/ha-2N-intercom/pull/99")
    elif args[:2] == ["pr", "view"]:
        print(subprocess.run(
            ["git", "--git-dir", str(root / "origin.git"), "rev-parse",
             "refs/heads/task-34-test-clone-recovery"],
            check=True, capture_output=True, text=True,
        ).stdout.strip())
    elif args[:2] == ["pr", "checks"]:
        counter = root / "checks-count"
        index = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(index))
        scripted = root / "checks" / f"{index}.json"
        print(scripted.read_text() if scripted.exists() else json.dumps([
            {"name": "e2e-pi", "bucket": "pass", "link": ""},
            {"name": "hassfest", "bucket": "pass", "link": ""},
        ]))
    elif args[:2] == ["pr", "merge"]:
        head = subprocess.run(
            ["git", "--git-dir", str(root / "origin.git"), "rev-parse",
             "refs/heads/task-34-test-clone-recovery"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if (root / "head-moved").exists():
            head = "f" * 40
        if (root / "merge-refuse").exists():
            sys.stderr.write((root / "merge-refuse").read_text())
            sys.exit(1)
        if args[args.index("--match-head-commit") + 1] != head:
            sys.stderr.write("GraphQL: Head branch was modified. Review and try the merge again. (mergePullRequest)\\n")
            sys.exit(1)
        (root / "merged").write_text(" ".join(args))
        if "--delete-branch" in args:
            (root / "deleted-branch-head").write_text(head)
            subprocess.run(
                ["git", "--git-dir", str(root / "origin.git"), "update-ref", "-d",
                 "refs/heads/task-34-test-clone-recovery"],
                check=True, capture_output=True,
            )
    elif args[:2] == ["pr", "comment"]:
        comments = root / "comments"
        comments.mkdir(exist_ok=True)
        body = (
            Path(args[args.index("--body-file") + 1]).read_text()
            if "--body-file" in args else args[args.index("--body") + 1]
        )
        (comments / f"{len(list(comments.iterdir())) + 1}.md").write_text(body)
    else:
        sys.exit(f"unexpected gh invocation: {args}")
elif name == "copilot" and args in ([], ["--review"]):
    prompts = root / "prompts"
    prompts.mkdir(exist_ok=True)
    prompt = sys.stdin.read()
    if "TASK-" not in prompt:
        sys.exit("missing task prompt")
    kind = "review" if args else "coder"
    index = len(list(prompts.glob(f"{kind}-*.md"))) + 1
    (prompts / f"{kind}-{index}.md").write_text(prompt)
    if args:
        print("model: review-model-x")
        output = root / "review-output"
        output.unlink(missing_ok=True)
        scripted = root / "reviews" / f"{index}.json"
        if scripted.exists():
            output.write_text(scripted.read_text())
        if (root / "review-rc").exists():
            sys.exit(int((root / "review-rc").read_text()))
        sys.exit(0)
    stop_for = [p.name[len("copilot-stop-"):] for p in root.glob("copilot-stop-TASK-*")]
    if (root / "copilot-stop").exists() or any(
            re.search(r"\\b" + re.escape(task) + r"\\b", prompt) for task in stop_for):
        print("=== Copilot asked to stop ===")
        print("Fixture stops after the ready check")
        sys.exit(3)
    print("Fixture implementation")
else:
    sys.exit(f"unexpected {name} invocation: {args}")
"""


class RunTaskCloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bash = shutil.which("bash")
        if bash is None:
            raise unittest.SkipTest("Bash 4+ is required")
        version = subprocess.run(
            [bash, "-c", 'printf "%s" "${BASH_VERSINFO[0]}"'],
            check=True, capture_output=True, text=True,
        )
        if int(version.stdout) < 4:
            raise unittest.SkipTest("Bash 4+ is required (macOS system Bash is 3.x)")
        flock = shutil.which("flock")
        if flock is None:
            raise unittest.SkipTest("flock is required")
        git = shutil.which("git")
        if git is None:
            raise unittest.SkipTest("git is required")
        real_user = subprocess.run(
            ["/usr/bin/id", "-un"], check=True, capture_output=True, text=True,
        )
        if real_user.stdout.strip() == "ha2n-coder":
            raise unittest.SkipTest("Hermetic tests require a non-production OS user")
        cls.bash = bash
        cls.flock = flock
        cls.git = git

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="ha2n-coder-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.base = self.root / "var/lib/ha2n-coder"
        (self.base / "runs").mkdir(parents=True)
        self.clone = self.base / "repo"
        self.origin = self.root / "origin.git"
        self.seed = self.root / "seed"
        self.env = {
            "PATH": f"{self.bin}{os.pathsep}{os.defpath}",
            "HOME": str(self.home),
            "LC_ALL": "C",
            "HA2N_CODER_TEST_ROOT": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(self.home / ".gitconfig"),
            "GIT_ALLOW_PROTOCOL": "file",
            "GIT_TERMINAL_PROMPT": "0",
        }
        for name, executable in (
            ("bash", self.bash), ("flock", self.flock),
            ("git", self.git), ("python3", sys.executable),
        ):
            (self.bin / name).symlink_to(executable)
        stub = self.bin / "stub"
        stub.write_text(f"#!{sys.executable}\n{STUB}", encoding="utf-8")
        stub.chmod(0o755)
        for name in ("id", "getent", "sudo", "gh", "backlog", "copilot", "sleep"):
            (self.bin / name).symlink_to(stub)
        lib = self.root / "usr/local/lib/ha2n-coder"
        (lib / "prompts").mkdir(parents=True)
        for name in ("implement.md", "fix.md", "review.md"):
            shutil.copyfile(CODER_DIR / "prompts" / name, lib / "prompts" / name)
        sandbox = lib / "sandbox.sh"
        sandbox.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            set -euo pipefail
            case "$1" in
              prepare|gates) ;;
              copilot) copilot ;;
              review)
                rc=0
                copilot --review || rc=$?
                echo; echo "=== REVIEW JSON ==="
                [ ! -f "$HA2N_CODER_TEST_ROOT/review-output" ] || cat "$HA2N_CODER_TEST_ROOT/review-output"
                exit "$rc" ;;
              patch) cat "$HA2N_CODER_TEST_ROOT/change.diff" ;;
              *) exit 2 ;;
            esac
            """), encoding="utf-8")
        sandbox.chmod(0o755)
        token = self.root / "etc/ha2n-coder/repo.token"
        token.parent.mkdir(parents=True)
        token.write_text("fixture-not-a-real-token\n", encoding="utf-8")
        self._git(self.root, "config", "--global", "user.name", "Coder Test")
        self._git(self.root, "config", "--global", "user.email", "coder@example.invalid")
        self._git(self.root, "config", "--global", "commit.gpgsign", "false")
        self._git(
            self.root, "config", "--global",
            f"url.{self.origin.as_uri()}.insteadOf", REPO_URL,
        )
        self._git(self.root, "init", "-q", "--bare", "--initial-branch=main", str(self.origin))
        self._git(self.root, "clone", "-q", str(self.origin), str(self.seed))
        (self.seed / "e2e").mkdir()
        (self.seed / "e2e/.env.example").write_text("original template\n", encoding="utf-8")
        (self.seed / "plain.txt").write_text("original\n", encoding="utf-8")
        (self.seed / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
        self._commit_main("Initial fixture")

    def _git(self, cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(
            [self.git, *args], cwd=cwd, env=self.env if env is None else env,
            check=True, capture_output=True, text=True, timeout=15,
        )
        return result.stdout

    def _commit_main(self, message: str, *, committed_at: int | None = None) -> None:
        self._git(self.seed, "add", "-A")
        env = None
        if committed_at is not None:
            env = {**self.env, "GIT_AUTHOR_DATE": f"{committed_at} +0000",
                   "GIT_COMMITTER_DATE": f"{committed_at} +0000"}
        self._git(self.seed, "commit", "-q", "-m", message, env=env)
        self._git(self.seed, "push", "-q", "origin", "main")

    def _write_patch(self) -> None:
        self._git(self.seed, "add", "-A")
        patch = self._git(self.seed, "diff", "--cached", "--binary", "--full-index")
        (self.root / "change.diff").write_text(patch, encoding="utf-8")
        self._git(self.seed, "reset", "-q", "--hard")

    def _run(self, number: int = 1) -> subprocess.CompletedProcess[str]:
        self.run_id = f"20260101-{number:06d}-TASK-34"
        result = subprocess.run(
            [
                self.bash, str(CODER_DIR / "run-task.sh"),
                "--foreground", "TASK-34", "--run", self.run_id,
            ],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def _assert_clean(self) -> None:
        self.assertEqual(
            self._git(self.clone, "status", "--porcelain", "--untracked-files=all", "--ignored"),
            "",
        )

    def _assert_rejected(self, message: str) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stdout)
        status = (self.base / "runs" / self.run_id / "status").read_text(encoding="utf-8")
        self.assertIn("state=stopped\n", status)
        self.assertIn(f"message={message}", status)
        self._assert_clean()
        self.assertEqual(
            self._git(self.clone, "rev-parse", "HEAD"),
            self._git(self.seed, "rev-parse", "HEAD"),
        )
        self.assertEqual(
            self._git(self.origin, "for-each-ref", "--format=%(refname)"),
            "refs/heads/main\n",
        )
        self.assertNotIn("\ngh ", "\n" + (self.root / "calls.log").read_text(encoding="utf-8"))

    def test_protected_stop_then_upstream_edit_then_next_run_is_ready(self) -> None:
        template = self.seed / "e2e/.env.example"
        template.write_text("rejected template\n", encoding="utf-8")
        self._write_patch()
        self._assert_rejected("change touches protected paths: e2e/.env.example")
        self.assertEqual(
            (self.clone / "e2e/.env.example").read_text(encoding="utf-8"),
            "original template\n",
        )

        template.write_text("updated upstream template\n", encoding="utf-8")
        self._commit_main("Update the same protected file on main")
        (self.root / "copilot-stop").touch()
        result = self._run(2)
        self.assertIn("ready: Test clone recovery", result.stdout)
        self.assertIn("Copilot stopped: Fixture stops after the ready check", result.stdout)
        self.assertNotIn("cannot reset own clone", result.stdout)
        self._assert_clean()
        self.assertEqual(
            self._git(self.clone, "rev-parse", "HEAD"),
            self._git(self.seed, "rev-parse", "HEAD"),
        )

    def _assert_dirty_start_recovers(self, detached: bool) -> None:
        self._git(self.root, "clone", "-q", str(self.origin), str(self.clone))
        if detached:
            self._git(self.clone, "checkout", "-q", "--detach")
        else:
            self._git(self.clone, "checkout", "-q", "-b", "leftover")
            (self.clone / "plain.txt").write_text("previous branch commit\n", encoding="utf-8")
            self._git(self.clone, "commit", "-qam", "Previous branch")
        (self.clone / "e2e/.env.example").write_text("staged leftover\n", encoding="utf-8")
        self._git(self.clone, "add", "e2e/.env.example")
        (self.clone / "plain.txt").write_text("unstaged leftover\n", encoding="utf-8")
        (self.clone / "new-on-main.txt").write_text("untracked collision\n", encoding="utf-8")
        (self.clone / "untracked.txt").write_text("untracked leftover\n", encoding="utf-8")
        (self.clone / "ignored.tmp").write_text("ignored leftover\n", encoding="utf-8")
        (self.seed / "e2e/.env.example").write_text("new main template\n", encoding="utf-8")
        (self.seed / "new-on-main.txt").write_text("tracked on main\n", encoding="utf-8")
        self._commit_main("Advance main over staged and untracked paths")
        (self.root / "copilot-stop").touch()

        result = self._run()
        self.assertIn("ready: Test clone recovery", result.stdout)
        self.assertIn("Copilot stopped:", result.stdout)
        self._assert_clean()
        self.assertEqual(
            self._git(self.clone, "rev-parse", "HEAD"),
            self._git(self.seed, "rev-parse", "HEAD"),
        )
        self.assertEqual(self._git(self.clone, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD\n")

    def test_start_discards_leftovers_on_another_branch(self) -> None:
        self._assert_dirty_start_recovers(detached=False)

    def test_start_discards_leftovers_on_detached_head(self) -> None:
        self._assert_dirty_start_recovers(detached=True)

    def test_symlink_rejection_cleans_the_clone(self) -> None:
        (self.seed / "link").symlink_to("plain.txt")
        self._write_patch()
        self._assert_rejected("symlinks, submodules and file-mode changes are not allowed")

    def test_mode_change_rejection_cleans_the_clone(self) -> None:
        (self.seed / "plain.txt").chmod(0o755)
        self._write_patch()
        self._assert_rejected("symlinks, submodules and file-mode changes are not allowed")

    def test_binary_rejection_cleans_the_clone(self) -> None:
        (self.seed / "binary.dat").write_bytes(b"fixture\0binary\n")
        self._write_patch()
        self._assert_rejected("binary files are not allowed")

    def test_line_limit_rejection_cleans_the_clone(self) -> None:
        (self.seed / "large.txt").write_text("line\n" * 2501, encoding="utf-8")
        self._write_patch()
        self._assert_rejected("change too big for one PR (")

    def test_file_limit_rejection_cleans_the_clone(self) -> None:
        for number in range(41):
            (self.seed / f"file-{number}.txt").write_text("line\n", encoding="utf-8")
        self._write_patch()
        self._assert_rejected("change too big for one PR (")

    def test_invalid_patch_stops_with_a_clean_clone(self) -> None:
        (self.root / "change.diff").write_text("not a patch\n", encoding="utf-8")
        self._assert_rejected("diff does not apply on main (apply-0.log)")

    def test_commit_failure_cleans_the_clone(self) -> None:
        self._git(self.root, "clone", "-q", str(self.origin), str(self.clone))
        self._git(self.clone, "config", "commit.gpgsign", "true")
        self._git(self.clone, "config", "gpg.program", str(self.root / "missing-gpg"))
        (self.seed / "plain.txt").write_text("accepted change\n", encoding="utf-8")
        self._write_patch()
        self._assert_rejected("commit failed")

    def test_boundary_sized_patch_is_still_published(self) -> None:
        for number in range(40):
            lines = 2461 if number == 0 else 1
            (self.seed / f"file-{number}.txt").write_text("line\n" * lines, encoding="utf-8")
        self._write_patch()
        result = self._run()
        self.assertIn("40 files, 2500 lines", result.stdout)
        self.assertIn("could not open the PR", result.stdout)
        self._assert_clean()
        self.assertEqual(
            self._git(self.origin, "rev-parse", "refs/heads/task-34-test-clone-recovery"),
            self._git(self.clone, "rev-parse", "HEAD"),
        )
        self.assertEqual(
            self._git(self.origin, "rev-parse", "refs/heads/main"),
            self._git(self.seed, "rev-parse", "HEAD"),
        )
        self.assertIn(
            "\ngh pr create ", "\n" + (self.root / "calls.log").read_text(encoding="utf-8"),
        )

    def test_user_check_still_applies_with_the_test_override(self) -> None:
        (self.root / "wrong-user").touch()
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("must run as ha2n-coder", result.stderr)
        self.assertFalse(self.clone.exists())
        self.assertEqual((self.root / "calls.log").read_text(encoding="utf-8"), "id -un\n")

    def test_production_user_override_is_refused_before_path_changes(self) -> None:
        (self.root / "wrong-user").touch()
        # Sourcing lets a test-only function mock absolute id without a production seam.
        command = '/usr/bin/id() { printf "%s\\n" ha2n-coder; }; source "$1"'
        for value in (str(self.root), ""):
            with self.subTest(override=value):
                result = subprocess.run(
                    [self.bash, "-c", command, "guard-test", str(CODER_DIR / "run-task.sh")],
                    cwd=self.root,
                    env={**self.env, "HA2N_CODER_TEST_ROOT": value},
                    capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(
                    result.stderr, "test override refused for the production user\n",
                )
                self.assertEqual(result.stdout, "")
                self.assertFalse((self.root / "calls.log").exists())
                self.assertFalse(self.clone.exists())

    def test_identity_lookup_failure_refuses_the_override(self) -> None:
        result = subprocess.run(
            [
                self.bash, "-c", '/usr/bin/id() { return 1; }; source "$1"',
                "guard-test", str(CODER_DIR / "run-task.sh"),
            ],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "cannot determine user for test override\n")
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.root / "calls.log").exists())
        self.assertFalse(self.clone.exists())

    # ---- independent review (TASK-33): the whole pipeline against stubbed gh/copilot/sandbox ----

    BRANCH = "refs/heads/task-34-test-clone-recovery"

    def _pipeline(self, reviews=(), review_model: str | None = "review-model-x",
                  checks=(), task_status: str | None = None) -> None:
        """Set up a full run: an accepted change, working gh stub, scripted reviews and checks."""
        (self.seed / "plain.txt").write_text("accepted change\n", encoding="utf-8")
        if task_status is not None:
            (self.seed / "backlog").mkdir(exist_ok=True)
            (self.seed / "backlog/task-34.md").write_text(f"Status: {task_status}\n", encoding="utf-8")
        self._write_patch()
        (self.root / "gh-ok").touch()
        if review_model is not None:
            (self.root / "etc/ha2n-coder/review-model").write_text(review_model + "\n", encoding="utf-8")
        (self.root / "reviews").mkdir()
        for number, review in enumerate(reviews, 1):
            if isinstance(review, dict):
                review = {"criteria": [self._criterion()], **review}
            text = review if isinstance(review, str) else json.dumps(review)
            (self.root / "reviews" / f"{number}.json").write_text(text, encoding="utf-8")
        (self.root / "checks").mkdir()
        for number, bucket in enumerate(checks, 1):
            (self.root / "checks" / f"{number}.json").write_text(json.dumps([
                {"name": "e2e-pi", "bucket": bucket, "link": ""},
            ]), encoding="utf-8")

    def _run_pipeline(self, returncode: int) -> subprocess.CompletedProcess[str]:
        self.run_id = "20260101-000001-TASK-34"
        result = subprocess.run(
            [self.bash, str(CODER_DIR / "run-task.sh"), "--foreground", "TASK-34", "--run", self.run_id],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, returncode, result.stdout + result.stderr)
        return result

    def _status(self) -> dict[str, str]:
        text = (self.base / "runs" / self.run_id / "status").read_text(encoding="utf-8")
        return dict(line.split("=", 1) for line in text.splitlines())

    def _comments(self) -> list[str]:
        folder = self.root / "comments"
        files = sorted(folder.glob("*.md"), key=lambda path: int(path.stem)) if folder.exists() else []
        return [path.read_text(encoding="utf-8") for path in files]

    def _labels(self) -> list[str]:
        with (self.base / "cost.csv").open(newline="", encoding="utf-8") as handle:
            return [row["label"] for row in csv.DictReader(handle)]

    def _calls(self) -> str:
        return (self.root / "calls.log").read_text(encoding="utf-8")

    def _prompts(self, kind: str) -> list[str]:
        folder = self.root / "prompts"
        files = sorted(folder.glob(f"{kind}-*.md"), key=lambda path: int(path.stem.split("-")[1]))
        return [path.read_text(encoding="utf-8") for path in files]

    def _assert_closed(self, closed: bool, status: str = "Done", proven: tuple[int, ...] = (1,)) -> None:
        edits = [line for line in self._calls().splitlines() if line.startswith("backlog task edit TASK-34 ")]
        self.assertEqual(len(edits), int(closed), edits)
        if closed:
            self.assertIn(f"task edit TASK-34 -s {status} ", edits[0])
            self.assertEqual(re.findall(r"--check-ac (\d+)", edits[0]), [str(i) for i in proven])
        deleted = self.root / "deleted-branch-head"  # gh pr merge --delete-branch removed the remote branch
        ref = deleted.read_text() if deleted.exists() else self.BRANCH
        tree = self._git(self.origin, "ls-tree", "-r", "--name-only", ref)
        self.assertEqual("backlog/task-34.md" in tree.splitlines(), closed)
        if closed:
            text = self._git(self.origin, "show", f"{ref}:backlog/task-34.md")
            self.assertIn(f"Status: {status}\n", text)
            for i in proven:
                self.assertIn(f"- [x] #{i} ", text)

    @staticmethod
    def _criterion(cid: int = 1, status: str = "proven",
                   evidence: str = "Fixture unit test passed in the green local gates.") -> dict:
        return {"id": cid, "status": status, "evidence": evidence}

    @staticmethod
    def _finding(severity: str = "blocking", summary: str = "Criterion #2 has no test",
                 file: str | None = "custom_components/2n_intercom/api.py", line: int | None = 7) -> dict:
        return {"severity": severity, "file": file, "line": line, "summary": summary}

    def test_review_approve_closes_the_task(self) -> None:
        self._pipeline(reviews=[{"verdict": "approve", "findings": [self._finding("minor", "Rename a helper")]}])
        result = self._run_pipeline(0)
        status = self._status()
        self.assertEqual((status["state"], status["review"]), ("green", "approve"))
        self.assertIn("review approved (1 minor finding(s))", status["message"])
        self.assertEqual(self._labels(), ["implement", "review-1"])
        self.assertEqual(len(self._prompts("review")), 1)
        review_prompt = self._prompts("review")[0]
        self.assertIn("TASK-34", review_prompt)
        self.assertIn("git diff origin/main HEAD", review_prompt)
        for tag in ("[unit]", "[e2e]", "[tester]", "[jan]"):
            self.assertIn(tag, review_prompt)
        self.assertIn('"criteria":', review_prompt)
        comments = self._comments()
        self.assertEqual(len(comments), 2)
        self.assertIn("**Verdict: approve**", comments[0])
        self.assertIn("Rename a helper", comments[0])
        self.assertNotIn("credit", comments[0].lower())
        self.assertIn("Review: review approved", comments[1])
        self._assert_closed(True)
        self.assertIn("AC #1: Fixture unit test passed", self._git(
            self.origin, "show", f"{self.BRANCH}:backlog/task-34.md"))
        self.assertIn("review-model-x", (self.base / "cost.csv").read_text(encoding="utf-8"))
        self.assertIn("approve", result.stdout)

    def test_review_changes_then_fixed_by_one_review_fix_round(self) -> None:
        self._pipeline(reviews=[
            {"verdict": "changes", "findings": [
                self._finding("blocking", "Criterion #2 has no test"),
                self._finding("minor", "Rename a helper"),
            ]},
            {"verdict": "approve", "findings": []},
        ])
        self._run_pipeline(0)
        status = self._status()
        self.assertEqual((status["state"], status["review"], status["round"]), ("green", "approve", "1"))
        self.assertEqual(self._labels(), ["implement", "review-1", "review-fix-1", "review-2"])
        fix_prompt = self._prompts("coder")[-1]
        self.assertIn("Criterion #2 has no test", fix_prompt)
        self.assertIn("custom_components/2n_intercom/api.py:7", fix_prompt)
        self.assertNotIn("Rename a helper", fix_prompt)
        comments = self._comments()
        self.assertEqual(len(comments), 3)
        self.assertIn("changes requested", comments[0])
        self.assertIn("**Verdict: approve**", comments[1])
        self._assert_closed(True)
        calls = self._calls()
        self.assertLess(calls.index("task edit TASK-34"), calls.rindex("pr comment"))

    def test_review_changes_not_fixed_ends_in_review_state(self) -> None:
        blocking = {"verdict": "changes", "findings": [self._finding()]}
        self._pipeline(reviews=[blocking, blocking])
        self._run_pipeline(1)
        status = self._status()
        self.assertEqual((status["state"], status["review"]), ("review", "changes"))
        self.assertIn("changes requested (1 blocking, 0 minor)", status["message"])
        self.assertIn("task stays In Progress", status["message"])
        self.assertEqual(self._labels(), ["implement", "review-1", "review-fix-1", "review-2"])
        self.assertEqual(len(self._prompts("review")), 2)
        self.assertEqual(len(self._comments()), 2)
        self._assert_closed(False)

    def test_missing_review_model_skips_the_review(self) -> None:
        self._pipeline(review_model=None)
        self._run_pipeline(0)
        status = self._status()
        self.assertEqual((status["state"], status["review"]), ("green", "skipped"))
        self.assertIn("review skipped (no review-model configured)", status["message"])
        self.assertEqual(self._labels(), ["implement"])
        self.assertNotIn("--review", self._calls())
        comments = self._comments()
        self.assertEqual(len(comments), 1)
        self.assertIn("Review: review skipped", comments[0])
        self._assert_closed(True, "To Test", ())
        summary = self._git(self.origin, "show", f"{self.BRANCH}:backlog/task-34.md")
        self.assertIn("AC #1: No review-model configured; verification required. (unproven)", summary)

    def test_invalid_review_model_stops_before_any_work(self) -> None:
        self._pipeline(review_model="bad model;id")
        self._run_pipeline(1)
        status = self._status()
        self.assertEqual(status["state"], "stopped")
        self.assertIn("unreadable or invalid /etc/ha2n-coder/review-model", status["message"])
        self.assertNotIn("copilot", self._calls())

    def _assert_unusable_review(self, output: str) -> None:
        self._pipeline(reviews=[output])
        self._run_pipeline(1)
        status = self._status()
        self.assertEqual((status["state"], status["review"]), ("review", "failed"))
        self.assertIn("independent review failed", status["message"])
        self.assertEqual(self._labels(), ["implement", "review-1"])
        comments = self._comments()
        self.assertEqual(len(comments), 1)
        self.assertIn("Review failed", comments[0])
        self.assertNotIn("Verdict: approve", comments[0])
        self._assert_closed(False)

    def test_unparsable_review_output_is_failed_and_never_approve(self) -> None:
        self._assert_unusable_review("this is not json")

    def test_empty_review_output_is_failed(self) -> None:
        self._assert_unusable_review("")

    def test_review_json_without_findings_is_failed(self) -> None:
        self._assert_unusable_review(json.dumps({"verdict": "approve"}))

    def test_review_json_with_unknown_verdict_is_failed(self) -> None:
        self._assert_unusable_review(json.dumps({"verdict": "lgtm", "findings": []}))

    def test_review_json_with_invalid_finding_is_failed(self) -> None:
        self._assert_unusable_review(json.dumps(
            {"verdict": "approve", "findings": [{"severity": "huge", "summary": "x"}]},
        ))

    def test_review_json_with_malformed_criteria_is_failed(self) -> None:
        invalid = [
            None, {}, [], [self._criterion(2)], [self._criterion(), self._criterion()],
            [self._criterion(True)], [self._criterion("1")], [self._criterion(status="unknown")],
            [self._criterion(evidence=" \n\t")], [self._criterion(evidence=None)], [None],
            [{"id": 1, "status": "proven"}],
        ]
        for criteria in invalid:
            with self.subTest(criteria=criteria):
                self.setUp()
                self._assert_unusable_review(json.dumps({
                    "verdict": "approve", "findings": [], "criteria": criteria,
                }))

    def test_review_json_without_criteria_is_failed(self) -> None:
        self._assert_unusable_review(json.dumps({"verdict": "approve", "findings": []}))

    def test_review_must_cover_checked_and_unchecked_criteria(self) -> None:
        (self.root / "task-criteria").write_text("- [x] #1 Already checked\n- [ ] #2 Still pending\n")
        self._assert_unusable_review(json.dumps({
            "verdict": "approve", "findings": [], "criteria": [self._criterion(2)],
        }))

    def test_all_criteria_proven_sets_done_and_ticks_all(self) -> None:
        (self.root / "task-criteria").write_text("- [ ] #1 Unit behaviour [unit]\n- [ ] #2 E2E behaviour [e2e]\n")
        self._pipeline(reviews=[{"verdict": "approve", "findings": [], "criteria": [
            self._criterion(2, evidence="e2e-pi passed test_fixture_e2e on this head."),
            self._criterion(1, evidence="test_fixture_unit passed in local gates."),
        ]}])
        self._run_pipeline(0)
        self._assert_closed(True, proven=(1, 2))
        summary = self._git(self.origin, "show", f"{self.BRANCH}:backlog/task-34.md")
        self.assertIn("AC #1: test_fixture_unit passed in local gates. (proven)", summary)
        self.assertIn("AC #2: e2e-pi passed test_fixture_e2e on this head. (proven)", summary)
        self.assertEqual(self._git(self.origin, "rev-list", "--count", f"main..{self.BRANCH}").strip(), "2")

    def test_mixed_evidence_sets_to_test_and_ticks_only_proven(self) -> None:
        (self.root / "task-criteria").write_text(
            "- [ ] #1 Automated behaviour [unit]\n- [ ] #2 Device check [tester]\n"
            "- [ ] #3 Owner check [jan]\n- [ ] #4 Pending evidence\n")
        self._pipeline(reviews=[{"verdict": "approve", "findings": [], "criteria": [
            self._criterion(), self._criterion(2, "manual", "Tester must verify the device."),
            self._criterion(3, "manual", "Jan must verify the result."),
            self._criterion(4, "unproven", "No objective evidence yet."),
        ]}])
        self._run_pipeline(0)
        self._assert_closed(True, "To Test")
        summary = self._git(self.origin, "show", f"{self.BRANCH}:backlog/task-34.md")
        for cid in (2, 3, 4):
            self.assertIn(f"- [ ] #{cid} ", summary)
            self.assertIn(f"AC #{cid}:", summary)
        self.assertIn("AC #4: No objective evidence yet. (unproven)", summary)

    def test_unproven_automated_tags_block_even_an_approve_verdict(self) -> None:
        for tag, status in (("unit", "unproven"), ("e2e", "manual")):
            with self.subTest(tag=tag, status=status):
                self.setUp()
                (self.root / "task-criteria").write_text(f"- [ ] #1 Required proof [{tag}]\n")
                review = {"verdict": "approve", "findings": [], "criteria": [self._criterion(status=status)]}
                self._pipeline(reviews=[review, review])
                self._run_pipeline(1)
                self.assertEqual(self._status()["review"], "changes")
                self.assertIn(f"AC #1 [{tag}] lacks automated proof", self._comments()[0])
                self.assertIn("lacks automated proof", self._prompts("coder")[-1])
                self._assert_closed(False)

    def test_manual_tags_cannot_be_reported_as_proven(self) -> None:
        for tag in ("tester", "jan"):
            with self.subTest(tag=tag):
                self.setUp()
                (self.root / "task-criteria").write_text(f"- [ ] #1 Manual verification [{tag}]\n")
                self._assert_unusable_review(json.dumps({
                    "verdict": "approve", "findings": [], "criteria": [self._criterion()],
                }))

    def test_manual_close_sets_to_test_even_with_all_criteria_proven(self) -> None:
        (self.root / "task-labels").write_text("agent, manual-close\n")
        self._pipeline(reviews=[{"verdict": "approve", "findings": []}])
        self._run_pipeline(0)
        self._assert_closed(True, "To Test")

    def test_missing_reviewer_preserves_existing_ticks_without_adding_any(self) -> None:
        (self.root / "task-criteria").write_text("- [x] #1 Already checked\n- [ ] #2 Unchecked\n")
        self._pipeline(review_model=None)
        self._run_pipeline(0)
        self._assert_closed(True, "To Test", ())
        summary = self._git(self.origin, "show", f"{self.BRANCH}:backlog/task-34.md")
        self.assertIn("- [x] #1 Already checked", summary)
        self.assertIn("- [ ] #2 Unchecked", summary)
        self.assertIn("AC #1:", summary)
        self.assertIn("AC #2:", summary)

    def test_changed_criteria_do_not_receive_stale_evidence(self) -> None:
        (self.root / "task-close-criteria").write_text("- [ ] #1 Different behaviour [jan]\n")
        self._pipeline(reviews=[{"verdict": "approve", "findings": []}])
        self._run_pipeline(0)
        self._assert_closed(False)
        self.assertEqual(self._status()["state"], "green")
        self.assertIn("evidence could not be applied", self._status()["message"])
        log = (self.base / "runs" / self.run_id / "close.log").read_text()
        self.assertIn("Task criteria changed since the review", log)

    def test_finalization_failures_keep_the_run_green(self) -> None:
        for marker, reason in (
            ("backlog-edit-fails", "backlog edit failed"),
            ("backlog-edit-outside", "the edit touched files outside backlog/"),
        ):
            with self.subTest(marker=marker):
                self.setUp()
                (self.root / marker).touch()
                self._pipeline(reviews=[{"verdict": "approve", "findings": []}])
                self._run_pipeline(0)
                self.assertEqual(self._status()["state"], "green")
                self.assertIn(reason, self._status()["message"])
                tree = self._git(self.origin, "ls-tree", "-r", "--name-only", self.BRANCH)
                self.assertNotIn("backlog/task-34.md", tree.splitlines())
                self.assertNotIn("outside-backlog.txt", tree.splitlines())
                self.assertEqual(self._git(self.clone, "status", "--porcelain"), "")

    def test_manual_and_unproven_criteria_allow_empty_evidence(self) -> None:
        (self.root / "task-criteria").write_text("- [ ] #1 Manual [jan]\n- [ ] #2 Not yet verified\n")
        self._pipeline(reviews=[{"verdict": "approve", "findings": [], "criteria": [
            self._criterion(1, "manual", ""), self._criterion(2, "unproven", ""),
        ]}])
        self._run_pipeline(0)
        self._assert_closed(True, "To Test", ())
        summary = self._git(self.origin, "show", f"{self.BRANCH}:backlog/task-34.md")
        self.assertIn("AC #1: Manual verification required. (manual)", summary)
        self.assertIn("AC #2: No objective evidence supplied. (unproven)", summary)

    def test_done_or_to_test_task_is_left_unchanged(self) -> None:
        for status in ("Done", "To Test"):
            with self.subTest(status=status):
                self.setUp()
                self._pipeline(reviews=[{"verdict": "approve", "findings": []}], task_status=status)
                self._run_pipeline(0)
                self.assertNotIn("backlog task edit TASK-34 ", self._calls())
                self.assertEqual(self._git(self.origin, "show", f"{self.BRANCH}:backlog/task-34.md"),
                                 f"Status: {status}\n")
                self.assertEqual(self._git(self.origin, "rev-list", "--count", f"main..{self.BRANCH}").strip(), "1")

    def test_reviewer_exit_failure_is_failed_even_with_approve_json(self) -> None:
        self._pipeline(reviews=[{"verdict": "approve", "findings": []}])
        (self.root / "review-rc").write_text("7")
        self._run_pipeline(1)
        status = self._status()
        self.assertEqual((status["state"], status["review"]), ("review", "failed"))
        self.assertIn("exit code 7", self._comments()[0])
        self._assert_closed(False)

    def test_approve_with_a_blocking_finding_counts_as_changes(self) -> None:
        self._pipeline(reviews=[{"verdict": "approve", "findings": [self._finding()]}] * 2)
        self._run_pipeline(1)
        status = self._status()
        self.assertEqual((status["state"], status["review"]), ("review", "changes"))
        self.assertEqual(self._labels(), ["implement", "review-1", "review-fix-1", "review-2"])
        self._assert_closed(False)

    def test_changes_without_blocking_findings_get_no_fix_round(self) -> None:
        self._pipeline(reviews=[{"verdict": "changes", "findings": [self._finding("minor")]}])
        self._run_pipeline(1)
        status = self._status()
        self.assertEqual((status["state"], status["review"]), ("review", "changes"))
        self.assertEqual(self._labels(), ["implement", "review-1"])
        self.assertIn("a human decides", self._comments()[0])
        self._assert_closed(False)

    def test_review_comment_is_sanitised(self) -> None:
        token = "ghp_" + "a" * 30
        hostile = f"see https://evil.example/x?t={token} and ping @someone <b>now</b> [x](y) {token}"
        self._pipeline(reviews=[{"verdict": "approve", "findings": [self._finding("minor", hostile)],
                                 "criteria": [self._criterion(evidence=hostile)]}])
        self._run_pipeline(0)
        comment = self._comments()[0]
        summary = self._git(self.origin, "show", f"{self.BRANCH}:backlog/task-34.md")
        for leaked in ("evil.example", "ghp_", "@someone", "<b>", "](y"):
            self.assertNotIn(leaked, comment)
            self.assertNotIn(leaked, summary)
        self.assertIn("[link removed]", comment)

    def test_review_fix_round_does_not_use_up_the_ci_fix_rounds(self) -> None:
        blocking = {"verdict": "changes", "findings": [self._finding()]}
        self._pipeline(
            reviews=[blocking, {"verdict": "approve", "findings": []}],
            checks=("pass", "fail", "pass"),
        )
        self._run_pipeline(0)
        self.assertEqual(self._status()["state"], "green")
        self.assertEqual(
            self._labels(), ["implement", "review-1", "review-fix-1", "ci-fix-1", "review-2"],
        )
        self._assert_closed(True)

    def test_red_checks_never_reach_the_reviewer(self) -> None:
        self._pipeline(checks=("fail", "fail", "fail", "fail"))
        self._run_pipeline(1)
        self.assertEqual(self._status()["state"], "failed")
        self.assertEqual(self._labels(), ["implement", "ci-fix-1", "ci-fix-2", "ci-fix-3"])
        self.assertNotIn("--review", self._calls())
        self._assert_closed(False)

    def test_scripts_have_valid_bash_syntax(self) -> None:
        for script in sorted(CODER_DIR.glob("*.sh")):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [self.bash, "-n", str(script)], capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    # ---- autostart (TASK-35): ha2n-run-task --next, the entry point of the systemd timer ----

    MILESTONES = textwrap.dedent("""\
        Active milestones (2):
          m-0: v1.5.0 (10/18 done)
          m-1: v1.6.0 (0/4 done)
        Completed milestones (0):
          (none)
        """)

    def _autostart(self, max_runs: int = 10) -> None:
        # Copilot stops every run right after the ready check, so background runs end quickly.
        (self.root / "etc/ha2n-coder/autostart").touch()
        (self.root / "etc/ha2n-coder/max-runs-per-day").write_text(f"{max_runs}\n", encoding="utf-8")
        (self.root / "copilot-stop").touch()
        (self.root / "milestones.txt").write_text(self.MILESTONES, encoding="utf-8")

    # Output format of the stubbed backlog CLI: "line" = 1.48 ("Dependencies:" line, no --json),
    # "tree" = 1.53 --plain ("Depends on" tree, no --json), "json" = 1.53 with --json.
    backlog_format = "line"

    def _task(self, number: int, *, status: str = "To Do", priority: str = "High",
              assignee: str = "@copilot", labels: tuple[str, ...] = (),
              milestone: str | None = None, deps: tuple[int, ...] = ()) -> None:
        # The text as `backlog task view` prints it; the same file goes to the seed repo for last_run_blocks.
        title = f"Fixture task {number}"
        head = f"Task TASK-{number} - {title}"
        lines = [
            f"File: backlog/tasks/task-{number} - {title}.md", "", head, "=" * len(head), "",
            f"Status: {status}", f"Priority: {priority}", "Type: task", f"Assignee: {assignee}",
        ]
        if labels:
            lines.append("Labels: " + ", ".join(labels))
        if deps and self.backlog_format == "line":
            lines.append("Dependencies: " + ", ".join(f"TASK-{dep}" for dep in deps))
        if milestone:
            lines.append(f"Milestone: {milestone}")
        if deps and self.backlog_format != "line":
            # Indirect and dependent tasks have no fixture: reading them as direct dependencies would fail the task.
            lines += ["", "Dependency Graph:", "-" * 50, f"Depends on ({len(deps)} direct, {len(deps) + 1} total):"]
            for index, dep in enumerate(deps):
                lines.append(f"{'└─' if index == len(deps) - 1 else '├─'} TASK-{dep} - Fixture task {dep} [To Do]")
            lines += ["   └─ TASK-997 - Indirect dependency [To Do]", "",
                      "Dependents (1 direct, 1 total):", "└─ TASK-998 - Dependent task [To Do]"]
        lines += ["", "Description:", "Fixture.", "", "Acceptance Criteria:", "- [ ] #1 Fixture criterion"]
        text = "\n".join(lines) + "\n"
        (self.root / "tasks").mkdir(exist_ok=True)
        (self.root / "tasks" / f"TASK-{number}.txt").write_text(text, encoding="utf-8")
        if self.backlog_format == "json":
            (self.root / "backlog-json").touch()
            (self.root / "tasks" / f"TASK-{number}.json").write_text(json.dumps({
                "schemaVersion": 1, "kind": "task-view",
                "task": {"id": f"TASK-{number}", "title": title, "status": status,
                         "dependencies": [f"TASK-{dep}" for dep in deps]},
            }), encoding="utf-8")
        (self.seed / "backlog/tasks").mkdir(parents=True, exist_ok=True)
        (self.seed / "backlog/tasks" / f"task-{number} - {title}.md").write_text(text, encoding="utf-8")

    def _next(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.bash, str(CODER_DIR / "run-task.sh"), "--next"],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=60,
        )

    def _started(self, result: subprocess.CompletedProcess[str]) -> str:
        match = re.search(r"^started (\S+) ", result.stdout, re.M)
        self.assertIsNotNone(match, result.stdout + result.stderr)
        return match.group(1)

    def _runs(self) -> list[str]:
        return sorted(
            path.name for path in (self.base / "runs").iterdir()
            if path.is_dir() and not path.is_symlink()
        )

    def _parse_status(self, path: Path) -> dict[str, str]:
        return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines())

    def _wait_idle(self, timeout: float = 60) -> None:
        # A background run holds the run lock until its process exits.
        deadline = time.monotonic() + timeout
        with (self.base / "run.lock").open("a") as handle:
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        self.fail("a background run still holds the run lock")
                    time.sleep(0.2)

    def _wait_run(self, run: str, timeout: float = 60) -> dict[str, str]:
        path = self.base / "runs" / run / "status"
        deadline = time.monotonic() + timeout
        while True:
            status = self._parse_status(path) if path.exists() else {}
            if status.get("state", "running") != "running":
                break
            if time.monotonic() > deadline:
                self.fail(f"run {run} did not finish")
            time.sleep(0.2)
        self._wait_idle(timeout)
        return status

    def _drain(self) -> list[str]:
        # Call --next until it starts nothing; return the tasks it started, in order.
        started: list[str] = []
        for _ in range(10):
            result = self._next()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if re.search(r"^started ", result.stdout, re.M) is None:
                self.assertEqual(result.stdout, "")
                return started
            status = self._wait_run(self._started(result))
            self.assertEqual(status["state"], "stopped", status)
            started.append(status["task"])
        self.fail("--next kept starting tasks")

    def test_next_starts_one_ready_task_and_records_it(self) -> None:
        self._autostart()
        self._task(2)
        self._commit_main("Add a ready task")
        result = self._next()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run = self._started(result)
        status = self._wait_run(run)
        self.assertEqual(status["task"], "TASK-2")
        self.assertRegex(status["started"], r"^\d+$")
        self.assertIn("Copilot stopped", status["message"])
        self.assertTrue((self.base / "runs" / run / "next.marker").exists())

    def test_next_without_autostart_file_does_nothing(self) -> None:
        self._task(2)
        self._commit_main("Add a ready task")
        result = self._next()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertEqual(self._runs(), [])
        calls = (self.root / "calls.log").read_text(encoding="utf-8").splitlines() if (self.root / "calls.log").exists() else []
        self.assertTrue(set(calls) <= {"id -un", "getent passwd ha2n-coder"}, calls)

    def test_next_rejects_extra_arguments(self) -> None:
        result = subprocess.run(
            [self.bash, str(CODER_DIR / "run-task.sh"), "--next", "TASK-2"],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("usage: ha2n-run-task --next", result.stderr)

    def test_next_without_ready_tasks_does_nothing(self) -> None:
        self._autostart()
        self._task(2, status="In Progress")
        self._commit_main("Add a task that is not ready")
        result = self._next()
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        self.assertEqual(self._runs(), [])

    def test_next_daily_limit_counts_only_autostarted_runs(self) -> None:
        self._autostart(max_runs=1)
        manual = self.base / "runs/20250101-000000-TASK-98"
        manual.mkdir()
        (manual / "status").write_text("task=TASK-98\nstarted=1\nstate=stopped\n", encoding="utf-8")
        self._task(2)
        self._commit_main("Add a ready task")
        self._wait_run(self._started(self._next()))
        blocked = self._next()
        self.assertEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        self.assertIn("daily limit reached: 1 autostarted runs in the last 24 h (max 1)", blocked.stdout)
        self.assertEqual(len(self._runs()), 2)

    def test_next_does_not_start_while_a_task_runs(self) -> None:
        self._autostart()
        self._task(2)
        self._commit_main("Add a ready task")
        with (self.base / "run.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            busy = self._next()
        self.assertEqual(busy.returncode, 0, busy.stdout + busy.stderr)
        self.assertIn("a task is running; not starting another", busy.stdout)
        self.assertEqual(self._runs(), [])
        self.assertEqual(self._drain(), ["TASK-2"])

    def test_next_skips_on_hold_manual_path_and_other_assignees(self) -> None:
        self._autostart()
        self._task(20, labels=("agent", "on-hold"))
        self._task(21, labels=("agent", "manual-path"))
        self._task(22, assignee="@copilot-mac")
        self._task(23, status="In Progress")
        self._task(24, deps=(31,))
        self._task(31, status="In Progress")
        self._task(40, status="Done")
        self._task(25)
        self._task(26, deps=(40,))
        self._task(27, labels=("not-on-hold",))
        self._commit_main("Add fixture tasks")
        self.assertEqual(self._drain(), ["TASK-25", "TASK-26", "TASK-27"])

    def test_next_orders_by_milestone_then_priority_then_id(self) -> None:
        self._autostart()
        self._task(10, milestone="m-1")
        self._task(11, priority="Low", milestone="m-0")
        self._task(12)
        self._task(17, milestone="m-0")
        self._commit_main("Add fixture tasks")
        self.assertEqual(self._drain(), ["TASK-17", "TASK-11", "TASK-10", "TASK-12"])

    def test_stopped_task_waits_for_its_file_to_change_on_main(self) -> None:
        self._autostart()
        self._task(2)
        self._commit_main("Add a ready task")
        status = self._wait_run(self._started(self._next()))
        self.assertEqual(status["state"], "stopped")
        started = int(status["started"])

        self.assertEqual(self._drain(), [])
        (self.seed / "backlog/tasks/task-2 - Fixture task 2.md").write_text("Edited on main\n", encoding="utf-8")
        self._commit_main("Update the task on main", committed_at=started + 1)
        time.sleep(1.1)   # run directories are named by second
        self.assertEqual(self._drain(), ["TASK-2"])

    def test_run_without_started_field_uses_the_run_id_time(self) -> None:
        # Runs made before status had started= must not keep their task off forever.
        self._autostart()
        added = int(time.time()) - 3600
        self._task(2)
        self._commit_main("Add a ready task", committed_at=added)
        legacy = self.base / "runs" / (time.strftime("%Y%m%d-%H%M%S", time.localtime(added + 600)) + "-TASK-2")
        legacy.mkdir()
        (legacy / "status").write_text("task=TASK-2\nstate=failed\nmessage=old run\n", encoding="utf-8")

        self.assertEqual(self._drain(), [])
        (self.seed / "backlog/tasks/task-2 - Fixture task 2.md").write_text("Edited on main\n", encoding="utf-8")
        self._commit_main("Update the task on main", committed_at=added + 1200)
        self.assertEqual(self._drain(), ["TASK-2"])

    def _manual(self, number: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.bash, str(CODER_DIR / "run-task.sh"), "--foreground", f"TASK-{number}",
             "--run", f"20260101-000001-TASK-{number}"],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20,
        )

    def _unfinished_dependency_case(self, backlog_format: str) -> None:
        # TASK-42-like: depends on a task that is not Done yet; skipped by --next, refused by a manual start.
        self.backlog_format = backlog_format
        self._autostart()
        self._task(41, status="In Progress")
        self._task(42, deps=(41,))
        self._task(40, status="Done")
        self._task(43, deps=(40,))
        self._commit_main("Add fixture tasks")
        self.assertEqual(self._drain(), ["TASK-43"])
        result = self._manual(42)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("task has dependencies that are not done", result.stdout)

    def test_unfinished_dependency_with_dependencies_line(self) -> None:
        self._unfinished_dependency_case("line")

    def test_unfinished_dependency_with_depends_on_tree(self) -> None:
        self._unfinished_dependency_case("tree")

    def test_unfinished_dependency_with_json(self) -> None:
        self._unfinished_dependency_case("json")
        self.assertIn("backlog task view TASK-42 --json", self._calls())

    def test_ready_check_stop_does_not_block_the_task(self) -> None:
        # The task becomes ready through its dependency's file, its own file does not change.
        self._autostart()
        self._task(31, status="In Progress")
        self._task(5, deps=(31,))
        self._commit_main("Add fixture tasks")
        refused = self._manual(5)
        self.assertIn("task has dependencies that are not done", refused.stdout)
        self.assertIn("branch=\n", (self.base / "runs/20260101-000001-TASK-5/status").read_text(encoding="utf-8"))
        self.assertEqual(self._drain(), [])
        self._task(31, status="Done")
        self._commit_main("Finish the dependency")
        self.assertEqual(self._drain(), ["TASK-5"])


    # ---- auto-merge (TASK-46): an approved green PR merges itself and triggers --next once ----

    def _automerge(self, *, autostart: bool = False, labels: str | None = None, **pipeline) -> None:
        pipeline.setdefault("reviews", [{"verdict": "approve", "findings": []}])
        self._pipeline(**pipeline)
        (self.root / "etc/ha2n-coder/automerge").touch()
        if labels is not None:
            (self.root / "task-labels").write_text(labels + "\n", encoding="utf-8")
        if autostart:
            (self.root / "etc/ha2n-coder/autostart").touch()
            (self.root / "etc/ha2n-coder/max-runs-per-day").write_text("10\n", encoding="utf-8")
            (self.root / "milestones.txt").write_text(self.MILESTONES, encoding="utf-8")

    def _branch_head(self) -> str:
        deleted = self.root / "deleted-branch-head"
        if deleted.exists():  # gh pr merge --delete-branch removed the remote branch
            return deleted.read_text()
        return self._git(self.origin, "rev-parse", self.BRANCH).strip()

    def _remote_branch_exists(self) -> bool:
        refs = self._git(self.origin, "for-each-ref", "--format=%(refname)", "refs/heads/")
        return self.BRANCH in refs.split()

    def _merge_calls(self) -> list[str]:
        return [line for line in self._calls().splitlines() if line.startswith("gh pr merge ")]

    def _assert_not_merged(self, reason: str) -> dict[str, str]:
        status = self._status()
        self.assertEqual(status["state"], "green", status)
        self.assertIn(f"not merged automatically: {reason}", status["message"])
        self.assertEqual(status["next"], "")
        self.assertFalse((self.root / "merged").exists())
        self.assertTrue(self._remote_branch_exists(), "an unmerged PR keeps its branch")
        self.assertIn(f"not merged automatically: {reason}", self._comments()[-1])
        self.assertFalse((self.base / "runs" / self.run_id / "next.log").exists())
        return status

    def test_automerge_off_keeps_the_pr_for_jan(self) -> None:
        self._pipeline(reviews=[{"verdict": "approve", "findings": []}])
        (self.root / "etc/ha2n-coder/autostart").touch()
        self._run_pipeline(0)
        status = self._status()
        self.assertEqual(status["state"], "green")
        self.assertNotIn("PR merged", status["message"])
        self.assertNotIn("not merged automatically", status["message"])
        self.assertEqual(status["next"], "")
        self.assertEqual(self._merge_calls(), [])
        self.assertIn("the coder never merges", self._comments()[-1])
        self.assertEqual(self._runs(), [self.run_id])

    def test_automerge_merges_the_checked_head_and_starts_next(self) -> None:
        self._automerge(autostart=True)
        self._task(2)
        self._commit_main("Add the next ready task")
        (self.root / "copilot-stop-TASK-2").touch()
        self._run_pipeline(0)
        status = self._status()
        self.assertEqual(status["state"], "merged", status)
        self.assertIn("PR merged: https://github.com/mastalir1980/ha-2N-intercom/pull/99", status["message"])
        self.assertIn("next: started ", status["message"])
        self._assert_closed(True)
        # The close commit is a new head: checks ran again on it, and exactly that head was merged.
        self.assertEqual((self.root / "checks-count").read_text(), "2")
        self.assertEqual(self._merge_calls(), [
            "gh pr merge https://github.com/mastalir1980/ha-2N-intercom/pull/99 -R mastalir1980/ha-2N-intercom "
            f"--merge --match-head-commit {self._branch_head()} --delete-branch",
        ])
        self.assertFalse(self._remote_branch_exists(), "merged branch must be deleted on the remote")
        self.assertIn("Merged by the coder (auto-merge)", self._comments()[-1])
        next_run = status["next"]
        self.assertRegex(next_run, r"^\d{8}-\d{6}-TASK-2$")
        self.assertTrue((self.base / "runs" / next_run / "next.marker").exists())
        self.assertEqual(self._wait_run(next_run)["state"], "stopped")
        self.assertEqual(len(self._runs()), 2)

    def test_automerge_with_autostart_off_does_not_start_next(self) -> None:
        self._automerge()
        self._task(2)
        self._commit_main("Add a ready task")
        self._run_pipeline(0)
        status = self._status()
        self.assertEqual(status["state"], "merged")
        self.assertIn("next task not started (autostart is off)", status["message"])
        self.assertEqual(status["next"], "")
        self.assertEqual(self._runs(), [self.run_id])

    def test_automerge_next_keeps_the_daily_limit(self) -> None:
        self._automerge(autostart=True)
        (self.root / "etc/ha2n-coder/max-runs-per-day").write_text("0\n", encoding="utf-8")
        self._task(2)
        self._commit_main("Add a ready task")
        self._run_pipeline(0)
        status = self._status()
        self.assertEqual(status["state"], "merged")
        self.assertIn("next task not started: daily limit reached", status["message"])
        self.assertEqual(self._runs(), [self.run_id])

    def test_automerge_without_review_model_never_merges(self) -> None:
        self._automerge(review_model=None)
        self._run_pipeline(0)
        self._assert_not_merged("no approved second-model review")
        self._assert_closed(True, "To Test", ())

    def test_automerge_never_merges_requested_changes(self) -> None:
        blocking = {"verdict": "changes", "findings": [self._finding()]}
        self._automerge(reviews=[blocking, blocking])
        self._run_pipeline(1)
        self.assertEqual(self._status()["state"], "review")
        self.assertEqual(self._merge_calls(), [])

    def test_automerge_never_merges_release_or_manual_path_tasks(self) -> None:
        for label in ("release", "manual-path"):
            with self.subTest(label=label):
                self.setUp()
                self._automerge(labels=f"agent, {label}")
                self._run_pipeline(0)
                self._assert_not_merged(f"task has the label {label}")
                self.assertEqual(self._merge_calls(), [])

    def test_automerge_merges_manual_close_after_to_test_commit_checks(self) -> None:
        self._automerge(labels="agent, manual-close")
        self._run_pipeline(0)
        status = self._status()
        self.assertEqual(status["state"], "merged", status)
        self.assertIn("task set to To Test", status["message"])
        self._assert_closed(True, "To Test")
        self.assertEqual((self.root / "checks-count").read_text(), "2")
        self.assertEqual(len(self._merge_calls()), 1)
        self.assertIn(f"--match-head-commit {self._branch_head()}", self._merge_calls()[0])

    def test_automerge_refuses_a_changed_head(self) -> None:
        self._automerge()
        (self.root / "head-moved").touch()
        self._run_pipeline(0)
        self._assert_not_merged("GitHub refused the merge: GraphQL: Head branch was modified")
        self.assertEqual(len(self._merge_calls()), 1)   # no retry

    def test_automerge_refusal_keeps_green_without_retry(self) -> None:
        self._automerge(autostart=True)
        (self.root / "merge-refuse").write_text("X Pull request is not mergeable: the merge commit cannot be cleanly created.\n")
        self._run_pipeline(0)
        self._assert_not_merged("GitHub refused the merge: X Pull request is not mergeable")
        self.assertEqual(len(self._merge_calls()), 1)
        self.assertEqual(self._runs(), [self.run_id])

    def test_automerge_waits_for_red_checks_on_the_close_commit(self) -> None:
        self._automerge(checks=("pass", "fail"))
        self._run_pipeline(0)
        status = self._assert_not_merged("checks on ")
        self.assertIn("are not green: e2e-pi fail", status["message"])
        self.assertEqual(self._merge_calls(), [])

    def test_automerge_never_merges_protected_paths(self) -> None:
        # publish() already stops such a patch; this checks auto_merge's own guard in isolation.
        script = (CODER_DIR / "run-task.sh").read_text(encoding="utf-8")
        protected = re.search(r"^PROTECTED=.*$", script, re.M).group(0)
        function = re.search(r"^auto_merge\(\) \{.*?^\}$", script, re.M | re.S).group(0)
        repo = self.root / "work"
        self._git(self.root, "clone", "-q", str(self.origin), str(repo))
        self._git(repo, "checkout", "-q", "-b", "task-1")
        for path in ("tools/coder/run-task.sh", ".github/copilot-instructions.md", "backlog/config.yml",
                     "CLAUDE.md", "e2e/ci/x.sh"):
            with self.subTest(path=path):
                self._git(repo, "reset", "-q", "--hard", "origin/main")
                (repo / path).parent.mkdir(parents=True, exist_ok=True)
                (repo / path).write_text("change\n", encoding="utf-8")
                self._git(repo, "add", "-A")
                self._git(repo, "commit", "-qm", "change")
                harness = "\n".join([
                    protected, function,
                    'status() { :; }; ghx() { echo "ghx $*"; }; wait_checks() { echo wait; }',
                    'DIR="$1"; HEADER="Labels: agent"; REVIEW_ON=1; REVIEW_VERDICT=approve',
                    'CHECKED_HEAD="$(git rev-parse HEAD)"; PR_URL=x; REPO=y',
                    'auto_merge; echo "merged=$MERGED"; echo "note=$MERGE_NOTE"',
                ])
                result = subprocess.run(
                    [self.bash, "-c", harness, "harness", str(self.root)],
                    cwd=repo, env=self.env, capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("merged=0", result.stdout)
                self.assertIn(f"note=the PR touches protected paths: {path}", result.stdout)
                self.assertNotIn("ghx", result.stdout)
                self.assertNotIn("wait", result.stdout)

if __name__ == "__main__":
    unittest.main()
