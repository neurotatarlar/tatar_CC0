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
OUTPUT_PATH = ROOT / "data" / "slots" / "tatar_cartoons.json"
API_URL = "https://dubdb.fandom.com/api.php"
SSL_CONTEXT = ssl._create_unverified_context()
USER_AGENT = "Mozilla/5.0"
CATEGORY_MAP = {
    "cartoon": "Category:Tatar-language_film_dubs",
    "cartoon_series": "Category:Tatar-language_TV_show_dubs",
}
TRAILING_ANNOTATION_RE = re.compile(r"\s*\((?:Tatar(?:,[^)]*)?|first dub)\)\s*$", re.IGNORECASE)


def fetch_json(params: dict[str, str]) -> dict:
    query = urlencode(params)
    request = Request(
        f"{API_URL}?{query}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urlopen(request, context=SSL_CONTEXT, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_title(title: str) -> str:
    title = TRAILING_ANNOTATION_RE.sub("", title).strip()
    title = title.replace(" hәм ", " һәм ")
    title = title.replace("Hәм", "Һәм")
    return title


def fetch_category_titles(category_name: str) -> list[str]:
    titles: OrderedDict[str, None] = OrderedDict()
    continuation: dict[str, str] = {}
    while True:
        payload = fetch_json(
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category_name,
                "cmlimit": "500",
                "format": "json",
                **continuation,
            }
        )
        members = payload.get("query", {}).get("categorymembers", [])
        for member in members:
            title = member.get("title", "").strip()
            if not title:
                continue
            titles[normalize_title(title)] = None
        if "continue" not in payload:
            break
        continuation = {
            key: value
            for key, value in payload["continue"].items()
            if key != "continue"
        }
    return list(titles.keys())


def update_lists(output_path: Path) -> dict[str, list[str]]:
    result = {
        list_name: fetch_category_titles(category_name)
        for list_name, category_name in CATEGORY_MAP.items()
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Tatar cartoon and cartoon-series titles from DubDB category pages."
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON file path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = update_lists(args.output)
    except Exception as exc:
        print(f"Failed to update Tatar cartoon lists: {exc}", file=sys.stderr)
        return 1

    for key, values in data.items():
        print(f"{key}={len(values)}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
