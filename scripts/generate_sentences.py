#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_PATH = ROOT / "data" / "templates" / "themes.json"
SLOTS_DIR = ROOT / "data" / "slots"
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)(?::([a-z0-9_]+))?\}")
SUPPORTED_CASES = {"nom", "gen", "dat", "acc", "loc", "abl"}
SUPPORTED_FORMS = SUPPORTED_CASES | {"1sg", "3sg"}
BACK_VOWELS = set("аоуыАОУЫ")
FRONT_VOWELS = set("әөүеиӘӨҮЕИ")
ALL_VOWELS = BACK_VOWELS | FRONT_VOWELS | set("ёюяЁЮЯ")
VOICELESS = set("пфктсшщчцхһqk")
QUESTION_STARTERS = {
    "кем",
    "нәрсә",
    "кайда",
    "кайчан",
    "ничек",
    "күпме",
    "ничә",
    "нинди",
    "нигә",
    "ни өчен",
    "әллә",
}
QUESTION_ENDINGS = ("мы", "ме")
QUESTION_TOKENS = {
    "кем",
    "нәрсә",
    "кайда",
    "кайчан",
    "кайсы",
    "ничек",
    "күпме",
    "ничә",
    "нинди",
    "нигә",
    "бармы",
    "буламы",
    "эшлиме",
}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def is_valid_slot_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value) and all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in value.items())
    return False


def load_slots(slots_dir: Path) -> dict[str, list[object]]:
    merged: dict[str, list[object]] = {}
    for path in sorted(slots_dir.glob("*.json")):
        data = load_json(path)
        if not isinstance(data, dict):
            raise TypeError(f"{path} must contain a JSON object.")
        for slot_name, values in data.items():
            if slot_name in merged:
                raise ValueError(f"Duplicate slot '{slot_name}' found in {path}.")
            if not isinstance(values, list) or not values or not all(is_valid_slot_value(v) for v in values):
                raise ValueError(
                    f"Slot '{slot_name}' in {path} must be a non-empty list of strings or form dictionaries."
                )
            merged[slot_name] = values
    return merged


def split_phrase(phrase: str) -> tuple[str, str]:
    phrase = phrase.strip()
    parts = phrase.rsplit(" ", 1)
    if len(parts) == 1:
        return "", parts[0]
    return parts[0] + " ", parts[1]


def last_vowel(token: str) -> str | None:
    for char in reversed(token):
        if char in ALL_VOWELS:
            return char
    return None


def is_front(token: str) -> bool:
    vowel = last_vowel(token)
    if vowel is None:
        return False
    return vowel in FRONT_VOWELS or vowel in set("ёюяЁЮЯ")


def is_voiceless(token: str) -> bool:
    stripped = token.rstrip("ьъЬЪ")
    if not stripped:
        return False
    return stripped[-1] in VOICELESS


def is_possessive_third_person(token: str) -> bool:
    return len(token) >= 3 and token.endswith(("сы", "се")) and token[-3] in ALL_VOWELS


def inflect_tatar_noun(phrase: str, case_name: str) -> str:
    if case_name not in SUPPORTED_CASES:
        raise ValueError(f"Unsupported case: {case_name}")
    if case_name == "nom":
        return phrase

    prefix, token = split_phrase(phrase)
    front = is_front(token)
    voiceless = is_voiceless(token)
    possessive = is_possessive_third_person(token)

    if case_name == "gen":
        suffix = "нең" if front else "ның"
        return prefix + token + suffix
    if case_name == "dat":
        if possessive:
            return prefix + token + ("нә" if front else "на")
        return prefix + token + ("кә" if front else "ка") if voiceless else prefix + token + ("гә" if front else "га")
    if case_name == "acc":
        if possessive:
            return prefix + token + "н"
        return prefix + token + ("не" if front else "ны")
    if case_name == "loc":
        if possessive:
            return prefix + token + ("ндә" if front else "нда")
        return prefix + token + ("тә" if front else "та") if voiceless else prefix + token + ("дә" if front else "да")
    if case_name == "abl":
        if possessive:
            return prefix + token + ("ннән" if front else "ннан")
        return prefix + token + ("тән" if front else "тан") if voiceless else prefix + token + ("дән" if front else "дан")
    raise ValueError(f"Unsupported case: {case_name}")


def resolve_slot_value(slot_name: str, form_name: str, entry: object) -> tuple[str, str]:
    if form_name not in SUPPORTED_FORMS:
        raise ValueError(f"Unsupported form: {form_name}")
    if isinstance(entry, str):
        if form_name in SUPPORTED_CASES:
            return entry, inflect_tatar_noun(entry, form_name)
        raise ValueError(f"Slot '{slot_name}' requires an explicit form dictionary for '{form_name}'.")
    if not isinstance(entry, dict):
        raise TypeError(f"Unexpected slot entry type for '{slot_name}'.")

    base_form = entry.get("nom") or entry.get("lemma") or next(iter(entry.values()))
    if form_name in entry:
        return base_form, entry[form_name]
    if form_name in SUPPORTED_CASES:
        return base_form, inflect_tatar_noun(base_form, form_name)
    raise ValueError(f"Slot '{slot_name}' entry does not define form '{form_name}'.")


def capitalize_first(text: str) -> str:
    for index, char in enumerate(text):
        if char.isalpha():
            return text[:index] + char.upper() + text[index + 1 :]
    return text


def guess_terminal_punctuation(text: str) -> str:
    normalized = text.strip().lower()
    tokens = normalized.split()
    if not tokens:
        return "."
    if normalized.endswith(("?", ".", "!")):
        return ""
    if normalized.startswith(tuple(QUESTION_STARTERS)):
        return "?"
    if any(token in QUESTION_TOKENS for token in tokens):
        return "?"
    if any(token.endswith(QUESTION_ENDINGS) for token in tokens):
        return "?"
    if normalized.endswith(("бармы", "буламы", "эшлиме")):
        return "?"
    return "."


def normalize_sentence(text: str) -> str:
    sentence = re.sub(r"\s+", " ", text).strip()
    sentence = capitalize_first(sentence)
    sentence += guess_terminal_punctuation(sentence)
    return sentence


def extract_placeholders(template: str) -> list[tuple[str, str]]:
    return [(slot_name, form_name or "nom") for slot_name, form_name in PLACEHOLDER_RE.findall(template)]


def render_template_with_entries(template: str, entries: list[tuple[str, str, object]]) -> tuple[str, list[dict[str, str]]]:
    substitutions: list[dict[str, str]] = []
    index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal index
        slot_name, form_name, entry = entries[index]
        index += 1
        base_form, rendered = resolve_slot_value(slot_name, form_name, entry)
        substitutions.append(
            {
                "slot": slot_name,
                "base": base_form,
                "form": form_name,
                "rendered": rendered,
            }
        )
        return rendered

    sentence = PLACEHOLDER_RE.sub(replace, template)
    return normalize_sentence(sentence), substitutions


def iter_templates(template_data: dict, selected_themes: set[str] | None) -> list[dict[str, str]]:
    templates: list[dict[str, str]] = []
    for theme_name, theme_body in template_data["themes"].items():
        if selected_themes and theme_name not in selected_themes:
            continue
        for intent_name, template_list in theme_body["intents"].items():
            for template in template_list:
                templates.append({"theme": theme_name, "intent": intent_name, "template": template})
    return templates


def enumerate_template_rows(template_entry: dict[str, str], slots: dict[str, list[object]]) -> list[dict]:
    placeholders = extract_placeholders(template_entry["template"])
    if not placeholders:
        return [
            {
                "text": normalize_sentence(template_entry["template"]),
                "theme": template_entry["theme"],
                "intent": template_entry["intent"],
                "template": template_entry["template"],
                "substitutions": [],
            }
        ]

    choices = [slots[slot_name] for slot_name, _ in placeholders]
    rows: list[dict] = []
    seen: set[str] = set()
    for combination in itertools.product(*choices):
        entries = [(slot_name, form_name, entry) for (slot_name, form_name), entry in zip(placeholders, combination)]
        text, substitutions = render_template_with_entries(template_entry["template"], entries)
        if text in seen:
            continue
        seen.add(text)
        rows.append(
            {
                "text": text,
                "theme": template_entry["theme"],
                "intent": template_entry["intent"],
                "template": template_entry["template"],
                "substitutions": substitutions,
            }
        )
    return rows


def build_theme_rows(template_data: dict, slots: dict[str, list[object]], selected_themes: set[str] | None) -> dict[str, list[dict]]:
    rows_by_theme: dict[str, list[dict]] = {}
    seen_by_theme: dict[str, set[str]] = {}
    for template_entry in iter_templates(template_data, selected_themes):
        theme = template_entry["theme"]
        rows_by_theme.setdefault(theme, [])
        seen_by_theme.setdefault(theme, set())
        for row in enumerate_template_rows(template_entry, slots):
            if row["text"] in seen_by_theme[theme]:
                continue
            seen_by_theme[theme].add(row["text"])
            rows_by_theme[theme].append(row)
    return rows_by_theme


def load_theme_max_map(path: Path | None) -> dict[str, int]:
    if path is None:
        return {}
    data = load_json(path)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object mapping themes to integer limits.")
    limits: dict[str, int] = {}
    for theme_name, value in data.items():
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"Theme limit for '{theme_name}' must be a non-negative integer.")
        limits[theme_name] = value
    return limits


def select_rows(
    rows_by_theme: dict[str, list[dict]],
    seed: int,
    target_count: int | None,
    max_per_theme: int | None,
    theme_limits: dict[str, int],
) -> tuple[list[dict], dict[str, dict[str, int]]]:
    rng = random.Random(seed)
    selected: list[dict] = []
    summary: dict[str, dict[str, int]] = {}

    for theme, rows in rows_by_theme.items():
        shuffled = list(rows)
        rng.shuffle(shuffled)
        available = len(shuffled)
        limit = theme_limits.get(theme, max_per_theme if max_per_theme is not None else available)
        generated = min(limit, available)
        summary[theme] = {"requested": limit, "available": available, "generated": generated}
        selected.extend(shuffled[:generated])

    rng.shuffle(selected)
    if target_count is not None:
        selected = selected[: min(target_count, len(selected))]
    return selected, summary


def write_jsonl(rows: list[dict], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_txt(rows: list[dict], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(row["text"] + "\n")


def write_csv(rows: list[dict], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "theme", "intent", "template", "substitutions"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "text": row["text"],
                    "theme": row["theme"],
                    "intent": row["intent"],
                    "template": row["template"],
                    "substitutions": json.dumps(row["substitutions"], ensure_ascii=False),
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Tatar tat_Cyrl sentences from templates.")
    parser.add_argument(
        "--target-count",
        type=int,
        default=None,
        help="Optional global maximum number of sentences after per-theme selection. Leave empty for all selected rows.",
    )
    parser.add_argument(
        "--themes",
        type=str,
        default="",
        help="Comma-separated list of theme names. Leave empty to use all themes.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible shuffling.")
    parser.add_argument(
        "--max-per-theme",
        type=int,
        default=None,
        help="Maximum number of generated sentences per theme. If a theme cannot reach this count, the script uses that theme's maximum possible unique count.",
    )
    parser.add_argument(
        "--theme-max-file",
        type=Path,
        default=None,
        help="Optional JSON file mapping theme names to per-theme maximum counts.",
    )
    parser.add_argument(
        "--format",
        choices=["jsonl", "txt", "csv"],
        default="jsonl",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "tat_Cyrl_sentences.jsonl",
        help="Output file path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    template_data = load_json(TEMPLATES_PATH)
    slots = load_slots(SLOTS_DIR)
    selected_themes = {item.strip() for item in args.themes.split(",") if item.strip()} or None
    theme_limits = load_theme_max_map(args.theme_max_file)

    rows_by_theme = build_theme_rows(template_data, slots, selected_themes)
    rows, summary = select_rows(
        rows_by_theme=rows_by_theme,
        seed=args.seed,
        target_count=args.target_count,
        max_per_theme=args.max_per_theme,
        theme_limits=theme_limits,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "jsonl":
        write_jsonl(rows, args.output)
    elif args.format == "txt":
        write_txt(rows, args.output)
    else:
        write_csv(rows, args.output)

    print(f"generated={len(rows)}")
    print(f"output={args.output}")
    for theme in sorted(summary):
        info = summary[theme]
        print(f"theme={theme} requested={info['requested']} available={info['available']} generated={info['generated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
