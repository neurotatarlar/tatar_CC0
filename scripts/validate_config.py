#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_PATH = ROOT / "data" / "templates" / "themes.json"
SLOTS_DIR = ROOT / "data" / "slots"
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)(?::([a-z0-9_]+))?\}")
SUPPORTED_FORMS = {"nom", "gen", "dat", "acc", "loc", "abl", "1sg", "3sg"}


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


def validate_templates(template_data: dict, slots: dict[str, list[object]]) -> list[str]:
    errors: list[str] = []
    themes = template_data.get("themes", {})
    if not isinstance(themes, dict) or not themes:
        errors.append("Template file must contain a non-empty 'themes' object.")
        return errors

    for theme_name, theme_body in themes.items():
        intents = theme_body.get("intents", {})
        if not isinstance(intents, dict) or not intents:
            errors.append(f"Theme '{theme_name}' must contain a non-empty 'intents' object.")
            continue
        for intent_name, templates in intents.items():
            if not isinstance(templates, list) or not templates:
                errors.append(f"Theme '{theme_name}' intent '{intent_name}' must be a non-empty list.")
                continue
            for template in templates:
                if not isinstance(template, str) or not template.strip():
                    errors.append(f"Theme '{theme_name}' intent '{intent_name}' contains an empty template.")
                    continue
                for slot_name, case_name in PLACEHOLDER_RE.findall(template):
                    if slot_name not in slots:
                        errors.append(
                            f"Unknown slot '{slot_name}' in theme '{theme_name}' intent '{intent_name}'."
                        )
                    if case_name and case_name not in SUPPORTED_FORMS:
                        errors.append(
                            f"Unsupported form '{case_name}' in theme '{theme_name}' intent '{intent_name}'."
                        )
    return errors


def main() -> int:
    template_data = load_json(TEMPLATES_PATH)
    slots = load_slots(SLOTS_DIR)
    errors = validate_templates(template_data, slots)

    if errors:
        print("CONFIG INVALID")
        for error in errors:
            print(f"- {error}")
        return 1

    print("CONFIG OK")
    print(f"themes={len(template_data['themes'])}")
    print(f"slots={len(slots)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
