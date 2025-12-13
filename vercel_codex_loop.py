import subprocess
import time
from pathlib import Path
import os
import shutil
from dotenv import load_dotenv
from pathlib import Path
import json

load_dotenv()  # Loads .env from repo root
# =========================
# CONFIGURATION
# =========================

REPO_PATH = Path(os.getenv("REPO_PATH")).resolve()
PROD_URL = os.getenv("PROD_URL")

GIT_REMOTE = os.getenv("GIT_REMOTE", "origin")
GIT_BRANCH = os.getenv("GIT_BRANCH", "main")

VERCEL_TOKEN = os.getenv("VERCEL_TOKEN")

# Convert command string to a list
CODEX_CMD = os.getenv("CODEX_CMD", "echo NO_CHANGES").split()

MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", 10))
SLEEP_AFTER_PUSH_SECONDS = int(os.getenv("SLEEP_AFTER_PUSH_SECONDS", 90))
VERCEL_TEAM_ID = os.getenv("VERCEL_TEAM_ID", "")

# =========================
# HELPER FUNCTIONS
# =========================

import json  # you can keep this import if already there, it's harmless


def git_workdir_has_changes() -> bool:
    """
    Return True if there are unstaged or staged changes in the repo.
    """
    # unstaged
    result = subprocess.run(
        ["git", "diff", "--quiet"],
        cwd=REPO_PATH,
        text=True,
    )
    if result.returncode != 0:
        return True

    # staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=REPO_PATH,
        text=True,
    )
    return result.returncode != 0


def run(cmd, cwd=None, input_text=None, check=True, env=None):
    """
    Run a shell command and return stdout as text.
    Raises RuntimeError on non-zero exit code if check=True.
    """
    result = subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
    return result.stdout, result.stderr, result.returncode


def fetch_latest_build_logs() -> str:
    """Fetch logs for the deployment that corresponds to the current HEAD commit."""
    print("\n[step] Fetching Vercel build logs for current commit...")

    env = os.environ.copy()
    if VERCEL_TOKEN:
        env["VERCEL_AUTH_TOKEN"] = VERCEL_TOKEN
    if VERCEL_TEAM_ID:
        env["VERCEL_TEAM_ID"] = VERCEL_TEAM_ID

    dep_id = get_deployment_id_for_current_commit()
    if not dep_id:
        print("[warn] Could not find a deployment for the current commit.")
        return ""

    print(f"[info] Inspecting deployment {dep_id} ...")
    cmd = ["vercel", "inspect", dep_id, "--logs", "--wait"]

    stdout, stderr, _ = run(cmd, cwd=REPO_PATH, check=False, env=env)
    logs = stdout if stdout.strip() else stderr
    if not logs.strip():
        print("[warn] No logs returned from Vercel for this deployment.")
        return ""

    print("[info] Log snippet:")
    print("\n".join(logs.splitlines()[-15:]))
    return logs


def get_current_commit_hash(short: bool = True) -> str:
    """Return the current HEAD commit hash (short or full)."""
    if short:
        cmd = ["git", "rev-parse", "--short=7", "HEAD"]
    else:
        cmd = ["git", "rev-parse", "HEAD"]
    stdout, _, _ = run(cmd, cwd=REPO_PATH, check=True)
    return stdout.strip()


def get_deployment_id_for_current_commit() -> str | None:
    """
    Find the Vercel deployment whose commit hash matches the current HEAD.

    Works with older Vercel CLI (no --json, no --limit):

    - Run `vercel list` in the linked project dir (uses .vercel/project.json).
    - Parse deployment IDs from the first column of the table.
    - For each ID, run `vercel inspect <id>` and search for the short commit hash.
    """

    commit_short = get_current_commit_hash(short=True)
    print(f"[info] Looking for deployment of commit {commit_short}...")

    env = os.environ.copy()
    if VERCEL_TOKEN:
        env["VERCEL_AUTH_TOKEN"] = VERCEL_TOKEN
    if VERCEL_TEAM_ID:
        env["VERCEL_TEAM_ID"] = VERCEL_TEAM_ID

    # 1) Get deployments in plain-text table form
    cmd = ["vercel", "list"]  # no --json, no --limit
    stdout, stderr, rc = run(cmd, cwd=REPO_PATH, check=False, env=env)

    if rc != 0 or not stdout.strip():
        print("[warn] `vercel list` failed or returned no data.")
        if stderr.strip():
            print("[vercel list stderr]")
            print(stderr)
        return None

    # 2) Parse deployment IDs / URLs from each non-header line.
    # Newer Vercel CLI prints the deployment URL as the first column (no raw IDs).
    dep_ids: list[str] = []
    for line in stdout.splitlines():
        raw = line.rstrip()
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("Vercel CLI"):
            continue
        # Skip obvious headers / separators
        lower = stripped.lower()
        if lower.startswith("age ") or lower.startswith("deployment") or lower.startswith("id "):
            continue
        if set(stripped) <= {"─", "━", " ", "┌", "└", "┼", "│", "┐", "┘"}:
            continue

        parts = stripped.split()
        if not parts:
            continue

        dep_id = parts[0]
        is_url = ".vercel.app" in dep_id or dep_id.startswith("https://")
        is_raw_id = (
            dep_id.startswith("dpl_")
            or (dep_id.isalnum() and len(dep_id) >= 8 and any(ch.isdigit() for ch in dep_id))
        )
        if is_url or is_raw_id:
            dep_ids.append(dep_id)

    if not dep_ids:
        print("[warn] Could not parse any deployment IDs from `vercel list`.")
        return None

    print(f"[info] Parsed {len(dep_ids)} deployment candidates from `vercel list`.")

    # 3) For each candidate deployment, inspect it (with logs) and look for the commit hash
    for dep_id in dep_ids:
        print(f"[debug] Inspecting deployment {dep_id} for commit {commit_short}...")
        insp_out, insp_err, _ = run(
            ["vercel", "inspect", dep_id, "--logs"],
            cwd=REPO_PATH,
            check=False,
            env=env,
        )
        combined = f"{insp_out}\n{insp_err}"
        if commit_short in combined:
            print(f"[info] Matched commit {commit_short} to deployment {dep_id}")
            return dep_id

    print(f"[warn] No deployment found for commit {commit_short} in {len(dep_ids)} candidates.")
    return None

def build_looks_successful(logs: str) -> bool:
    """
    Naive heuristic to decide whether the build is 'clean enough'.
    Adjust this to match your project’s real success markers.
    """
    text = logs.lower()

    # Typical failure hints
    possible_failure_markers = [
        "error ",
        "failed",
        "build failed",
        "exit code 1",
        "command \"npm run build\" exited with 1",
    ]
    if any(marker in text for marker in possible_failure_markers):
        return False

    # Some positive indicators – you can tune these
    possible_success_markers = [
        "deployment completed",
        "build completed",
        "ready! deployed to",
    ]
    return any(marker in text for marker in possible_success_markers)


def run_codex_on_logs(logs: str) -> bool:
    """
    Send logs to Codex via stdin. Returns:
      True  -> Codex did apply changes (or thinks it did)
      False -> Codex says 'no changes' or exit code indicates nothing done

    You *must* adapt this to however your local Codex tool behaves.
    """
    print("\n[step] Running Codex with latest build logs...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    def run_once(cmd: list[str], label: str):
        print(f"[debug] Running Codex command ({label}): {' '.join(cmd)}")
        return run(
            cmd,
            cwd=REPO_PATH,
            input_text=logs,
            check=False,  # we handle non-zero ourselves
            env=env,
        )

    stdout, stderr, returncode = run_once(CODEX_CMD, "plain")

    print("[codex stdout]")
    print(stdout)
    if stderr.strip():
        print("\n[codex stderr]")
        print(stderr)

    combined = (stdout + stderr).lower()
    if returncode != 0 and "stdin is not a terminal" in combined:
        if shutil.which("script"):
            print("[info] Codex requires a TTY; retrying via `script` to provide a pseudo-tty...")
            wrapped_cmd = ["script", "-q", "/dev/null"] + CODEX_CMD
            stdout, stderr, returncode = run_once(wrapped_cmd, "pty")
            print("[codex stdout]")
            print(stdout)
            if stderr.strip():
                print("\n[codex stderr]")
                print(stderr)
            combined = (stdout + stderr).lower()
        else:
            print("[warn] Codex requires a TTY but `script` is not available. Skipping Codex run.")
            return False

    # Example convention: Codex prints "NO_CHANGES" if everything is fine
    if "NO_CHANGES" in stdout.upper():
        print("[info] Codex reports no changes needed.")
        return False

    if returncode != 0:
        print(f"[warn] Codex exited with non-zero code ({returncode}). "
              f"Treating as 'no further changes'.")
        return False

    print("[info] Codex appears to have made changes.")
    return True


def git_commit_and_push() -> bool:
    """
    git add/commit/push. Returns True if something was pushed, False if nothing changed.
    """
    print("\n[step] Git add/commit/push...")

    # Stage everything
    run(["git", "add", "-A"], cwd=REPO_PATH)

    # Commit; if nothing to commit, git will exit non-zero
    commit_msg = "chore: auto-fix by codex based on Vercel build logs"
    stdout, stderr, returncode = run(
        ["git", "commit", "-m", commit_msg],
        cwd=REPO_PATH,
        check=False,
    )

    if returncode != 0:
        if "nothing to commit" in stdout.lower() or "nothing to commit" in stderr.lower():
            print("[info] Nothing to commit. Skipping push.")
            return False
        raise RuntimeError(
            f"git commit failed unexpectedly:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )

    print("[info] Commit created:")
    print(stdout)

    # Push
    stdout, stderr, returncode = run(
        ["git", "push", GIT_REMOTE, GIT_BRANCH],
        cwd=REPO_PATH,
        check=False,
    )
    if returncode != 0:
        raise RuntimeError(
            f"git push failed:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )

    print("[info] git push completed.")
    return True

def apply_codex_fixes(logs: str) -> bool:
    """
    Use Codex CLI (`codex exec`) to try to fix the build based on Vercel logs.

    Strategy:
    - Build a task message that includes the logs.
    - Run `codex exec` with --full-auto and a sandbox mode that allows file edits.
    - Compare git diff before/after to see if any files changed.
    """
    print("\n[step] Running Codex (codex exec) to apply fixes...")

    if not logs.strip():
        print("[info] No logs provided to Codex. Skipping.")
        return False

    # Check if there were already changes before Codex runs
    had_changes_before = git_workdir_has_changes()

    # Build the task string for Codex CLI
    task = (
        "You are Codex running in a CI autofix loop for a Vercel deployment.\n\n"
        "The build or deployment has failed. Your goal:\n"
        "1. Read the build logs.\n"
        "2. Identify the root cause of the failure.\n"
        "3. Modify files in this Git repository to fix the issue.\n"
        "4. DO NOT commit; just edit files. A separate step will commit and push.\n\n"
        "Here are the Vercel logs:\n\n"
        f"{logs}\n"
    )

    # Environment for Codex; it can reuse OpenAI CLI auth or you can set CODEX_API_KEY
    env = os.environ.copy()
    # Example: if you want to override per-run, set CODEX_API_KEY in .env
    # env["CODEX_API_KEY"] = os.getenv("CODEX_API_KEY", env.get("CODEX_API_KEY", ""))

    cmd = [
        "codex",
        "exec",
        "--full-auto",                 # allow Codex to edit files
        "--sandbox",
        "workspace-write",             # allow writes inside repo, but no arbitrary network
        task,
    ]

    stdout, stderr, returncode = run(cmd, cwd=REPO_PATH, check=False, env=env)

    # Stream Codex info for debugging
    print("\n[codex stdout - final message]")
    print(stdout)
    if stderr.strip():
        print("\n[codex stderr - activity log]")
        print(stderr)

    if returncode != 0:
        print(f"[warn] Codex exited with non-zero status ({returncode}). "
              f"Treating as 'no changes'.")
        return False

    # Check if Codex actually changed anything
    has_changes_after = git_workdir_has_changes()

    if not has_changes_after and not had_changes_before:
        print("[info] Codex made no file changes.")
        return False

    print("[info] Codex appears to have modified the repo.")
    return True

# =========================
# MAIN LOOP
# =========================

def main():
    print("[start] Vercel ↔ Codex auto-fix loop")
    print(f"Repo:   {REPO_PATH}")
    print(f"Branch: {GIT_BRANCH}")
    print(f"URL:    {PROD_URL}")

    for i in range(1, MAX_ITERATIONS + 1):
        print(f"\n==============================")
        print(f"Iteration {i}/{MAX_ITERATIONS}")
        print(f"==============================")

        # 1. Fetch current build logs
        logs = fetch_latest_build_logs()
        if not logs.strip():
            print("[warn] No logs found. Sleeping and retrying...")
            time.sleep(SLEEP_AFTER_PUSH_SECONDS)
            continue

        # 2. If build is already clean AND we’ve looped at least once, we can stop
        if build_looks_successful(logs):
            print("[info] Build looks successful 🎉")
            print("[done] Stopping loop.")
            return

        # 3. Ask Codex to fix issues based on the logs
        changed = run_codex_on_logs(logs)
        if not changed:
            print("[info] Codex has no further changes. Stopping loop.")
            return

        # 4. Commit & push changes (this triggers a new Vercel deployment)
        pushed = git_commit_and_push()
        if not pushed:
            print("[info] No code changes actually pushed. Stopping loop.")
            return

        # 5. Give Vercel time to build the new commit
        print(f"[info] Sleeping {SLEEP_AFTER_PUSH_SECONDS}s while Vercel builds...")
        time.sleep(SLEEP_AFTER_PUSH_SECONDS)

    print(f"[stop] Reached MAX_ITERATIONS={MAX_ITERATIONS}. Exiting.")


if __name__ == "__main__":
    main()

# cd /path/to/your/repo
# python /abs_path_to/vercel_codex_loop.py
