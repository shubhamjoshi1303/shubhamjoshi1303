import requests
import subprocess
import re

USERNAME = "shubhamjoshi1303"

# -------------------------
# Get repo count
# -------------------------

user = requests.get(
    f"https://api.github.com/users/{USERNAME}"
).json()

repos = user["public_repos"]

# -------------------------
# Get commit count
# -------------------------

events = requests.get(
    f"https://api.github.com/users/{USERNAME}/events"
).json()

commits = 0

for event in events:
    if event["type"] == "PushEvent":
        commits += len(event["payload"]["commits"])

# -------------------------
# LOC using tokei
# -------------------------

result = subprocess.check_output(
    ["tokei", "."]
).decode()

match = re.search(r"Total\s+\d+\s+\d+\s+\d+\s+(\d+)", result)

loc = match.group(1) if match else "0"

# -------------------------
# Added / deleted lines
# -------------------------

git_stats = subprocess.check_output(
    "git log --shortstat --pretty=format:",
    shell=True
).decode()

added = sum(
    int(x)
    for x in re.findall(r"(\d+) insertions?", git_stats)
)

deleted = sum(
    int(x)
    for x in re.findall(r"(\d+) deletions?", git_stats)
)

# format nicely
added = f"{added//1000}K" if added > 1000 else str(added)
deleted = f"{deleted//1000}K" if deleted > 1000 else str(deleted)

# -------------------------
# Replace placeholders
# -------------------------

for file in ["dark_mode.svg", "light_mode.svg"]:

    with open(file, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("{{REPOS}}", str(repos))
    content = content.replace("{{COMMITS}}", str(commits))
    content = content.replace("{{LOC}}", str(loc))
    content = content.replace("{{ADDED}}", added)
    content = content.replace("{{DELETED}}", deleted)

    with open(file, "w", encoding="utf-8") as f:
        f.write(content)

print("Updated SVG stats.")