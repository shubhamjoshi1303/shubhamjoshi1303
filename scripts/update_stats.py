import json
import os
import re
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


def public_repo_count():
    user = github_json(f"/users/{USERNAME}")
    return int(user["public_repos"])


def recent_activity_count():
    events = github_json(f"/users/{USERNAME}/events/public?per_page=100")
    count = 0

    for event in events:
        if event.get("type") == "PushEvent":
            count += len(event.get("payload", {}).get("commits", []))
        elif event.get("type") in {"CreateEvent", "PullRequestEvent", "IssuesEvent"}:
            count += 1

    return count


def run_command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL)


def line_count_with_tokei():
    try:
        output = run_command(["tokei", ".", "--output", "json"])
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


def fallback_line_count():
    total = 0

    for path in ROOT.rglob("*"):
        relative_path = path.relative_to(ROOT)
        if not should_count(path, relative_path):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        total += sum(1 for line in text.splitlines() if line.strip())

    return total


def line_count():
    return line_count_with_tokei() or fallback_line_count()


def added_deleted_lines():
    output = run_command(["git", "log", "--shortstat", "--pretty=format:"])
    added = sum(int(value) for value in re.findall(r"(\d+) insertions?", output))
    deleted = sum(int(value) for value in re.findall(r"(\d+) deletions?", output))
    return added, deleted


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
    added, deleted = added_deleted_lines()
    stats = {
        "repos": format_count(public_repo_count()),
        "commits": format_count(recent_activity_count()),
        "loc": format_count(line_count()),
        "added": format_count(added),
        "deleted": format_count(deleted),
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
