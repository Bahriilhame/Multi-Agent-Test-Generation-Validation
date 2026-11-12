"""Git workspace helpers with strict task-path isolation."""

from pathlib import Path
import re
import subprocess


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def prepare_worktree(repo: str, base_commit: str, root: Path) -> Path:
    """Clone/cache a public repo and create an isolated worktree at base_commit."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("repo must be owner/name")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", base_commit):
        raise ValueError("base_commit must be a full 40-character commit SHA")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    slug = repo.replace("/", "__")
    cache = (root / "repos" / slug).resolve()
    worktree = (root / "tasks" / f"{slug}__{base_commit[:12]}").resolve()
    if root not in cache.parents or root not in worktree.parents:
        raise ValueError("Resolved repository paths must remain inside workspace root")
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        _git(["clone", "--filter=blob:none", f"https://github.com/{repo}.git", str(cache)])
    _git(["fetch", "origin", base_commit], cwd=cache)
    if not worktree.exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _git(["worktree", "add", "--detach", str(worktree), base_commit], cwd=cache)
    if not worktree.is_dir() or not (worktree / ".git").exists():
        raise RuntimeError(f"Refusing to use non-worktree task path: {worktree}")
    actual = _git(["rev-parse", "HEAD"], cwd=worktree)
    if actual.lower() != base_commit.lower():
        raise RuntimeError(f"Worktree commit mismatch: expected {base_commit}, got {actual}")
    return worktree

