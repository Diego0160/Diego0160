#!/usr/bin/env python3
"""Generate GitHub profile README from GitHub API data."""

import argparse
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

SPOTIFY_USER = "31xeyrnyhnslgituoph2rdn7j5ym"


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


def get_recent_activity(username, token=None):
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
                # Fallback if both are missing/zero, but it's a push
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


def get_readme_stats(username, token=None):
    user = get_user(username, token=token)
    repos = get_repos(username, token=token)

    base = {
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
        "activity": [],
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

    base["activity"] = get_recent_activity(username, token=token)

    return base


def render_template(template_path, stats):
    with open(template_path) as f:
        template = f.read()

    ctx = {k: v for k, v in stats.items()}

    lang_bar = " ".join(
        f"![](https://img.shields.io/badge/{lang.replace(' ', '%20')}-{_lang_color(lang)}?style=flat&logo={_lang_logo(lang)})"
        for lang in stats["top_languages"]
    )
    ctx["lang_badges"] = lang_bar

    avatar = stats["avatar_url"]

    tech_badges = " ".join(
        f"![](https://img.shields.io/badge/{t}-{_lang_color(t)}?style=flat&logo={_lang_logo(t)})"
        for t in ["Nix", "QML", "Python", "TypeScript", "Haxe", "Hyprland"]
    )

    neofetch_lines = f"""
| | |
|---|---|
| <img src="{avatar}" width="120" height="120" /> | **{stats['name']}**<br><br>{tech_badges}<br><br>**OS** NixOS ❄️ / Arch 🐉 · **WM** Hyprland<br>**Repos** {stats['public_repos']} public · {stats['repo_count']} active<br>**Stars** {stats['total_stars']} · **Forks** {stats['total_forks']}<br>**Followers** {stats['followers']} · **Following** {stats['following']} |
"""
    ctx["neofetch"] = neofetch_lines

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

    print(f"[*] Done: {args.output}")
    print(f"    API returned: name={stats['name']}, repos={stats['repo_count']}, "
          f"followers={stats['followers']}, activity={len(stats['activity'])}")


main()
