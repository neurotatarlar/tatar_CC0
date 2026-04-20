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

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "slots" / "kazan_streets_tatar.json"
WIKIPEDIA_URL = (
    "https://ru.wikipedia.org/wiki/"
    "%D0%A1%D0%BF%D0%B8%D1%81%D0%BE%D0%BA_%D1%83%D0%BB%D0%B8%D1%86_%D0%9A%D0%B0%D0%B7%D0%B0%D0%BD%D0%B8"
)
WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
SSL_CONTEXT = ssl._create_unverified_context()
USER_AGENT = "Mozilla/5.0"
QID_RE = re.compile(r"/wiki/(Q\d+)$")
BATCH_SIZE = 50


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"})
    with urlopen(request, context=SSL_CONTEXT, timeout=60) as response:
        return response.read().decode("utf-8")


def extract_qids_from_wikipedia(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.wikitable")
    if table is None:
        raise RuntimeError("Could not find the Kazan streets table on Wikipedia.")

    qids: OrderedDict[str, None] = OrderedDict()
    for anchor in table.select('a.extiw[href*="wikidata.org/wiki/Q"]'):
        href = anchor.get("href", "")
        match = QID_RE.search(href)
        if match:
            qids[match.group(1)] = None
    return list(qids.keys())


def batched(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def fetch_tatar_labels(qids: list[str]) -> OrderedDict[str, str]:
    names: OrderedDict[str, str] = OrderedDict()
    for batch_index, batch in enumerate(batched(qids, BATCH_SIZE), start=1):
        params = urlencode(
            {
                "action": "wbgetentities",
                "format": "json",
                "props": "labels",
                "languages": "tt",
                "ids": "|".join(batch),
            }
        )
        payload = json.loads(fetch_text(f"{WIKIDATA_API_URL}?{params}"))
        entities = payload.get("entities", {})
        for qid in batch:
            entity = entities.get(qid, {})
            tt_label = entity.get("labels", {}).get("tt", {}).get("value")
            if tt_label:
                names[tt_label] = qid
        if batch_index == 1 or batch_index % 10 == 0 or batch_index == len(batched(qids, BATCH_SIZE)):
            print(f"batch={batch_index}/{len(batched(qids, BATCH_SIZE))}", flush=True)
    return names


def update_streets(output_path: Path) -> tuple[int, int]:
    wikipedia_html = fetch_text(WIKIPEDIA_URL)
    qids = extract_qids_from_wikipedia(wikipedia_html)
    names = fetch_tatar_labels(qids)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"street_kazan_tatar": list(names.keys())}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(qids), len(names)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Kazan street Wikidata links from Wikipedia and write Tatar street names to a slot file."
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON file path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        qid_count, street_count = update_streets(args.output)
    except Exception as exc:
        print(f"Failed to update Kazan streets: {exc}", file=sys.stderr)
        return 1

    print(f"wikidata_qids={qid_count}")
    print(f"street_kazan_tatar={street_count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
