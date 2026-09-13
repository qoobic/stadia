"""Parse the editable venue candidate catalogue into stable JSON records."""

import json
import re
import sys
import unicodedata


def _slug(*parts: str) -> str:
    value = "-".join(parts)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def parse_catalogue(text: str) -> list[dict]:
    records = []
    seen_ids = {}
    for source_line, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 4 or any(not field for field in fields):
            records.append({
                "source_line": source_line,
                "raw_source_line": raw_line,
                "status": "parse_error",
                "error": "expected four non-empty pipe-separated fields",
            })
            continue
        name, city, country, venue_class = fields
        venue_id = _slug(name, city, country, venue_class)
        if venue_id in seen_ids:
            raise ValueError(
                f"venue_id collision for {venue_id!r} at lines "
                f"{seen_ids[venue_id]} and {source_line}"
            )
        seen_ids[venue_id] = source_line
        records.append({
            "venue_id": venue_id,
            "canonical_name": name,
            "city": city,
            "country": country,
            "venue_class": venue_class,
            "source_line": source_line,
        })
    return records


def write_catalogue(source_path: str, output_path: str) -> None:
    with open(source_path, encoding="utf-8") as source:
        records = parse_catalogue(source.read())
    with open(output_path, "w", encoding="utf-8") as output:
        json.dump(records, output, ensure_ascii=False, indent=2)
        output.write("\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} SOURCE OUTPUT")
    write_catalogue(sys.argv[1], sys.argv[2])
