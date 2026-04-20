#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "slots" / "villages.json"
CATALOG_URL = "https://toponym.antat.ru/toponyms/1?page={page}"
DETAIL_LINK_RE = re.compile(r"^https://toponym\.antat\.ru/toponym/(\d+)$")
PAGE_NUMBER_RE = re.compile(r"^\d+$")
REQUEST_TIMEOUT_MS = 60000
MAX_RETRIES = 3


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_field(lines: list[str], label: str) -> str | None:
    for index, line in enumerate(lines):
        if line == label:
            for next_line in lines[index + 1 :]:
                if next_line:
                    return next_line
    return None


def split_name_variants(value: str) -> list[str]:
    variants: list[str] = []
    for part in value.split(","):
        cleaned = re.sub(r"\s+", " ", part).strip()
        if cleaned:
            variants.append(cleaned)
    return variants


def normalize_for_comparison(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def discover_last_page(page) -> int:
    pager_texts = page.locator("a").evaluate_all("(els) => els.map(e => (e.textContent || '').trim())")
    numbers = [int(text) for text in pager_texts if PAGE_NUMBER_RE.match(text)]
    if not numbers:
        raise RuntimeError("Could not discover the last catalog page number.")
    return max(numbers)


def fetch_html(request_context, url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = request_context.get(url, timeout=REQUEST_TIMEOUT_MS)
            if response.status != 200:
                raise RuntimeError(f"Unexpected status {response.status} for {url}")
            return response.text()
        except Exception as exc:
            last_error = exc
            print(f"retry={attempt} url={url}", flush=True)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def extract_detail_urls_from_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    detail_urls: OrderedDict[str, None] = OrderedDict()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if href.startswith("/toponym/"):
            href = f"https://toponym.antat.ru{href}"
        if DETAIL_LINK_RE.match(href):
            detail_urls[href] = None
    return list(detail_urls.keys())


def collect_detail_urls(request_context, start_page: int, end_page: int) -> list[str]:
    detail_urls: OrderedDict[str, None] = OrderedDict()
    for page_number in range(start_page, end_page + 1):
        html = fetch_html(request_context, CATALOG_URL.format(page=page_number))
        for href in extract_detail_urls_from_html(html):
            detail_urls[href] = None
        if page_number == start_page or page_number == end_page or page_number % 25 == 0:
            print(f"list_page={page_number}", flush=True)
    return list(detail_urls.keys())


def extract_names(request_context, detail_url: str) -> tuple[list[str], list[str]]:
    html = fetch_html(request_context, detail_url)
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    lines = clean_lines(text)
    russian_value = extract_field(lines, "На русском языке:")
    tatar_value = extract_field(lines, "На татарском языке:")
    if not russian_value or not tatar_value:
        raise RuntimeError(f"Could not extract Russian/Tatar name pair from {detail_url}")
    return split_name_variants(russian_value), split_name_variants(tatar_value)


def update_villages(
    start_page: int,
    end_page: int | None,
    output_path: Path,
    only_nonidentical_ru_tat: bool,
) -> tuple[int, int]:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        context = browser.new_context(ignore_https_errors=True)
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "font", "media", "stylesheet"}
            else route.continue_(),
        )
        list_page = context.new_page()

        list_page.goto(CATALOG_URL.format(page=start_page), wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT_MS)
        resolved_end_page = end_page or discover_last_page(list_page)
        detail_urls = collect_detail_urls(context.request, start_page, resolved_end_page)

        villages: OrderedDict[str, None] = OrderedDict()
        for index, detail_url in enumerate(detail_urls, start=1):
            russian_names, tatar_names = extract_names(context.request, detail_url)
            russian_set = {normalize_for_comparison(name) for name in russian_names}
            if only_nonidentical_ru_tat and all(normalize_for_comparison(name) in russian_set for name in tatar_names):
                continue
            for name in tatar_names:
                villages[name] = None
            if index == 1 or index == len(detail_urls) or index % 250 == 0:
                print(f"detail_page={index}/{len(detail_urls)}", flush=True)

        browser.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"village": list(villages.keys())}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(detail_urls), len(villages)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Tatar village names from the paginated Toponym catalog and update villages.json."
    )
    parser.add_argument("--start-page", type=int, default=1, help="First catalog page to parse.")
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="Last catalog page to parse. If omitted, the script discovers the last page automatically.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Output JSON file to update.",
    )
    parser.add_argument(
        "--only-nonidentical-ru-tat",
        action="store_true",
        help="Keep only villages where the Russian and Tatar names are not identical.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        detail_count, village_count = update_villages(
            args.start_page,
            args.end_page,
            args.output,
            args.only_nonidentical_ru_tat,
        )
    except PlaywrightTimeoutError as exc:
        print(f"Timed out while fetching the catalog: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Failed to update villages: {exc}", file=sys.stderr)
        return 1

    print(f"detail_pages={detail_count}")
    print(f"villages={village_count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
