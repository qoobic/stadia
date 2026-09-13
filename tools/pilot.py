"""Build the deterministic, diverse venue queue for initial manual review."""

import json
import sys
from collections import defaultdict
from pathlib import Path


PILOT_SIZE = 25
FOCAL_DEFINITIONS = {
    "stadium": "playing-surface centre",
    "arena": "competition-floor centre",
    "circuit": "current main-layout start/finish line",
    "racecourse": "winning post on the racing surface",
    "golf": "18th green centre",
}
COUNTRY_REGIONS = {
    **{country: "Europe" for country in ("England", "Scotland", "Wales", "Northern Ireland", "France", "Germany", "Italy", "Spain", "Portugal", "Belgium", "Netherlands", "Austria", "Monaco", "Hungary", "Azerbaijan", "Türkiye", "Czechia", "Serbia", "Belarus", "Ireland")},
    **{country: "Americas" for country in ("United States", "Canada", "Mexico", "Brazil", "Argentina", "Chile", "Colombia")},
    **{country: "Asia-Pacific" for country in ("Japan", "China", "South Korea", "Australia", "New Zealand", "Philippines", "Hong Kong", "India")},
    **{country: "Middle East" for country in ("Qatar", "United Arab Emirates", "Bahrain", "Saudi Arabia")},
    **{country: "Africa" for country in ("South Africa", "Algeria", "Angola", "Egypt")},
}
REVIEW_FIELDS = (
    "reviewer_a_id", "reviewer_b_id", "reviewer_a_evidence",
    "reviewer_b_evidence", "reviewer_a_result", "reviewer_b_result",
    "reviewer_a_notes", "reviewer_b_notes", "reviewer_agreement_m",
)


def select_pilot(venues: list[dict]) -> list[dict]:
    """Select five records per class, rotating through regions deterministically."""
    grouped = defaultdict(lambda: defaultdict(list))
    for venue in venues:
        if venue.get("venue_class") in FOCAL_DEFINITIONS:
            country = venue.get("country", "")
            grouped[venue["venue_class"]][COUNTRY_REGIONS.get(country, "Other")].append(venue)
    selected = []
    for venue_class in FOCAL_DEFINITIONS:
        regions = {}
        for region, candidates in grouped[venue_class].items():
            regions[region] = sorted(candidates, key=lambda row: (row.get("country", ""), row.get("city", ""), row.get("venue_id", "")))
        chosen = []
        region_names = sorted(regions)
        while len(chosen) < PILOT_SIZE // len(FOCAL_DEFINITIONS):
            progressed = False
            for region in region_names:
                if regions[region]:
                    chosen.append(regions[region].pop(0))
                    progressed = True
                    if len(chosen) == PILOT_SIZE // len(FOCAL_DEFINITIONS):
                        break
            if not progressed:
                break
        selected.extend(chosen)
    if len(selected) != PILOT_SIZE:
        raise ValueError("at least five candidates are required for each venue class")
    result = []
    for venue in selected:
        row = dict(venue)
        row["focal_definition"] = FOCAL_DEFINITIONS[row["venue_class"]]
        row["status"] = "manual_required"
        row.update({field: "" for field in REVIEW_FIELDS})
        result.append(row)
    return result


def write_pilot(source_path: str, output_path: str) -> None:
    venues = json.loads(Path(source_path).read_text())
    Path(output_path).write_text(json.dumps(select_pilot(venues), indent=2) + "\n")


if __name__ == "__main__":
    write_pilot(sys.argv[1], sys.argv[2])
