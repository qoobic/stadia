# Stadia Coordinate Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable pipeline that turns the editable candidate list into an independently reviewable focal-coordinate catalogue.

**Architecture:** A standard-library Python parser creates stable JSON records from the editable text file. A separate validation module enforces focal-point and review-state rules. A 25-venue pilot queue exercises every venue class before any bulk coordinate resolution.

**Tech Stack:** Python 3 standard library, JSON, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-13-stadia-coordinates-design.md`

## Global Constraints

- Never use a geocoder or venue centroid as a game coordinate.
- Preserve source rows and unresolved records.
- Only `verified` records may be exported for play.
- Store latitude/longitude as EPSG:4326 decimal degrees with six or more decimal places.

---

### Task 1: Parse the editable catalogue

**Files:**

- Create: `tests/test_catalogue.py`
- Create: `tools/catalogue.py`
- Create: `data/venues.json`

**Interfaces:**

- Produces `parse_catalogue(text: str) -> list[dict]`.
- Produces `venue_id` as a deterministic slug of name, city, country, and class.

- [ ] **Step 1: Write the failing test**

```python
from tools.catalogue import parse_catalogue

def test_parse_catalogue_preserves_source_fields_and_generates_stable_id():
    rows = parse_catalogue('Wembley Stadium | London | England | stadium\n')
    assert rows == [{
        'venue_id': 'wembley-stadium-london-england-stadium',
        'canonical_name': 'Wembley Stadium',
        'city': 'London',
        'country': 'England',
        'venue_class': 'stadium',
        'source_line': 1,
    }]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_catalogue`

Expected: failure because `tools.catalogue` does not exist.

- [ ] **Step 3: Write the minimal parser and JSON writer**

```python
def parse_catalogue(text: str) -> list[dict]:
    ...

def write_catalogue(source_path: str, output_path: str) -> None:
    ...
```

- [ ] **Step 4: Run the parser test and generate the data file**

Run: `python3 -m unittest tests.test_catalogue && python3 tools/catalogue.py stadia-candidates.txt data/venues.json`

Expected: test passes and JSON contains every non-comment candidate row.

### Task 2: Enforce coordinate-review state rules

**Files:**

- Create: `tests/test_review.py`
- Create: `tools/review.py`

**Interfaces:**

- Produces `validate_review(record: dict) -> list[str]`.
- Produces `can_export(record: dict) -> bool`.

- [ ] **Step 1: Write failing tests**

```python
from tools.review import can_export, validate_review

def test_unverified_coordinate_cannot_be_exported():
    assert can_export({'status': 'manual_required'}) is False

def test_verified_coordinate_requires_coordinate_and_two_reviews():
    errors = validate_review({'status': 'verified', 'final_lat': 51.0, 'final_lon': -0.2})
    assert 'reviewer_a_result is required' in errors
    assert 'reviewer_b_result is required' in errors
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_review`

Expected: failure because `tools.review` does not exist.

- [ ] **Step 3: Implement minimal review validation**

```python
def validate_review(record: dict) -> list[str]:
    ...

def can_export(record: dict) -> bool:
    return not validate_review(record) and record['status'] == 'verified'
```

- [ ] **Step 4: Run both test modules**

Run: `python3 -m unittest tests.test_catalogue tests.test_review`

Expected: all tests pass.

### Task 3: Create the representative pilot queue

**Files:**

- Create: `tests/test_pilot.py`
- Create: `tools/pilot.py`
- Create: `data/pilot-venues.json`

**Interfaces:**

- Produces `select_pilot(venues: list[dict]) -> list[dict]`.
- Each returned record includes `focal_definition`, `status: 'manual_required'`, and empty review evidence fields.

- [ ] **Step 1: Write the failing test**

```python
from tools.pilot import select_pilot

def test_pilot_contains_every_venue_class_and_is_limited_to_25_rows():
    pilot = select_pilot(sample_venues)
    assert len(pilot) == 25
    assert {row['venue_class'] for row in pilot} == {'stadium', 'arena', 'circuit', 'racecourse', 'golf'}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_pilot`

Expected: failure because `tools.pilot` does not exist.

- [ ] **Step 3: Implement a deterministic, balanced selector and writer**

```python
def select_pilot(venues: list[dict]) -> list[dict]:
    ...
```

- [ ] **Step 4: Generate and inspect the pilot**

Run: `python3 -m unittest tests.test_catalogue tests.test_review tests.test_pilot && python3 tools/pilot.py data/venues.json data/pilot-venues.json`

Expected: all tests pass and the pilot contains five venue classes across multiple regions.
