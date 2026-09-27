"""Find exact-name OSM venue features for manual coordinate review."""

import argparse
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ENDPOINT = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "stadia-coordinate-review/1.0"


def normalise(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def request_for(venue):
    query = ", ".join((venue["canonical_name"], venue["city"], venue["country"]))
    parameters = urllib.parse.urlencode({
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "namedetails": 1,
        "extratags": 1,
        "limit": 10,
    })
    url = f"{ENDPOINT}?{parameters}"
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def exact_stadium_rows(venue, response):
    canonical_name = normalise(venue["canonical_name"])
    matches = []
    for row in response:
        if not isinstance(row, dict) or normalise(row.get("type")) != "stadium":
            continue
        names = [row.get("name")]
        namedetails = row.get("namedetails")
        if isinstance(namedetails, dict):
            names.extend(namedetails.values())
        if canonical_name in {normalise(name) for name in names if name}:
            matches.append(row)
    non_nodes = [row for row in matches if row.get("osm_type") != "node"]
    if len(non_nodes) == 1:
        return non_nodes[0]
    return matches[0] if len(matches) == 1 else None


def read_cache_or_fetch(request, cache_path, next_allowed):
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    delay = next_allowed - time.monotonic()
    if delay > 0:
        time.sleep(delay)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            retry_after = error.headers.get("Retry-After", "60")
            try:
                time.sleep(max(1.0, float(retry_after)))
            except ValueError:
                time.sleep(60)
        raise
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def resolve(venue, cache_dir, next_allowed):
    request = request_for(venue)
    request_hash = hashlib.sha256(request.full_url.encode("utf-8")).hexdigest()
    cache_path = cache_dir / "nominatim-candidates-v1" / f"{request_hash}.json"
    result = dict(venue)
    result["focal_definition"] = "playing-surface centre"
    try:
        response = read_cache_or_fetch(request, cache_path, next_allowed)
        matches = exact_stadium_rows(venue, response if isinstance(response, list) else [])
        if matches is None:
            result.update(status="manual_required", resolution_reason="no_unique_exact_osm_stadium_match")
            return result, time.monotonic() + 1.0
        lat, lon = float(matches["lat"]), float(matches["lon"])
        osm_type, osm_id = matches.get("osm_type"), matches.get("osm_id")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and osm_type and osm_id):
            result.update(status="manual_required", resolution_reason="invalid_osm_point")
            return result, time.monotonic() + 1.0
        osm_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        result.update(
            candidate_lat=lat,
            candidate_lon=lon,
            osm_site_id=f"{osm_type}/{osm_id}",
            status="manual_required",
            resolution_reason="exact_name_osm_stadium_feature",
            derivation_method="Nominatim OSM stadium representative point; place marker on playing surface",
            identity_evidence_url=osm_url,
            focal_evidence_url=osm_url,
            source_snapshots={
                "nominatim": {
                    "source": "Nominatim",
                    "url": request.full_url,
                    "cache_file": cache_path.as_posix(),
                }
            },
            attribution="© OpenStreetMap contributors",
        )
    except (OSError, ValueError, urllib.error.URLError) as error:
        result.update(status="manual_required", resolution_reason="nominatim_request_failed", resolution_error=str(error))
    return result, time.monotonic() + 1.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args()
    venues = json.loads(args.input.read_text(encoding="utf-8"))
    results = []
    next_allowed = time.monotonic()
    for venue in venues:
        result, next_allowed = resolve(venue, args.cache_dir, next_allowed)
        results.append(result)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
        if result.get("candidate_lat") is not None:
            print(f"candidate: {venue['canonical_name']}", flush=True)
    print(f"Resolved {len(results)} records; {sum('candidate_lat' in row for row in results)} candidates")


if __name__ == "__main__":
    main()
