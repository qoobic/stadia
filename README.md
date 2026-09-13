# Stadia

Daily satellite-view sporting-venue guessing game. Five rounds per day, one fixed
satellite view per round, one guess each via autocomplete. Sibling project to
[Elevation](https://elevation-game.netlify.app), whose architecture it is ported from.

## Local dev

```bash
python3 -m http.server 8000
open http://localhost:8000/
```

Append `?dev` for the dev panel (day navigation, clear state, celebration test).

## Tests

Two independent suites live in this repository.

**Web app (JavaScript)** — open `http://localhost:8000/tests/js/test.html`. Results
render in the page with a pass count at the bottom.

**Coordinate catalogue (Python)** — `tests/test_catalogue.py`, `tests/test_pilot.py`,
`tests/test_review.py`, covering the tooling in `tools/`. Run them with your usual
Python test runner from the repository root.

## The venue data is currently a placeholder

`data/live-venues.json` is the **current live dataset**. Its coordinates are
approximate and hand-entered; they have not been through the catalogue's verification
pipeline and must not be treated as verified. The file marks itself with
`"_temporary": true`, and `tests/js/live-data.test.js` asserts that flag is present —
so swapping in real data without clearing the flag fails the suite loudly.

Two known consequences, both properties of the placeholder rather than the game:

- The autocomplete pool is only 19 venues, small enough to solve by elimination.
- Distances shown on the reveal screen are indicative only.

The real dataset comes from the coordinate catalogue workstream (see
`docs/superpowers/specs/2026-09-13-stadia-coordinates-design.md`). Only records with
`status == "verified"` are eligible for export — `tools/review.py:can_export` is the
gate. The export is expected to produce the same banded structure, keyed by the same
`venueId`, and to omit `_temporary`.

## Architecture

See `docs/superpowers/specs/2026-09-13-stadia-web-app-design.md`.

Static site, no build step. `index.html` pulls Leaflet from CDN and loads `js/main.js`
as an ES module.

| Module | Purpose |
|---|---|
| `js/main.js` | Orchestration: load data, resolve the day, run five rounds, show the summary |
| `js/venues.js` | Day arithmetic, daily venue selection, search index |
| `js/state.js` | LocalStorage persistence with in-memory fallback |
| `js/score.js` | Haversine distance and round scoring |
| `js/share.js` | Share-string construction and clipboard copy |
| `js/map.js` | Leaflet setup, guess/reveal/summary map states |
| `js/picker.js` | Autocomplete input and suggestion list |
| `js/ui.js` | Panel, summary, dev panel and celebration rendering |
| `js/analytics.js` | Google Analytics event wrapper |

### Bands are difficulty, not venue class

`data/live-venues.json` holds five bands, `l1` (most recognisable) through `l5`
(hardest). Each day draws one venue per band via `list[dayIndex % list.length]`, where
day 0 is `launchDate`. `venueClass` (`stadium`, `arena`, `circuit`, `racecourse`,
`golf`) is metadata: it informs the default zoom and the reveal display, and is reported
to analytics, but plays no part in selection. Any day may serve any mix of classes.

### Scoring

Ported unchanged from Elevation. Distance converts to miles, then:

```
n = max(1, ceil((-39 + sqrt(1521 + 8 * distMiles)) / 2))
distanceScore = max(0, 101 - n)
```

Exact venue scores `distanceScore` (100 at zero distance). Any wrong venue scores
`min(distanceScore + countryBonus, 90)`, where the bonus is 10 for the right country.
Round multipliers are `[1, 1, 2, 3, 3]`, so a perfect day is 1,000.

**This curve is flat at venue scale, by design.** Every wrong guess within roughly 200
miles scores exactly 90, and every same-country wrong guess within roughly 400 miles
also scores 90. Stadia is therefore a recognition game: you either name the venue or you
score 90 for being in the right part of the world. The reveal map still draws the true
distance, which is where proximity feedback lives.

### State

`js/state.js` requires `initState(dayIndex)` before any other call. LocalStorage keys:

- `stadia_day_N` — game state for day N (rounds, scores, completion flag)
- `stadia_dayOffset` — dev-panel day offset; absent or `0` means today

Writes fall back to memory when LocalStorage is unavailable, so private-browsing
sessions degrade rather than break.

## Deployment

Netlify, publishing the repository root. See `netlify.toml`.
