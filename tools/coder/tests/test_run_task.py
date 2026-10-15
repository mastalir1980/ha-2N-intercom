"""Hermetic regressions for the headless coder's owned-clone lifecycle."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


CODER_DIR = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/mastalir1980/ha-2N-intercom.git"

STUB = """\
import json
import os
from pathlib import Path
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
elif name == "backlog" and args == ["task", "view", "TASK-34", "--plain"]:
    print("Task TASK-34 - Test clone recovery")
    print("Status: To Do")
    print("Assignee: @copilot")
    print("Description:")
    print("Hermetic fixture")
    print("Acceptance Criteria:")
    print("- [ ] #1 Fixture criterion")
elif name == "backlog" and args[:3] == ["task", "edit", "TASK-34"]:
    Path("backlog").mkdir(exist_ok=True)
    Path("backlog/task-34.md").write_text("Status: Done\\n")
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
    if "TASK-34" not in prompt:
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
    if (root / "copilot-stop").exists():
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

    def _git(self, cwd: Path, *args: str) -> str:
        result = subprocess.run(
            [self.git, *args], cwd=cwd, env=self.env,
            check=True, capture_output=True, text=True, timeout=15,
        )
        return result.stdout

    def _commit_main(self, message: str) -> None:
        self._git(self.seed, "add", "-A")
        self._git(self.seed, "commit", "-q", "-m", message)
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
                  checks=()) -> None:
        """Set up a full run: an accepted change, working gh stub, scripted reviews and checks."""
        (self.seed / "plain.txt").write_text("accepted change\n", encoding="utf-8")
        self._write_patch()
        (self.root / "gh-ok").touch()
        if review_model is not None:
            (self.root / "etc/ha2n-coder/review-model").write_text(review_model + "\n", encoding="utf-8")
        (self.root / "reviews").mkdir()
        for number, review in enumerate(reviews, 1):
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

    def _assert_closed(self, closed: bool) -> None:
        self.assertEqual("task edit TASK-34 -s Done --check-ac 1" in self._calls(), closed)
        tree = self._git(self.origin, "ls-tree", "-r", "--name-only", self.BRANCH)
        self.assertEqual("backlog/task-34.md" in tree.splitlines(), closed)

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
        comments = self._comments()
        self.assertEqual(len(comments), 2)
        self.assertIn("**Verdict: approve**", comments[0])
        self.assertIn("Rename a helper", comments[0])
        self.assertNotIn("credit", comments[0].lower())
        self.assertIn("Review: review approved", comments[1])
        self._assert_closed(True)
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
        self._assert_closed(True)

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
        self._pipeline(reviews=[{"verdict": "approve", "findings": [self._finding("minor", hostile)]}])
        self._run_pipeline(0)
        comment = self._comments()[0]
        for leaked in ("evil.example", "ghp_", "@someone", "<b>", "](y"):
            self.assertNotIn(leaked, comment)
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


if __name__ == "__main__":
    unittest.main()
