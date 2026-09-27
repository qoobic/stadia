# Stadia coordinate catalogue design

## Goal

Produce a reproducible, auditable catalogue of class-specific sporting-venue focal coordinates. A coordinate is eligible for the game only after independent verification.

## Scope

The source catalogue is `stadia-candidates.txt`. Its rows are converted into stable records, resolved to Wikidata and OpenStreetMap identities, and placed at a focal point rather than an address or venue centroid.

Focal points are:

- stadium: playing-surface centre
- arena: competition-floor centre
- circuit: current main-layout start/finish line
- racecourse: winning post on the racing surface
- golf course: 18th green centre

## Sources and identity

Wikidata is the identity anchor. Its coordinate is discovery data only. OpenStreetMap is the geometry source. A QID is accepted only after city/country matching plus one further discriminator such as sport, tenant, official site, capacity, image, or alias.

The pipeline stores raw source values separately from game coordinates. It snapshots OSM-derived input and records source timestamps and versions.

## Validation and review

The automated pipeline may produce `auto_candidate` and `manual_required` records, never `verified` records. Stadium and golf focal points must lie inside their selected pitch/green geometry; circuit points must be within 10 m of the main raceway centreline; a racecourse point must be inside the track surface or within 15 m of its centreline.

Reviewer A resolves identity and derives a point. Reviewer B independently repeats the selection from a different evidence chain. Their points must agree within 15 m for stadiums/arenas, 20 m for golf, and 25 m for circuits/racecourses. Disagreements are adjudicated, never averaged. A record with missing geometry or uncertain identity remains unresolved.

## Data products

`data/venues.json` is the parsed source catalogue. `data/coordinate-review.json` adds identifiers, raw source coordinates, final focal coordinates, provenance, validation flags, review outcomes, confidence, and status. `data/pilot-venues.json` is a deliberately diverse 25-row review queue.

## Constraints

- Use Python standard library for the initial parser and validation tooling.
- Preserve each source-line record even when unresolved.
- Do not use geocoder, address, clubhouse, entrance, building, site, or track centroids as a fallback game coordinate.
- Store coordinates in EPSG:4326 with at least six decimal places and an explicit uncertainty estimate.
- Only `verified` records can be exported to a playable dataset.
