# Tatar templated sentence generation

This workspace now uses a split config:

- `data/templates/themes.json`: only theme and intent templates
- `data/slots/*.json`: slot vocabularies in nominative form
- `data/slots/common_voice_domains.json`: reusable slot pack for Common Voice-style smart home, reminder, messaging, navigation, weather, and search templates
- `scripts/validate_config.py`: checks placeholder and slot consistency
- `scripts/generate_sentences.py`: generates exact unique sentences, inflects slot nouns into Tatar cases, applies verb forms, capitalizes sentence start, and adds final punctuation
- `scripts/update_villages_from_toponym.py`: rebuilds `data/slots/villages.json` from the paginated `Ойконим` catalog at `toponym.antat.ru`
- `scripts/update_russian_names_from_zags.py`: rebuilds `data/slots/russian_names.json` from the ZAGS name-selection API
- `scripts/update_kazan_streets_from_wikidata.py`: rebuilds `data/slots/kazan_streets_tatar.json` from the Kazan streets Wikipedia list and the linked Wikidata items
- `scripts/update_tatar_cartoons_from_dubdb.py`: rebuilds `data/slots/tatar_cartoons.json` from DubDB's Tatar-language film and TV-show dub categories
- `scripts/update_tt_wikipedia_film_and_series.py`: rebuilds `data/slots/tatar_films_series.json` from Tatar Wikipedia film-by-year and TV-series categories

## Placeholder format

- `{slot}` or `{slot:nom}`: nominative form
- `{slot:gen}`: genitive
- `{slot:dat}`: dative
- `{slot:acc}`: accusative
- `{slot:loc}`: locative
- `{slot:abl}`: ablative
- `{slot:1sg}`: explicit first-person singular verb form from a slot dictionary
- `{slot:3sg}`: explicit third-person singular verb form from a slot dictionary

Example:

```text
{city:loc} {place_type:acc} тап
{contact:dat} {amount} җибәр
{product:gen} бәясен кара
мин {daily_action:1sg}
ул {daily_action:3sg}
```

## Commands

Validate config:

```bash
python3 scripts/validate_config.py
```

Refresh the village list from the live catalog:

```bash
python3 scripts/update_villages_from_toponym.py
```

Refresh the village list but keep only entries where the Russian and Tatar names differ:

```bash
python3 scripts/update_villages_from_toponym.py --only-nonidentical-ru-tat
```

Refresh the Russian names list from ZAGS:

```bash
python3 scripts/update_russian_names_from_zags.py
```

Refresh the Kazan street list in Tatar from Wikipedia + Wikidata:

```bash
python3 scripts/update_kazan_streets_from_wikidata.py
```

Refresh the Tatar cartoon and cartoon-series lists from DubDB:

```bash
python3 scripts/update_tatar_cartoons_from_dubdb.py
```

Refresh the Tatar Wikipedia film and series lists:

```bash
python3 scripts/update_tt_wikipedia_film_and_series.py
```

Generate all available JSONL sentences:

```bash
python3 scripts/generate_sentences.py --format jsonl --output outputs/tat_Cyrl_sentences.jsonl
```

Generate only banking and telecom examples:

```bash
python3 scripts/generate_sentences.py --themes banking_payments,telecom_support --format txt --output outputs/support.txt
```

Generate up to 500 per theme:

```bash
python3 scripts/generate_sentences.py --max-per-theme 500 --format jsonl --output outputs/tat_Cyrl_per_theme.jsonl
```

Generate with per-theme overrides from a JSON file:

```bash
python3 scripts/generate_sentences.py --theme-max-file config/theme_limits.json --format jsonl --output outputs/tat_Cyrl_limited.jsonl
```

Example `config/theme_limits.json`:

```json
{
  "assistant_common": 100,
  "banking_payments": 400,
  "telecom_support": 400
}
```

## Morphology note

The generator assumes slot values are stored in nominative form and applies a lightweight Tatar case transformation at generation time. It inflects the final word in a phrase using simple vowel harmony and voicing rules, which works well for many common ASR-style nouns and noun phrases.

For verbs, use explicit form dictionaries in slot files for person-specific forms such as `1sg` and `3sg`.

## Surface normalization

- Each generated sentence starts with a capital letter.
- The generator appends final punctuation automatically.
- Interrogative sentences receive `?` using a lightweight heuristic; other outputs receive `.` by default.

## Source notes

- `data/templates/themes.json` now includes patterns distilled from the examples in `common_voice_intents.txt`, grouped into reusable slots instead of copying the example set literally.
- `person_name` was refreshed using Tatar name entries visible in the mirrored/public name articles that reproduce the same list as the requested Millattashlar page, including entries such as `ӘДИБӘ -> Әдибә`.
- `village` was added from татарские ойконимы in the Tatarstan toponym catalog at `toponym.antat.ru`.
- `cartoon` and `cartoon_series` are refreshed from DubDB via the `Tatar-language film dubs` and `Tatar-language TV show dubs` categories, with trailing annotations such as `(Tatar)` removed from titles.
- `film` and `series` are refreshed from Tatar Wikipedia; films are collected by recursively walking year-based film categories, while the `series` list excludes obvious film and animated-series spillover from the TV-series category.
