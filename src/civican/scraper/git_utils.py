import os
import subprocess


def run_command(args, cwd=None):
    """Run a system command and return output."""
    return subprocess.run(args, capture_output=True, text=True, cwd=cwd)


def run_git_commit(message, date_str, repo_path, author_name=None, author_email=None):
    """Run git commit with backdated dates and optional author override."""
    env = os.environ.copy()
    cmd = ["git", "commit", "-m", message]

    if date_str:
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
        cmd.append(f"--date={date_str}")

    if author_name:
        env["GIT_AUTHOR_NAME"] = author_name
    if author_email:
        env["GIT_AUTHOR_EMAIL"] = author_email

    return subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path, env=env)


def find_commit_by_event_id(event_id, repo_path):
    """Find a commit hash in the git history by the Legisinfo-Event ID."""
    cmd = ["git", "log", f"--grep=Legisinfo-Event: {event_id}", "--format=%H"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path)
    if res.returncode == 0 and res.stdout.strip():
        # Return the first matching commit hash
        return res.stdout.strip().split("\n")[0]
    return None


def run_git_fixup(target_hash, repo_path, author_name=None, author_email=None):
    """Create a fixup commit targeting an existing commit hash."""
    env = os.environ.copy()
    cmd = ["git", "commit", f"--fixup={target_hash}"]

    if author_name:
        env["GIT_AUTHOR_NAME"] = author_name
        env["GIT_COMMITTER_NAME"] = author_name
    if author_email:
        env["GIT_AUTHOR_EMAIL"] = author_email
        env["GIT_COMMITTER_EMAIL"] = author_email

    return subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path, env=env)


def run_git_autosquash(repo_path, author_name=None, author_email=None):
    """Perform a non-interactive autosquash rebase on the root."""
    env = os.environ.copy()
    env["GIT_SEQUENCE_EDITOR"] = "true"

    if author_name:
        env["GIT_AUTHOR_NAME"] = author_name
        env["GIT_COMMITTER_NAME"] = author_name
    if author_email:
        env["GIT_AUTHOR_EMAIL"] = author_email
        env["GIT_COMMITTER_EMAIL"] = author_email

    cmd = ["git", "rebase", "--interactive", "--autosquash", "--empty=keep", "--root"]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path, env=env)
