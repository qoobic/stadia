# Accelerated Coordinate Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete, auditable, visually accurate 466-venue coordinate dataset quickly.

**Architecture:** A resolver batches Wikidata identities and uses Nominatim only to select OSM objects near an independently cached city coordinate. Class-aware geometry derives a focal point and emits `needs_imagery`; a static imagery audit accepts or repositions every candidate before `verified` export.

**Tech Stack:** Python 3 standard library, Nominatim/Overpass/Wikidata HTTP APIs, Leaflet static HTML, JSON, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-13-stadia-coordinates-design.md`

## Global Constraints

- Nominatim and Wikidata coordinates are identity/discovery evidence, never final game coordinates.
- Preserve focal definitions and provenance for every source request and geometry.
- Uncertainty limits are 40 m stadium/arena, 60 m golf, and 75 m circuit/racecourse.
- Every final coordinate requires an imagery audit decision.
- Cache all external source payloads and pace public API requests at one request per second.

---

### Task 1: Build cached city and OSM-object discovery

**Files:**

- Modify: `tools/bulk_resolve.py`
- Modify: `tests/test_bulk_resolve.py`

**Interfaces:**

- Produces `resolve_city(name: str, country: str) -> dict | None`.
- Produces `resolve_osm_object(venue: dict, city: dict) -> dict | None`.
- Each result records request URL, cache hash, source point, OSM type/id, and distance to city.

- [ ] **Step 1: Write failing tests**

```python
def test_nominatim_object_outside_city_radius_is_rejected():
    assert select_nominatim_object(venue, city, far_response) is None

def test_nominatim_object_is_identity_evidence_not_final_coordinate():
    result = select_nominatim_object(venue, city, valid_response)
    assert result['osm_id'] == 'way/12'
    assert 'final_lat' not in result
```

- [ ] **Step 2: Run the focused test module**

Run: `python3 -m unittest tests.test_bulk_resolve -v`

Expected: FAIL because the city and Nominatim object selectors do not exist.

- [ ] **Step 3: Implement the minimal cached selectors**

```python
def select_nominatim_object(venue, city, response):
    candidates = [row for row in response if class_compatible(venue, row)]
    candidates = [row for row in candidates if distance_m(city, row) <= 40_000]
    return candidates[0] if len(candidates) == 1 else None
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest discover -s tests`

Expected: PASS.

### Task 2: Derive visual focal geometry with class limits

**Files:**

- Modify: `tools/bulk_resolve.py`
- Modify: `tests/test_bulk_resolve.py`

**Interfaces:**

- Produces `derive_accelerated_focal(venue: dict, venue_geometry: dict, members: dict) -> dict | None`.
- Stadium/arena outline fallback records `derivation_method: 'venue_outline_centroid'` and `uncertainty_m`.

- [ ] **Step 1: Write failing tests**

```python
def test_stadium_outline_is_a_documented_visual_fallback():
    focal = derive_accelerated_focal(stadium, outline, {})
    assert focal['derivation_method'] == 'venue_outline_centroid'
    assert focal['uncertainty_m'] == 40

def test_racecourse_never_uses_outline_centroid():
    assert derive_accelerated_focal(racecourse, outline, {}) is None
```

- [ ] **Step 2: Run focused tests**

Run: `python3 -m unittest tests.test_bulk_resolve -v`

Expected: FAIL because accelerated derivation does not exist.

- [ ] **Step 3: Implement class-specific derivation**

```python
def derive_accelerated_focal(venue, venue_geometry, members):
    if venue['venue_class'] in {'stadium', 'arena'}:
        return pitch_or_outline_focal(venue_geometry, members)
    return strict_focal_from_members(venue, members)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest discover -s tests`

Expected: PASS.

### Task 3: Produce an imagery-audit queue and apply decisions

**Files:**

- Create: `tools/audit.html`
- Create: `tools/apply_audit.py`
- Create: `tests/test_apply_audit.py`

**Interfaces:**

- `apply_decisions(records: list[dict], decisions: list[dict]) -> list[dict]` applies `accept`, `move`, or `reject`.
- Decisions contain `venue_id`, `decision`, optional `lat`/`lon`, and `audited_at`.

- [ ] **Step 1: Write failing tests**

```python
def test_accept_marks_a_candidate_verified_after_imagery_audit():
    result = apply_decisions([candidate], [acceptance])
    assert result[0]['status'] == 'verified'

def test_move_replaces_candidate_point_and_records_audit():
    result = apply_decisions([candidate], [move])
    assert result[0]['final_lat'] == move['lat']
```

- [ ] **Step 2: Run test**

Run: `python3 -m unittest tests.test_apply_audit -v`

Expected: FAIL because the audit application module does not exist.

- [ ] **Step 3: Implement static audit and merger**

```python
def apply_decisions(records, decisions):
    by_id = {decision['venue_id']: decision for decision in decisions}
    return [apply_one(record, by_id.get(record['venue_id'])) for record in records]
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest discover -s tests`

Expected: PASS.

### Task 4: Pilot, measure, and run the full queue

**Files:**

- Create: `data/accelerated-pilot.json`
- Create: `data/accelerated-candidates.json`
- Create: `data/accelerated-audit-decisions.json`

**Interfaces:**

- Pilot output contains 25 complete queue records, source evidence, focal candidates, uncertainty, and `needs_imagery` status.
- Full output includes all 466 venue IDs exactly once.

- [ ] **Step 1: Run the resolver on the existing 25-row pilot**

Run: `python3 tools/bulk_resolve.py data/pilot-venues.json data/accelerated-pilot.json --cache-dir data/source-cache --refresh`

Expected: every input ID is represented; no record is directly exported as verified.

- [ ] **Step 2: Inspect identity and focal yield by class**

Run: `python3 -c "import json,collections; print(collections.Counter(x['venue_class'] for x in json.load(open('data/accelerated-pilot.json')) if x['status']=='needs_imagery'))"`

Expected: output identifies the class-specific manual tail before the full run.

- [ ] **Step 3: Run the complete source queue**

Run: `python3 tools/bulk_resolve.py data/venues.json data/accelerated-candidates.json --cache-dir data/source-cache --refresh`

Expected: all 466 IDs are present exactly once with source provenance.

- [ ] **Step 4: Audit every candidate and apply decisions**

Run: `python3 tools/apply_audit.py data/accelerated-candidates.json data/accelerated-audit-decisions.json data/verified-venues.json`

Expected: only audited, valid points are `verified`.
