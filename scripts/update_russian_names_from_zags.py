#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import ssl
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "slots" / "russian_names.json"
API_URL = "https://zags.nalog.gov.ru/api/nameselect/firstnames"
PAGE_SIZE = 500
TIMEOUT_SECONDS = 60
SSL_CONTEXT = ssl._create_unverified_context()


def fetch_page(page: int, size: int) -> dict:
    query = urlencode(
        {
            "search": "",
            "favorite": "false",
            "gender": "",
            "page": page,
            "size": size,
            "clearfavorites": "false",
            "sort": "a",
        }
    )
    request = Request(
        f"{API_URL}?{query}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
        return json.loads(response.read().decode("utf-8"))


def unique_sorted(values: list[str]) -> list[str]:
    return sorted(OrderedDict.fromkeys(value.strip() for value in values if value and value.strip()))


def update_names(output_path: Path, page_size: int) -> tuple[int, int, int]:
    first_page = fetch_page(1, page_size)
    total_count = int(first_page["firstNamesCount"])
    total_pages = max(1, math.ceil(total_count / page_size))

    all_names: list[str] = []
    male_names: list[str] = []
    female_names: list[str] = []

    for page_number in range(1, total_pages + 1):
        data = first_page if page_number == 1 else fetch_page(page_number, page_size)
        names = data.get("firstNames", [])
        for item in names:
            name = (item.get("name") or "").strip()
            gender_code = item.get("genderCode")
            if not name:
                continue
            all_names.append(name)
            if gender_code == "M":
                male_names.append(name)
            elif gender_code == "F":
                female_names.append(name)
        if page_number == 1 or page_number == total_pages or page_number % 10 == 0:
            print(f"page={page_number}/{total_pages}", flush=True)

    payload = {
        "person_name_russian": unique_sorted(all_names),
        "person_name_russian_male": unique_sorted(male_names),
        "person_name_russian_female": unique_sorted(female_names),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(payload["person_name_russian"]), len(payload["person_name_russian_male"]), len(
        payload["person_name_russian_female"]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Russian names from the ZAGS name-selection API and update russian_names.json."
    )
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE, help="Page size for API pagination.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON file path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        total_names, male_names, female_names = update_names(args.output, args.page_size)
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
        print(f"Failed to update Russian names: {exc}", file=sys.stderr)
        return 1

    print(f"person_name_russian={total_names}")
    print(f"person_name_russian_male={male_names}")
    print(f"person_name_russian_female={female_names}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
