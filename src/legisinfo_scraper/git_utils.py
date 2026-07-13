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
