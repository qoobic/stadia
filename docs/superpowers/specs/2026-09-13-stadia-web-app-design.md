# Stadia web app design

## Goal

A daily satellite-view sporting-venue guessing game. Five rounds per day, one fixed
satellite view per round, one guess each via autocomplete. The architecture is ported
from the sibling project Elevation (`/Users/james.hargreaves/Personal/elevation`),
adapted from city guessing to sporting venues.

This document covers the playable web app only. The coordinate catalogue and its
verification pipeline are specified separately in
`docs/superpowers/specs/2026-09-13-stadia-coordinates-design.md` and are owned by a
different workstream.

## Approach

Copy-and-adapt Elevation's eight ES modules into this repository.

Elevation is roughly 1,800 lines with no build step, no package manager, and no
framework. Forking it costs one rename sweep and leaves the two games with
independent futures. The alternatives were rejected:

- **Extract a shared core.** Introducing build tooling and a package boundary to two
  static hobby games, for the sake of one consumer, buys nothing today.
- **Generalise Elevation in place** behind a `city | venue` configuration. This
  couples two live deployments, so a change made for Stadia could break Elevation.

## Architecture

Static site, no build step. `index.html` loads Leaflet from CDN, the confetti library
from `assets/`, and `js/main.js` as an ES module. Everything else is plain ES modules
loaded by the browser.

```
index.html
css/style.css
js/{main,venues,state,score,share,map,picker,ui,analytics}.js
assets/confetti.min.js
data/sample-venues.json
tests/js/{test.html,runner.js,*.test.js}
netlify.toml
README.md
```

### Module responsibilities

| Module | Purpose | Depends on |
|---|---|---|
| `main.js` | Orchestration: load data, resolve the day, run five rounds, show summary | every other module |
| `venues.js` | Day arithmetic, daily venue selection, search index, fetch | none |
| `state.js` | LocalStorage persistence with in-memory fallback | none |
| `score.js` | Haversine distance and round scoring | none |
| `share.js` | Share-string construction and clipboard/share-sheet copy | none |
| `map.js` | Leaflet setup and the guess/reveal/summary map states | Leaflet |
| `picker.js` | Autocomplete input and suggestion list | `venues.js` |
| `ui.js` | DOM rendering for panel, summary, dev panel, celebration | `state.js`, `venues.js` |
| `analytics.js` | Google Analytics event wrapper | none |

Each module is independently testable. `map.js` and `ui.js` are the only modules that
touch the DOM directly; `main.js` is the only module that knows the shape of a round.

### Rename map from Elevation

| Elevation | Stadia |
|---|---|
| `js/cities.js` | `js/venues.js` |
| `loadCitiesData`, `selectTodayCities`, `buildCityIndex`, `searchCities` | `loadVenuesData`, `selectTodayVenues`, `buildVenueIndex`, `searchVenues` |
| `cities.json` | `data/sample-venues.json` |
| `elev_day_N`, `elev_dayOffset` | `stadia_day_N`, `stadia_dayOffset` |
| `elev:picker-changed` | `stadia:picker-changed` |
| `.elev-truth-label` | `.stadia-truth-label` |
| `#city-modal`, `#city-panel` | `#venue-modal`, `#venue-panel` |
| Who Knows Where cross-sell | Elevation cross-sell |
| Satellite-themed celebration phrases | Sport-themed celebration phrases |
| `G-K791CZTZHY` | `G-0TG7Q6L6GD` |
| `https://elevation-game.netlify.app` | `https://stadia-game.netlify.app` |

Elevation's analytics property ID must not appear anywhere in this repository.

## Data

### Daily selection

`data/sample-venues.json` holds five difficulty bands, `l1` through `l5`. Each day
selects one venue per band by `list[dayIndex % list.length]`, where
`dayIndex = daysSince(launchDate)` in UTC and day 0 is the launch date itself. Selection
is pure and deterministic: the same day index always yields the same five venues.

Bands are **difficulty tiers**, not venue classes:

- `l1` — globally iconic, unmistakable from the air
- `l2` — very well known internationally
- `l3` — well known to followers of the sport
- `l4` — recognisable regionally or to dedicated fans
- `l5` — obscure, or visually ambiguous from above

`venueClass` (`stadium`, `arena`, `circuit`, `racecourse`, `golf`) is metadata. It
drives the default zoom and the reveal display, and is reported to analytics. It plays
no part in selection, so any given day may serve any mix of classes.

This was chosen over one-round-per-class because class counts in the catalogue are
lopsided — 310 stadiums against 24 racecourses — which would rotate racecourses every
24 days and stadiums every 310, and because class does not track difficulty. A golf
course from orbit is nothing like Wembley.

### Record schema

```json
{
  "_temporary": true,
  "_warning": "TEMPORARY SAMPLE — approximate hand-entered coordinates, NOT verified. Replace with the verified export before launch.",
  "launchDate": "2026-09-13",
  "l1": [
    {
      "id": "wembley-stadium",
      "venueId": "wembley-stadium-london-england-stadium",
      "name": "Wembley Stadium",
      "city": "London",
      "country": "England",
      "venueClass": "stadium",
      "aliases": [],
      "lat": 51.556,
      "lng": -0.2796,
      "zoom": 16
    }
  ]
}
```

`id` is the app-level key used for exact-match scoring and state persistence. `venueId`
matches the catalogue's `venue_id` so that a verified export drops in by identifier
without a re-key. `aliases` carries sponsor and former names; it is indexed for search
from day one because retrofitting it into the data contract later is awkward.

Default starting zoom by class: stadium and arena 16–17, golf 14–15, circuit 13–14,
racecourse 14–15.

### The sample dataset is deliberately temporary

The catalogue pipeline currently holds zero `verified` records. `data/coordinate-drafts/`
contains `auto_candidate` and `manual_required` records, which are unresolved by design
and must not reach the game — `tools/review.py:can_export` gates playable export on
`status == 'verified'`.

Therefore `data/sample-venues.json` carries **hand-entered approximate coordinates**
for roughly 15 to 20 venues spread across the five bands, written for this app and
marked temporary in the file itself. No coordinate is copied out of
`data/coordinate-drafts/`, `data/venues.json`, or `data/pilot-venues.json`.

Two consequences are accepted and documented in the README rather than hidden:

1. A 15-to-20 venue autocomplete pool is small enough to solve by elimination. That is
   a property of the placeholder, not of the game.
2. The coordinates are approximate, so distances shown on reveal are indicative only.

The replacement path is a one-line change: `loadVenuesData` takes a URL, and the
verified export is expected to produce the same banded structure with `_temporary`
absent. Producing that export belongs to the catalogue workstream, not this app.

## Scoring

The Elevation formula is ported **unchanged**. Distance in kilometres converts to miles,
then:

```
n = max(1, ceil((-39 + sqrt(1521 + 8 * distMiles)) / 2))
distanceScore = max(0, 101 - n)
```

Per-round base, before the round multiplier:

- Exact venue (`pick.id === correct.id`): `base = distanceScore`, which is 100 at zero distance.
- Any wrong venue: `base = min(distanceScore + bonus, 90)`, where `bonus = 10` if the
  countries match, otherwise 0.

Round multipliers are `[1, 1, 2, 3, 3]`, so a perfect day is 1,000.

### Known consequence at venue scale

The band formula was tuned for city-scale distances. At venue scale it goes flat:

| Wrong guess, distance | distanceScore | Final, same country | Final, different country |
|---|---|---|---|
| 5 miles | 100 | 90 | 90 |
| 50 miles | 98 | 90 | 90 |
| 200 miles | 92 | 90 | 90 |
| 400 miles | 86 | 90 | 86 |
| 1,500 miles | 62 | 72 | 62 |

Every wrong guess within roughly 200 miles scores exactly 90, and every same-country
wrong guess within roughly 400 miles also scores exactly 90. Since the plausible
confusion set for a venue is "another stadium in the same city or country", the distance
term is effectively constant across near misses.

This is a deliberate choice, not an oversight. Stadia is a recognition game: you either
name the venue for full marks, or you score 90 for being in the right part of the world.
Near misses and same-region misses are not distinguished. The reveal still draws the
real distance on the map, which is where the proximity feedback lives.

The right-country bonus is retained for consistency with Elevation, but note that under
the 90 cap it only materialises beyond roughly 400 miles. `countryBonus()` returns the
*effective* bonus actually awarded, so it correctly reports 0 for near misses and the
UI shows nothing.

## Map

Esri World Imagery satellite tiles, as in Elevation.

**Guess state.** The map opens at the venue's own `zoom` with a minimum zoom of
`zoom - 3`, locked on the venue. Panning is disabled — both drag and keyboard — and
every zoom is anchored to the centre (`scrollWheelZoom: 'center'` and the same for
double-click and touch). The centre anchoring matters: without it, zooming toward the
pointer would let a player pan by repeatedly zooming in and out, reintroducing exactly
what disabling drag removes.

This replaces Elevation's square pan boundary, which existed only to bound panning and
is therefore redundant once panning is off.

The three-level zoom-out allowance is retained deliberately. Zooming out from a stadium
reveals its host city, which makes Stadia a geography game as well as a venue-recognition
game — venue recognition alone would be too hard. Zooming out is now the only way to see
the surroundings, so it carries the whole geography half of the game.

**Reveal state.** Panning and pointer-anchored zoom are restored, so the answer can be
explored freely. Green marker on the true venue with a name-and-location popup, yellow
marker on the guess, dashed line between them, bounds fitted to both. Longitude is
normalised to the nearest world copy so the line never wraps the long way round.

**Summary state.** All five truth/guess pairs drawn together, bounds fitted to all
points, free pan and zoom.

## Game flow

1. `main.js` initialises the map and modal, fetches `data/sample-venues.json`, builds the
   search index, and wires the picker.
2. Day index is computed from `launchDate` plus any dev-panel offset; today's five
   venues are selected.
3. State loads from LocalStorage. A missing, stale, or different-day state is replaced
   with a fresh one and `game_started` is sent.
4. Stored rounds are re-scored in place on load, so a scoring change corrects historical
   state rather than leaving it stale.
5. Rounds run in sequence. Each round: reset map and picker, show the guess view, await a
   submission, score it, persist it, reveal, then auto-advance after four seconds or on click.
6. After round five the game is marked complete, `game_completed` is sent, the summary
   renders, and the celebration fires at 950 or above.

`Cmd/Ctrl+Enter` triggers the primary button wherever it is enabled.

## State

`state.js` requires `initState(dayIndex)` before any other call. Keys:

- `stadia_day_N` — game state for day N: rounds, scores, completion flag
- `stadia_dayOffset` — dev-panel offset; absent or `0` means today

Writes fall back to an in-memory object when LocalStorage is unavailable or throws, so
private-browsing sessions degrade rather than break.

Three invariants guard multi-tab and reload races, and are covered by regression tests
ported from Elevation: a round index already recorded is ignored, writes after
completion are ignored, and rounds are hard-capped at five.

## Sharing

```
https://stadia-game.netlify.app #<N>
<pct><emoji> <pct><emoji> <pct><emoji> <pct><emoji> <pct><emoji>
Final score: <total>
```

Day number is 1-based. The URL comes first so chat apps auto-linkify it. Each cell shows
that round's percentage of its multiplier-adjusted maximum. The emoji ladder is
re-themed from travel to sport, keeping Elevation's banding thresholds so the two games'
grids remain visually comparable.

Copy prefers the native share sheet, then the async clipboard API, then a hidden
textarea and `execCommand`. A failure surfaces the raw string for manual copying.

## Analytics

`analytics.js` wraps `gtag` and no-ops to `console.log` on localhost, `127.0.0.1`, empty
hostname, or any URL containing `?dev`.

Google Analytics property 553967923, stream 15770061674, measurement ID `G-0TG7Q6L6GD`.

Events: `game_started`, `round_completed`, `game_completed`, `share_copied`.
`round_completed` carries day and round index, band, target and guessed venue id/name/
city/country, `venue_class`, distance, score, multiplier, `is_exact_match`,
`country_match`, and `country_bonus`.

### Celebration

At 950 or above, an overlay fires canvas-confetti with sport-shaped particles built via
`confetti.shapeFromText` — one emoji per venue class plus a few of the sports those
venues host (football, American football, rugby, tennis, horse, F1 car, golf,
basketball, cricket). Emoji particles need a larger `scalar` than default confetti to
stay legible and fewer particles to stay cheap, since each is a rendered glyph rather
than a coloured rectangle. They also set `flat: true`, which disables the tilt-and-wobble
tumble: paper confetti reads well spinning edge-on, but an emoji rendered edge-on is an
unreadable sliver. Shapes are built once and cached. A canvas-confetti build
without `shapeFromText` falls back to plain confetti rather than failing.

## Error handling

- **Data fetch fails** — a fatal message renders in the panel and the footer hides. The
  game does not half-start.
- **Empty band** — `selectTodayVenues` throws with the offending band name, surfaced
  through the same fatal path.
- **LocalStorage unavailable** — in-memory fallback; the session works but does not persist.
- **Unknown id in stored state** — re-scoring skips the round and keeps its stored score
  rather than discarding progress.
- **Clipboard failure** — the share string is shown for manual copying.

## Testing

`tests/` already holds the catalogue workstream's Python suite (`test_catalogue.py`,
`test_pilot.py`, `test_review.py`). The JS harness therefore lives in **`tests/js/`**
with its own `test.html`, so the two suites never collide.

Ported from Elevation: `runner.js` and the `smoke`, `score`, `state`, `regression`,
`share`, and `picker` suites, plus `cities.test.js` renamed to `venues.test.js`.

Added for Stadia:

- **Alias search** — a venue is findable by a sponsor or former name.
- **Sample-data integrity** — every band non-empty; `id` unique across all bands;
  `lat` in [-90, 90] and `lng` in [-180, 180]; `zoom` present and an integer; `venueId`
  present; `_temporary` flag present. The last assertion fails loudly if real data is
  swapped in without removing the placeholder marker.

Run the JS suite at `http://localhost:8000/tests/js/test.html`. The Python suite runs
unchanged via its own runner. The README documents both.

## Deployment

Netlify, publishing the repository root. Security headers (`X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`) and `max-age=0, must-revalidate`
on `/`, `index.html`, `js/*`, `css/*`, and `data/*` so a deploy is picked up on the next
load rather than served stale.

## Out of scope

- Producing verified coordinates, or any change to `tools/`, `data/venues.json`,
  `data/pilot-venues.json`, `data/coordinate-drafts/`, `stadia-candidates.txt`, or the
  coordinate documentation.
- The verified-export step that will eventually replace the sample dataset.
- Accounts, server-side state, leaderboards, and streaks.
