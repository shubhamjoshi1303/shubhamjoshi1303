import json
import os
import re
import tempfile
import subprocess
import urllib.error
import urllib.request
from html import escape
from pathlib import Path


USERNAME = "shubhamjoshi1303"
ROOT = Path(__file__).resolve().parents[1]
SVG_FILES = (ROOT / "dark_mode.svg", ROOT / "light_mode.svg")

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}

SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".css",
    ".go",
    ".h",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
}


def github_json(path):
    token = os.environ.get("GITHUB_TOKEN")
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "profile-readme-stats-updater",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed: {error.code} {body}") from error


def github_paginated(path):
    page = 1
    results = []

    while True:
        separator = "&" if "?" in path else "?"
        data = github_json(f"{path}{separator}per_page=100&page={page}")
        if not data:
            return results

        results.extend(data)
        page += 1


def public_repo_count():
    user = github_json(f"/users/{USERNAME}")
    return int(user["public_repos"])


def public_source_repos():
    repos = github_paginated(f"/users/{USERNAME}/repos?type=owner&sort=full_name")
    return [repo for repo in repos if not repo.get("fork")]


def run_command(args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.DEVNULL)


def clone_repo(repo, destination):
    clone_url = repo["clone_url"]
    args = [
        "git",
        "clone",
        "--quiet",
        "--depth",
        "1",
        "--single-branch",
    ]

    default_branch = repo.get("default_branch")
    if default_branch:
        args.extend(["--branch", default_branch])

    args.extend([clone_url, str(destination)])
    run_command(args)

    # A shallow clone keeps initial checkout fast. Unshallow when possible so
    # history totals reflect the full default branch instead of only depth=1.
    try:
        run_command(["git", "fetch", "--quiet", "--unshallow"], cwd=destination)
    except subprocess.CalledProcessError:
        pass


def line_count_with_tokei(path):
    try:
        output = run_command(["tokei", ".", "--output", "json"], cwd=path)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    try:
        data = json.loads(output)
        return int(data["Total"]["code"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def should_count(path, relative_path):
    if any(part in EXCLUDED_DIRS for part in relative_path.parts):
        return False
    return path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS


def fallback_line_count(root):
    total = 0

    for path in root.rglob("*"):
        relative_path = path.relative_to(root)
        if not should_count(path, relative_path):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        total += sum(1 for line in text.splitlines() if line.strip())

    return total


def line_count(path):
    return line_count_with_tokei(path) or fallback_line_count(path)


def commit_count(path):
    try:
        return int(run_command(["git", "rev-list", "--count", "HEAD"], cwd=path).strip())
    except subprocess.CalledProcessError:
        return 0


def added_deleted_lines(path):
    try:
        output = run_command(
            ["git", "log", "--shortstat", "--pretty=format:"],
            cwd=path,
        )
    except subprocess.CalledProcessError:
        return 0, 0

    added = sum(int(value) for value in re.findall(r"(\d+) insertions?", output))
    deleted = sum(int(value) for value in re.findall(r"(\d+) deletions?", output))
    return added, deleted


def aggregate_repo_stats():
    totals = {
        "commits": 0,
        "loc": 0,
        "added": 0,
        "deleted": 0,
    }
    repos = public_source_repos()

    with tempfile.TemporaryDirectory(prefix="profile-stats-") as temp_dir:
        temp_root = Path(temp_dir)

        for repo in repos:
            repo_name = repo["name"]
            repo_path = temp_root / repo_name

            if repo.get("size", 0) == 0:
                print(f"Skipping {repo['full_name']}: empty repo")
                continue

            print(f"Cloning {repo['full_name']}...")

            try:
                clone_repo(repo, repo_path)
            except subprocess.CalledProcessError as error:
                print(f"Skipping {repo['full_name']}: clone failed ({error.returncode})")
                continue

            added, deleted = added_deleted_lines(repo_path)
            totals["commits"] += commit_count(repo_path)
            totals["loc"] += line_count(repo_path)
            totals["added"] += added
            totals["deleted"] += deleted

    return totals


def format_count(value):
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1_000:
        return f"{value / 1_000:.1f}K".replace(".0K", "K")
    return str(value)


def update_svg(path, stats):
    content = path.read_text(encoding="utf-8")
    line_1 = f"Repos: {stats['repos']} | Commits: {stats['commits']}"
    line_2 = f"{stats['loc']} | (+{stats['added']}, -{stats['deleted']})"

    replacements = {
        "stats-line-1": escape(line_1),
        "stats-line-2": escape(line_2),
    }

    for element_id, text in replacements.items():
        content, count = re.subn(
            rf'(<text\b[^>]*\bid="{element_id}"[^>]*>).*?(</text>)',
            lambda match: f"{match.group(1)}{text}{match.group(2)}",
            content,
            count=1,
            flags=re.DOTALL,
        )
        if count != 1:
            raise RuntimeError(f"Could not update {element_id} in {path.name}")

    path.write_text(content, encoding="utf-8")


def main():
    repo_stats = aggregate_repo_stats()
    stats = {
        "repos": format_count(public_repo_count()),
        "commits": format_count(repo_stats["commits"]),
        "loc": format_count(repo_stats["loc"]),
        "added": format_count(repo_stats["added"]),
        "deleted": format_count(repo_stats["deleted"]),
    }

    for path in SVG_FILES:
        update_svg(path, stats)

    print(
        "Updated SVG stats: "
        f"repos={stats['repos']}, commits={stats['commits']}, loc={stats['loc']}, "
        f"added={stats['added']}, deleted={stats['deleted']}"
    )


if __name__ == "__main__":
    main()
