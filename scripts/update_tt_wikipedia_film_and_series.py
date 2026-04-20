#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "slots" / "tatar_films_series.json"
API_URL = "https://tt.wikipedia.org/w/api.php"
SSL_CONTEXT = ssl._create_unverified_context()
USER_AGENT = "Mozilla/5.0"

FILM_ROOT_CATEGORY = "Төркем:Еллар буенча фильмнар"
SERIES_ROOT_CATEGORY = "Төркем:Әлифба буенча телесериаллар"
YEAR_FILM_CATEGORY_RE = re.compile(r"^Төркем:\d{4} елның фильмнары$")
TRAILING_MEDIA_QUALIFIER_RE = re.compile(
    r"\s*\((?:телесериал|телевизион сериал|мультсериал|аниме|фильм(?:,\s*\d{4})?|film(?:,\s*\d{4})?)\)\s*$",
    re.IGNORECASE,
)

SERIAL_KEYWORDS = ("телесериал", "сериал", "сериаллар", "сериалы")
ANIMATED_KEYWORDS = ("мультсериал", "мультфильм", "анимацион", "аниме")
FILM_KEYWORDS = ("фильм", "фильмнар", "кино")


def fetch_json(params: dict[str, str]) -> dict:
    request = Request(
        f"{API_URL}?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(request, context=SSL_CONTEXT, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_title(title: str) -> str:
    return TRAILING_MEDIA_QUALIFIER_RE.sub("", title).strip()


def iter_category_members(category_title: str) -> list[dict]:
    members: list[dict] = []
    continuation: dict[str, str] = {}
    while True:
        payload = fetch_json(
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category_title,
                "cmlimit": "500",
                "format": "json",
                **continuation,
            }
        )
        members.extend(payload.get("query", {}).get("categorymembers", []))
        if "continue" not in payload:
            break
        continuation = {
            key: value
            for key, value in payload["continue"].items()
            if key != "continue"
        }
    return members


def batch(iterable: list[str], size: int) -> list[list[str]]:
    return [iterable[index : index + size] for index in range(0, len(iterable), size)]


def fetch_page_categories(titles: list[str]) -> dict[str, list[str]]:
    by_title: dict[str, list[str]] = {}
    for chunk in batch(titles, 50):
        payload = fetch_json(
            {
                "action": "query",
                "prop": "categories",
                "titles": "|".join(chunk),
                "cllimit": "max",
                "format": "json",
            }
        )
        for page in payload.get("query", {}).get("pages", {}).values():
            title = page.get("title", "")
            categories = [item["title"] for item in page.get("categories", [])]
            by_title[title] = categories
    return by_title


def collect_film_titles() -> list[str]:
    titles: OrderedDict[str, None] = OrderedDict()
    visited_categories: set[str] = set()

    def walk(category_title: str) -> None:
        if category_title in visited_categories:
            return
        visited_categories.add(category_title)
        for member in iter_category_members(category_title):
            namespace = member.get("ns")
            title = member.get("title", "").strip()
            if not title:
                continue
            if namespace == 0:
                titles[title] = None
            elif namespace == 14:
                walk(title)

    for member in iter_category_members(FILM_ROOT_CATEGORY):
        category_title = member.get("title", "")
        if member.get("ns") == 14 and YEAR_FILM_CATEGORY_RE.match(category_title):
            walk(category_title)

    raw_titles = list(titles.keys())
    categories_by_title = fetch_page_categories(raw_titles) if raw_titles else {}

    result: OrderedDict[str, None] = OrderedDict()
    for title in raw_titles:
        lowered_title = title.lower()
        categories_text = " ".join(categories_by_title.get(title, [])).lower()
        if any(keyword in lowered_title for keyword in SERIAL_KEYWORDS):
            continue
        if any(keyword in categories_text for keyword in ("телесериал", "сериаллар", "мультсериал")):
            continue
        result[normalize_title(title)] = None
    return list(result.keys())


def collect_series_titles() -> list[str]:
    raw_titles = [
        member["title"].strip()
        for member in iter_category_members(SERIES_ROOT_CATEGORY)
        if member.get("ns") == 0 and member.get("title", "").strip()
    ]
    categories_by_title = fetch_page_categories(raw_titles) if raw_titles else {}

    result: OrderedDict[str, None] = OrderedDict()
    for title in raw_titles:
        lowered_title = title.lower()
        categories_text = " ".join(categories_by_title.get(title, [])).lower()

        if any(keyword in lowered_title for keyword in ANIMATED_KEYWORDS):
            continue
        if "(фильм" in lowered_title:
            continue
        if any(keyword in categories_text for keyword in ANIMATED_KEYWORDS):
            continue
        if "фильм" in categories_text and not any(keyword in categories_text for keyword in SERIAL_KEYWORDS):
            continue

        result[normalize_title(title)] = None
    return list(result.keys())


def update_lists(output_path: Path) -> dict[str, list[str]]:
    payload = {
        "film": collect_film_titles(),
        "series": collect_series_titles(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch film and live-action-like TV-series titles from Tatar Wikipedia categories."
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON file path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = update_lists(args.output)
    except Exception as exc:
        print(f"Failed to update Tatar Wikipedia film and series lists: {exc}", file=sys.stderr)
        return 1

    print(f"film={len(payload['film'])}")
    print(f"series={len(payload['series'])}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
