#!/usr/bin/env python3
"""Fetch GitHub trending repos and save to data/trending/.

Usage:
    python3 py/fetch-trending.py                     # daily, all languages
    python3 py/fetch-trending.py --since weekly       # weekly trending
    python3 py/fetch-trending.py --since monthly      # monthly trending
    python3 py/fetch-trending.py --language python    # filter by language
    python3 py/fetch-trending.py --all                # fetch daily+weekly+monthly

Output: data/trending/YYYY-MM-DD[THH:MM:SS]-{daily,weekly,monthly}.json
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "trending"
TRENDING_URL = "https://github.com/trending"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def fetch_trending(since: str = "daily", language: str = "") -> str:
    """Fetch trending page HTML."""
    url = f"{TRENDING_URL}/{language}?since={since}" if language else f"{TRENDING_URL}?since={since}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_articles(html: str) -> list[dict]:
    """Parse trending repos from HTML.

    Each <article class="Box-row"> stripped of HTML tags gives a clean text pattern:
        owner /
        repo_name
        description
        language
        stars_count
        forks_count
        stars_today
    """
    articles = re.findall(
        r'<article[^>]*class="Box-row"[^>]*>.*?</article>', html, re.DOTALL
    )

    results = []
    for art in articles:
        # Strip HTML tags to get clean text lines
        text = re.sub(r"<[^>]+>", "\n", art)
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Filter out UI-only lines
        lines = [l for l in lines if l not in ("Sponsor", "Star", "Fork", "Built by", "")]

        # Extract "X stars today"
        stars_today = 0
        remaining = []
        for l in lines:
            m = re.search(r"([\d,]+)\s+stars?\s+today", l)
            if m:
                stars_today = int(m.group(1).replace(",", ""))
            else:
                remaining.append(l)
        lines = remaining

        # Remove "Built by" trailing lines + any remaining artifact lines
        lines = [l for l in lines if not l.startswith("Built by")]

        if len(lines) < 5:
            continue  # skip malformed entries

        # Owner/repo: first two lines are "owner /" and "repo_name"
        owner = lines[0].rstrip(" /")
        repo_name = lines[1]
        full_name = f"{owner}/{repo_name}"
        # Get repo URL
        m_href = re.search(r'href="([^"]*/' + re.escape(full_name) + r')"', art)
        repo_url = f"https://github.com{ m_href.group(1) }" if m_href else f"https://github.com/{full_name}"

        # Description: everything between repo_name and language
        # Some descriptions span multiple lines before the language marker
        desc_lines = []
        idx = 2
        while idx < len(lines) and idx < 4:  # language is usually line 3 or 4
            desc_lines.append(lines[idx])
            idx += 1

        # Try to find the language line
        skip_language = False
        # Common patterns to detect where language is
        lang_idx = 2
        for i in range(2, min(len(lines), 5)):
            v = lines[i]
            # If it's a number, we already passed language (no language listed)
            if re.match(r"^[\d,]+$", v):
                skip_language = True
                idx = i
                break
            # If it's a known word that's not a language, skip
            if v in ("Built",):
                continue
            # Otherwise, it's either part of description or the language
            # Check if next line is a number (stars count)
            if i + 1 < len(lines) and re.match(r"^[\d,]+$", lines[i + 1]):
                # This line is the language
                lang_idx = i
                break

        description = " ".join(lines[2:lang_idx]).strip()
        language = lines[lang_idx] if not skip_language else ""
        num_idx = lang_idx + (0 if skip_language else 1)

        stars = int(lines[num_idx].replace(",", "")) if num_idx < len(lines) else 0
        forks = int(lines[num_idx + 1].replace(",", "")) if num_idx + 1 < len(lines) else 0

        results.append({
            "full_name": full_name,
            "owner": owner,
            "repo": repo_name,
            "url": repo_url,
            "description": description,
            "language": language,
            "stars": stars,
            "forks": forks,
            "stars_today": stars_today,
        })

    return results


def save_results(repos: list[dict], since: str):
    """Save repos to data/trending/ as timestamped JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = f"{ts}-{since}.json"
    path = DATA_DIR / filename

    output = {
        "fetched_at": ts,
        "since": since,
        "count": len(repos),
        "repos": repos,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(repos)} repos → {path}")
    return path


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch GitHub trending repos")
    parser.add_argument("--since", choices=["daily", "weekly", "monthly"], default="daily")
    parser.add_argument("--language", default="", help="Filter by language (e.g. python)")
    parser.add_argument("--all", action="store_true", help="Fetch daily+weekly+monthly at once")
    args = parser.parse_args()

    if args.all:
        for s in ("daily", "weekly", "monthly"):
            print(f"\n=== Fetching {s} ===")
            html = fetch_trending(since=s, language=args.language)
            repos = parse_articles(html)
            save_results(repos, s)
    else:
        html = fetch_trending(since=args.since, language=args.language)
        repos = parse_articles(html)
        save_results(repos, args.since)


if __name__ == "__main__":
    main()