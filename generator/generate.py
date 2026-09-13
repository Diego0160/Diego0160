#!/usr/bin/env python3
"""Generate GitHub profile README from GitHub API data.

Built with Nix: run via `nix run .#profile-readme` so the generator is
declared as a Nix dependency and GITHUB_TOKEN is available at runtime
(outside the Nix sandbox).
"""

import argparse
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

SPOTIFY_USER = "31xeyrnyhnslgituoph2rdn7j5ym"

# Repos that reflect the user's Nix/Qt stack (featured section)
FEATURED_KEYWORDS = ("quickshell", "sddm", "caelestia", "dots", "nix")


def api_get(endpoint, token=None):
    url = f"https://api.github.com{endpoint}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "profile-readme-generator")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  [warn] HTTP {e.code} for {endpoint}")
        return None
    except Exception as e:
        print(f"  [warn] {e} for {endpoint}")
        return None


def api_search_commits(username, token=None):
    """Commit search needs the cloak-preview Accept header."""
    url = f"https://api.github.com/search/commits?q=author:{username}&per_page=1"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.cloak-preview")
    req.add_header("User-Agent", "profile-readme-generator")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [warn] {e} for commit search")
        return None


def get_commit_count(username, token=None):
    data = api_search_commits(username, token=token)
    if data is None:
        data = api_search_commits(username)
    return (data or {}).get("total_count", 0)


def get_pr_count(username, token=None):
    data = api_get(f"/search/issues?q=author:{username}+type:pr&per_page=1", token=token)
    if data is None:
        data = api_get(f"/search/issues?q=author:{username}+type:pr&per_page=1")
    return (data or {}).get("total_count", 0)


def get_issue_count(username, token=None):
    data = api_get(f"/search/issues?q=author:{username}+type:issue&per_page=1", token=token)
    if data is None:
        data = api_get(f"/search/issues?q=author:{username}+type:issue&per_page=1")
    return (data or {}).get("total_count", 0)


CONTRIB_EVENTS = {"PushEvent", "PullRequestEvent", "IssuesEvent",
                  "IssueCommentEvent", "CreateEvent", "ReleaseEvent"}


def get_contributed_count(events):
    """Unique repos the user actually contributed to (recent public events)."""
    repos = set()
    for ev in events:
        if ev.get("type") in CONTRIB_EVENTS:
            repo = ev.get("repo", {}).get("name", "")
            if repo:
                repos.add(repo)
    return len(repos)


def get_user(username, token=None):
    data = api_get(f"/users/{username}", token=token)
    if data is None:
        data = api_get(f"/users/{username}")
    return data


def get_repos(username, token=None):
    data = api_get(f"/users/{username}/repos?per_page=100&sort=updated&type=owner", token=token)
    if data is None:
        data = api_get(f"/users/{username}/repos?per_page=100&sort=updated&type=owner")
    return data or []


def get_languages(repo_full_name, token=None):
    data = api_get(f"/repos/{repo_full_name}/languages", token=token)
    if data is None:
        data = api_get(f"/repos/{repo_full_name}/languages")
    return data or {}


def get_recent_activity(username, token=None, events=None):
    if events is None:
        events = api_get(f"/users/{username}/events/public?per_page=10", token=token)
        if not events:
            events = api_get(f"/users/{username}/events/public?per_page=10")
    if not events:
        return []
    items = []
    for ev in events:
        type_ = ev["type"]
        repo = ev["repo"]["name"]
        created = ev.get("created_at", "")[:10]
        payload = ev.get("payload", {})
        item = {"type": type_, "repo": repo, "date": created}

        if type_ == "PushEvent":
            size = payload.get("size")
            commits = payload.get("commits", [])
            count = size if size is not None else len(commits)

            if count == 0 and not commits:
                item["desc"] = "pushed changes"
            else:
                item["desc"] = f"{count} commit{'' if count==1 else 's'}"

            if commits:
                msg = commits[-1].get("message", "").split("\n")[0]
                item["desc"] += f" · {msg[:50]}"
            elif payload.get("head"):
                item["desc"] += f" · {payload['head'][:7]}"
        elif type_ == "IssuesEvent":
            action = payload.get("action", "")
            issue = payload.get("issue", {})
            item["desc"] = f"{action} issue #{issue.get('number', '')} · {issue.get('title', '')[:50]}"
        elif type_ == "IssueCommentEvent":
            issue = payload.get("issue", {})
            item["desc"] = f"commented on issue #{issue.get('number', '')}"
        elif type_ == "PullRequestEvent":
            action = payload.get("action", "")
            pr = payload.get("pull_request", {})
            item["desc"] = f"{action} PR #{pr.get('number', '')} · {pr.get('title', '')[:50]}"
        elif type_ == "CreateEvent":
            ref_type = payload.get("ref_type", "")
            ref = payload.get("ref", "")
            item["desc"] = f"created {ref_type} {ref}" if ref else f"created {ref_type}"
        elif type_ == "ForkEvent":
            forkee = payload.get("forkee", {})
            item["desc"] = f"forked → {forkee.get('full_name', '')}"
        elif type_ == "StarEvent":
            item["desc"] = "starred"
        elif type_ == "WatchEvent":
            item["desc"] = "starred"
        elif type_ == "ReleaseEvent":
            rel = payload.get("release", {})
            item["desc"] = f"published {rel.get('tag_name', '')}"
        elif type_ == "PublicEvent":
            item["desc"] = "made public"
        else:
            item["desc"] = type_
        items.append(item)
    return items[:8]


def get_featured_repos(repos):
    """Select repos that reflect the Nix/Qt stack (QML language or keyword match)."""
    featured = []
    for repo in repos:
        name = repo.get("name", "")
        lang = repo.get("language") or ""
        if lang == "QML" or any(k in name.lower() for k in FEATURED_KEYWORDS):
            featured.append({
                "name": name,
                "html_url": repo.get("html_url", f"https://github.com/{repo.get('full_name', '')}"),
                "description": repo.get("description") or "",
                "language": lang,
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "updated_at": repo.get("updated_at", ""),
            })
    featured.sort(key=lambda r: r["updated_at"], reverse=True)
    return featured[:6]


def get_readme_stats(username, token=None):
    user = get_user(username, token=token)
    repos = get_repos(username, token=token)

    base = {
        "username": username,
        "name": username,
        "bio": "",
        "location": "",
        "company": "",
        "blog": "",
        "public_repos": 0,
        "followers": 0,
        "following": 0,
        "avatar_url": f"https://github.com/{username}.png",
        "top_languages": {},
        "repo_count": 0,
        "total_stars": 0,
        "total_forks": 0,
        "commits": 0,
        "prs": 0,
        "issues": 0,
        "contributed": 0,
        "activity": [],
        "featured": [],
        "spotify_user": SPOTIFY_USER,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    if user:
        base["name"] = user.get("name") or username
        base["bio"] = user.get("bio") or ""
        base["location"] = user.get("location") or ""
        base["company"] = user.get("company") or ""
        base["blog"] = user.get("blog") or ""
        base["public_repos"] = user.get("public_repos", 0)
        base["followers"] = user.get("followers", 0)
        base["following"] = user.get("following", 0)
        base["avatar_url"] = user.get("avatar_url", f"https://github.com/{username}.png")

    if repos:
        lang_bytes = {}
        repo_count = 0
        total_stars = 0
        total_forks = 0
        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            repo_count += 1
            total_stars += repo.get("stargazers_count", 0)
            total_forks += repo.get("forks_count", 0)
            langs = get_languages(repo["full_name"], token=token)
            for lang, bytes_ in langs.items():
                lang_bytes[lang] = lang_bytes.get(lang, 0) + bytes_

        total = sum(lang_bytes.values())
        top_langs = {}
        if total > 0:
            sorted_langs = sorted(lang_bytes.items(), key=lambda x: -x[1])[:8]
            for lang, bytes_ in sorted_langs:
                top_langs[lang] = round(bytes_ / total * 100)

        base["top_languages"] = top_langs
        base["repo_count"] = repo_count
        base["total_stars"] = total_stars
        base["total_forks"] = total_forks
        base["featured"] = get_featured_repos(repos)

    events = api_get(f"/users/{username}/events/public?per_page=10", token=token)
    if not events:
        events = api_get(f"/users/{username}/events/public?per_page=10")
    base["activity"] = get_recent_activity(username, token=token, events=events)
    base["contributed"] = get_contributed_count(events or [])

    base["commits"] = get_commit_count(username, token=token)
    base["prs"] = get_pr_count(username, token=token)
    base["issues"] = get_issue_count(username, token=token)

    return base


def render_template(template_path, stats):
    with open(template_path) as f:
        template = f.read()

    ctx = {k: v for k, v in stats.items()}

    ctx["tech_icons"] = render_tech_icons()

    ctx["featured_rows"] = render_featured(stats["featured"])

    activity_lines = ""
    if stats["activity"]:
        for ev in stats["activity"]:
            icon = _event_icon(ev["type"])
            activity_lines += f"  <tr>\n    <td>{icon}</td>\n    <td><sub><b>{ev['repo'].split('/')[0]}</b>/{ev['repo'].split('/')[1]}</sub></td>\n    <td><sub>{ev['desc'][:70]}</sub></td>\n    <td><sub><code>{ev['date']}</code></sub></td>\n  </tr>\n"
        ctx["activity_rows"] = activity_lines
    else:
        ctx["activity_rows"] = "  <tr><td colspan='4' align='center'><sub>No recent public activity</sub></td></tr>"

    result = template
    for key, val in ctx.items():
        placeholder = f"{{{{ {key} }}}}"
        result = result.replace(placeholder, str(val))

    return result


def render_tech_icons():
    """Skill icons with per-icon tooltips (title attribute survives GitHub's sanitizer).

    Languages actually used across all projects on the system (inir, FNF mods,
    InkBridge, caelestia-dots-flake, MST-API, Arduino, ...) — not GitHub profile stats.
    """
    skills = [
        ("qt", "Qt / QML"),
        ("haxe", "Haxe"),
        ("lua", "Lua"),
        ("python", "Python"),
        ("cpp", "C++"),
        ("typescript", "TypeScript"),
        ("javascript", "JavaScript"),
        ("bash", "Shell"),
        ("nix", "NixOS"),
    ]
    return "\n".join(
        f'  <img src="https://skillicons.dev/icons?i={icon}&theme=dark" title="{label}" alt="{label}" width="48" height="48" />'
        for icon, label in skills
    )


def render_featured(repos):
    if not repos:
        return "  <tr><td colspan='4' align='center'><sub>No featured projects</sub></td></tr>"
    rows = ""
    for r in repos:
        desc = (r["description"] or "No description")[:60]
        stars = r["stars"]
        forks = r["forks"]
        meta = f"{desc} · ⭐ {stars} · 🍴 {forks}" if stars or forks else desc
        rows += (
            f"  <tr>\n"
            f"    <td>{_lang_icon(r['language'])}</td>\n"
            f"    <td><sub><b><a href='{r['html_url']}'>{r['name']}</a></b></sub></td>\n"
            f"    <td><sub>{meta}</sub></td>\n"
            f"    <td><sub><code>{r['language'] or '-'}</code></sub></td>\n"
            f"  </tr>\n"
        )
    return rows


def generate_profile_card(stats, output_dir="."):
    """Generate a profile card SVG: animated banner + avatar + username + stats.

    One self-contained SVG (CSS keyframes — GitHub renders these natively).
    Replaces the old banner + neofetch + external stats widgets.
    """
    avatar = stats["avatar_url"]
    handle = stats["username"]
    repos = stats["public_repos"]
    stars = stats["total_stars"]
    forks = stats["total_forks"]
    commits = stats.get("commits", 0)
    prs = stats.get("prs", 0)
    issues = stats.get("issues", 0)
    contributed = stats.get("contributed", 0)

    left = [
        ("Total Repository:", repos),
        ("Star's Count:", stars),
        ("Fork's Count:", forks),
        ("Commit's Count:", commits),
    ]
    right = [
        ("Total PRs:", prs),
        ("Total Issues:", issues),
        ("Contributed to:", contributed),
    ]

    def stat_rows(col, x, y_start):
        rows = ""
        for i, (label, value) in enumerate(col):
            y = y_start + i * 26
            rows += (
                f'  <text class="stat" x="{x}" y="{y}" font-family="\'Fira Code\', monospace" font-size="13" fill="#8b949e">{label}</text>\n'
                f'  <text class="stat" x="{x + 150}" y="{y}" font-family="\'Fira Code\', monospace" font-size="13" font-weight="600" fill="#e6edf3" text-anchor="end">{value}</text>\n'
            )
        return rows

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="535" height="290" viewBox="0 0 535 290" fill="none">
  <defs>
    <linearGradient id="nixQt" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#7EBAE4"/>
      <stop offset="100%" stop-color="#44A51C"/>
    </linearGradient>
    <clipPath id="avatarClip">
      <circle cx="85" cy="105" r="45"/>
    </clipPath>
    <clipPath id="barClip">
      <rect x="0" y="0" width="535" height="6"/>
    </clipPath>
    <style>
      @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
      @keyframes slideUp {{ from {{ opacity: 0; transform: translateY(12px); }} to {{ opacity: 1; transform: translateY(0); }} }}
      @keyframes shimmer {{ 0% {{ transform: translateX(-100%); }} 100% {{ transform: translateX(100%); }} }}
      .card {{ animation: fadeIn 0.8s ease-out both; }}
      .username {{ animation: slideUp 0.6s ease-out 0.3s both; }}
      .stat {{ animation: slideUp 0.5s ease-out both; }}
      .shimmer {{ animation: shimmer 3s ease-in-out infinite; }}
    </style>
  </defs>
  <rect class="card" width="535" height="290" rx="14" fill="#0d1117" stroke="#30363d" stroke-width="1"/>
  <g clip-path="url(#barClip)">
    <rect x="0" y="0" width="535" height="6" fill="url(#nixQt)"/>
    <rect class="shimmer" x="0" y="0" width="180" height="6" fill="rgba(255,255,255,0.35)"/>
  </g>
  <image href="{avatar}" x="40" y="60" width="90" height="90" clip-path="url(#avatarClip)"/>
  <circle cx="85" cy="105" r="45" fill="none" stroke="url(#nixQt)" stroke-width="2"/>
  <text class="username" x="150" y="95" font-family="'Fira Code', monospace" font-size="22" font-weight="700" fill="#7EBAE4">@{handle}</text>
  <text x="150" y="118" font-family="'Fira Code', monospace" font-size="12" fill="#8b949e">GitHub Stats</text>
{stat_rows(left, 150, 150)}
{stat_rows(right, 330, 150)}
</svg>
'''
    path = os.path.join(output_dir, "profile-card.svg")
    with open(path, "w") as f:
        f.write(svg)
    print(f"[*] Profile card written: {path}")


def _event_icon(type_):
    icons = {
        "PushEvent": "📤",
        "IssuesEvent": "🐛",
        "IssueCommentEvent": "💬",
        "PullRequestEvent": "🔄",
        "CreateEvent": "✨",
        "ForkEvent": "🍴",
        "StarEvent": "⭐",
        "WatchEvent": "⭐",
        "ReleaseEvent": "📦",
        "PublicEvent": "🌍",
        "DeleteEvent": "🗑️",
        "MemberEvent": "👤",
    }
    return icons.get(type_, "🔹")


def _lang_icon(lang):
    icons = {
        "QML": "🎨",
        "Nix": "❄️",
        "Python": "🐍",
        "TypeScript": "🔷",
        "Haxe": "🎮",
        "HTML": "🌐",
        "JavaScript": "🟨",
        "Shell": "🐚",
        "Rust": "🦀",
        "C++": "⚙️",
        "C": "🔧",
        "Lua": "🌙",
        "Java": "☕",
        "Kotlin": "🟣",
        "CSS": "🎨",
    }
    return icons.get(lang, "📦")


def _lang_color(lang):
    colors = {
        "Python": "3776AB",
        "QML": "44A51C",
        "JavaScript": "F7DF1E",
        "TypeScript": "3178C6",
        "Haxe": "EA8220",
        "HTML": "E34F26",
        "Shell": "4EAA25",
        "Nix": "7EBAE4",
        "Java": "ED8B00",
        "Kotlin": "7F52FF",
        "C": "A8B9CC",
        "C++": "00599C",
        "CSS": "1572B6",
        "Lua": "2C2D72",
        "Rust": "000000",
        "Hyprland": "00C1D4",
    }
    return colors.get(lang, "555555")


def _lang_logo(lang):
    logos = {
        "Python": "python",
        "QML": "qt",
        "JavaScript": "javascript",
        "TypeScript": "typescript",
        "Haxe": "haxe",
        "HTML": "html5",
        "Shell": "gnubash",
        "Nix": "nixos",
        "Java": "openjdk",
        "Kotlin": "kotlin",
        "C": "c",
        "C++": "cplusplus",
        "CSS": "css3",
        "Lua": "lua",
        "Rust": "rust",
        "Hyprland": "hyprland",
    }
    return logos.get(lang, "github")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="Diego0160")
    parser.add_argument("--template", default="generator/template.md")
    parser.add_argument("--output", default="README.md")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    print(f"[*] Token available: {bool(token)}")

    print(f"[*] Fetching data for {args.username}...")
    stats = get_readme_stats(args.username, token=token)

    print(f"[*] Rendering template: {args.template}")
    readme = render_template(args.template, stats)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        f.write(readme)

    generate_profile_card(stats, os.path.dirname(args.output) or ".")

    print(f"[*] Done: {args.output}")
    print(f"    API returned: name={stats['name']}, repos={stats['repo_count']}, "
          f"followers={stats['followers']}, activity={len(stats['activity'])}, "
          f"featured={len(stats['featured'])}, commits={stats['commits']}, "
          f"prs={stats['prs']}, issues={stats['issues']}, contributed={stats['contributed']}")


main()