"""Conservatively resolve venue identities and class-specific OSM focal points."""

import argparse
import hashlib
import json
import math
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


WIKIDATA_ENDPOINT = "https://www.wikidata.org/w/api.php"
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "stadia-coordinate-resolver/1.0"
WIKIDATA_SEARCH_CACHE_VERSION = "v2-name-only"
QID_PATTERN = re.compile(r"Q[1-9][0-9]*\Z")

COUNTRY_ALIASES = {
    "czechia": ("czechia", "czech republic"),
    "england": ("england", "united kingdom", "uk"),
    "northern ireland": ("northern ireland", "united kingdom", "uk"),
    "scotland": ("scotland", "united kingdom", "uk"),
    "south korea": ("south korea", "republic of korea"),
    "turkiye": ("turkiye", "turkey"),
    "united states": ("united states", "united states of america", "usa", "us"),
    "wales": ("wales", "united kingdom", "uk"),
}
CLASS_DESCRIPTION_TERMS = {
    "stadium": ("stadium", "sports ground", "sports venue", "ballpark"),
    "arena": ("arena", "indoor stadium", "indoor sports venue"),
    "circuit": ("circuit", "motor racing", "motorsport", "race track", "racetrack"),
    "racecourse": ("racecourse", "horse racing", "horse racetrack"),
    "golf": ("golf",),
}
DISCONTINUED_DESCRIPTION_TERMS = (
    "closed",
    "defunct",
    "demolished",
    "destroyed",
    "disused",
    "former",
)
FOCAL_DEFINITIONS = {
    "stadium": "playing-surface centre",
    "arena": "competition-floor centre",
    "circuit": "current main-layout start/finish line",
    "racecourse": "winning post on the racing surface",
    "golf": "18th green centre",
}


class JsonHttpClient:
    def __init__(
        self,
        *,
        timeout: float = 90,
        max_retries: int = 5,
        backoff_base: float = 2,
        request_interval: float = 1,
        opener=urllib.request.urlopen,
        sleep=time.sleep,
        monotonic=time.monotonic,
        wall_time=time.time,
    ):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if isinstance(max_retries, bool) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        if backoff_base < 0:
            raise ValueError("backoff_base must be non-negative")
        if request_interval < 0:
            raise ValueError("request_interval must be non-negative")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.request_interval = request_interval
        self.opener = opener
        self.sleep = sleep
        self.monotonic = monotonic
        self.wall_time = wall_time
        self.last_request_started_at = None

    def fetch(self, request: urllib.request.Request) -> dict:
        for retry_number in range(self.max_retries + 1):
            self._pace_request()
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    value = json.load(response)
                if not isinstance(value, dict):
                    raise ValueError(f"expected an object from {request.full_url}")
                return value
            except urllib.error.HTTPError as error:
                if not self._is_retryable(error) or retry_number >= self.max_retries:
                    raise
                self.sleep(self._retry_delay(error, retry_number))
        raise RuntimeError("retry loop exhausted")

    def _pace_request(self) -> None:
        now = self.monotonic()
        if self.last_request_started_at is not None:
            remaining = self.request_interval - (now - self.last_request_started_at)
            if remaining > 0:
                self.sleep(remaining)
        self.last_request_started_at = self.monotonic()

    @staticmethod
    def _is_retryable(error: urllib.error.HTTPError) -> bool:
        return error.code == 429 or 500 <= error.code <= 599

    def _retry_delay(
        self, error: urllib.error.HTTPError, retry_number: int
    ) -> float:
        exponential = self.backoff_base * (2 ** retry_number)
        retry_after = self._retry_after_seconds(error.headers.get("Retry-After"))
        return max(exponential, retry_after or 0)

    def _retry_after_seconds(self, value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, parsed.timestamp() - self.wall_time())


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?:^| ){re.escape(_normalise(phrase))}(?: |$)", text))


def _mentions_location(text: object, place: str) -> bool:
    target = _normalise(place)
    if not target:
        return False
    segments = {_normalise(part) for part in re.split(r"[,;()]", str(text or ""))}
    if target in segments:
        return True
    normalised_text = _normalise(text)
    return any(
        _contains_phrase(normalised_text, f"{preposition} {target}")
        for preposition in ("in", "at", "near")
    )


def build_wikidata_request(
    venue: dict, endpoint: str = WIKIDATA_ENDPOINT
) -> urllib.request.Request:
    search = str(venue.get("canonical_name", "")).strip()
    if not search:
        raise ValueError("canonical_name is required")
    parameters = urllib.parse.urlencode({
        "action": "wbsearchentities",
        "search": search,
        "language": "en",
        "uselang": "en",
        "type": "item",
        "limit": 10,
        "format": "json",
    })
    return urllib.request.Request(
        f"{endpoint}?{parameters}", headers={"User-Agent": USER_AGENT}
    )


def score_wikidata_candidate(venue: dict, candidate: dict) -> int | None:
    canonical_name = _normalise(venue.get("canonical_name"))
    aliases = candidate.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [aliases]
    names = [_normalise(candidate.get("label")), *map(_normalise, aliases)]
    if not canonical_name or canonical_name not in names:
        return None

    raw_description = candidate.get("description")
    description = _normalise(raw_description)
    if any(
        _contains_phrase(description, term)
        for term in DISCONTINUED_DESCRIPTION_TERMS
    ):
        return None
    city = _normalise(venue.get("city"))
    country = _normalise(venue.get("country"))
    country_names = COUNTRY_ALIASES.get(country, (country,))
    if not city or not _mentions_location(raw_description, city):
        return None
    if not country or not any(
        _mentions_location(raw_description, name) for name in country_names
    ):
        return None

    venue_class = venue.get("venue_class")
    terms = CLASS_DESCRIPTION_TERMS.get(venue_class)
    if not terms or not any(_contains_phrase(description, term) for term in terms):
        return None

    discriminators = venue.get("identity_discriminators", [])
    if isinstance(discriminators, str):
        discriminators = [discriminators]
    if not isinstance(discriminators, list) or not any(
        isinstance(discriminator, str)
        and _contains_phrase(description, discriminator)
        for discriminator in discriminators
    ):
        return None

    label_score = 100 if canonical_name == names[0] else 95
    return label_score + 40 + 25


def select_wikidata_candidate(venue: dict, response: dict) -> dict | None:
    scored = []
    for candidate in response.get("search", []):
        if not isinstance(candidate, dict) or not QID_PATTERN.fullmatch(
            str(candidate.get("id", ""))
        ):
            continue
        score = score_wikidata_candidate(venue, candidate)
        if score is not None:
            scored.append((score, candidate))
    if len(scored) != 1:
        return None
    return scored[0][1]


def build_overpass_query(qid: str, venue_class: str) -> str:
    if not QID_PATTERN.fullmatch(qid):
        raise ValueError(f"invalid Wikidata QID: {qid!r}")
    selectors = {
        "stadium": ('["leisure"="pitch"]',),
        "arena": (
            '["leisure"="pitch"]["indoor"="yes"]',
            '["leisure"="pitch"]["location"="indoor"]',
        ),
        "golf": ('["golf"="green"]',),
        "circuit": (
            '["raceway"="start_finish"]',
            '["raceway"="start-finish"]',
            '["raceway"="start/finish"]',
        ),
        "racecourse": (
            '["horse_racing"="winning_post"]',
            '["horse_racing"="finish"]',
            '["raceway"="finish"]',
            '["racing"="finish"]',
        ),
    }
    if venue_class not in selectors:
        raise ValueError(f"unsupported venue class: {venue_class!r}")
    setup = ""
    if venue_class in {"stadium", "arena", "golf"}:
        scope = "area.venueArea"
        setup = ".venue map_to_area -> .venueArea;\n"
    elif venue_class == "circuit":
        scope = "around.mainTrack:10"
        setup = (
            "(\n"
            '  way.venue["highway"="raceway"]["service"!="pit_lane"];\n'
            '  way(around.venue:50)["highway"="raceway"]'
            '["service"!="pit_lane"];\n'
            ")->.mainTrack;\n"
        )
    else:
        scope = "around.mainTrack:15"
        setup = (
            "(\n"
            '  nwr.venue["leisure"="track"]["sport"="horse_racing"];\n'
            '  nwr.venue["horse_racing"="track"];\n'
            '  nwr(around.venue:50)["leisure"="track"]'
            '["sport"="horse_racing"];\n'
            '  nwr(around.venue:50)["horse_racing"="track"];\n'
            ")->.mainTrack;\n"
        )
    focal_queries = "\n".join(
        f"  nwr({scope}){selector};" for selector in selectors[venue_class]
    )
    main_track_output = (
        "  .mainTrack;\n" if venue_class in {"circuit", "racecourse"} else ""
    )
    return "".join((
        "[out:json][timeout:60];\n",
        f'nwr["wikidata"="{qid}"]->.venue;\n',
        setup,
        "(\n",
        "  .venue;\n",
        main_track_output,
        f"{focal_queries}\n",
        ");\n",
        "out meta geom;",
    ))


def overpass_to_geojson(response: dict) -> dict:
    if response.get("type") == "FeatureCollection":
        return response
    features = []
    for element in response.get("elements", []):
        element_type = element.get("type")
        osm_id = element.get("id")
        tags = element.get("tags", {})
        properties = {
            **tags,
            "osm_id": f"{element_type}/{osm_id}",
            **{
                f"osm_{field}": element[field]
                for field in ("version", "timestamp", "changeset", "uid", "user")
                if field in element
            },
        }
        geometry = None
        if element_type == "node" and _valid_lon_lat(
            element.get("lon"), element.get("lat")
        ):
            geometry = {
                "type": "Point",
                "coordinates": [element["lon"], element["lat"]],
            }
        elif element_type == "way" and isinstance(element.get("geometry"), list):
            coordinates = [
                [point.get("lon"), point.get("lat")]
                for point in element["geometry"]
                if _valid_lon_lat(point.get("lon"), point.get("lat"))
            ]
            is_linear_track = (
                tags.get("highway") == "raceway"
                or tags.get("leisure") == "track"
                or tags.get("horse_racing") == "track"
            ) and tags.get("area") != "yes"
            if (
                len(coordinates) >= 4
                and coordinates[0] == coordinates[-1]
                and not is_linear_track
            ):
                geometry = {"type": "Polygon", "coordinates": [coordinates]}
            elif len(coordinates) >= 2:
                geometry = {"type": "LineString", "coordinates": coordinates}
        if geometry is None:
            if (
                element_type in {"node", "way", "relation"}
                and isinstance(osm_id, int)
                and QID_PATTERN.fullmatch(str(tags.get("wikidata", "")))
            ):
                features.append({
                    "type": "Feature",
                    "properties": properties,
                    "geometry": None,
                })
            continue
        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
        })
    return {"type": "FeatureCollection", "features": features}


def derive_focal_candidates(venue_class: str, geojson: dict) -> list[dict]:
    if venue_class not in FOCAL_DEFINITIONS:
        raise ValueError(f"unsupported venue class: {venue_class!r}")
    candidates = []
    tracks = _main_track_features(venue_class, geojson)
    for feature in geojson.get("features", []):
        geometry = feature.get("geometry") or {}
        properties = _feature_properties(feature)
        if not _matches_focal_rule(venue_class, geometry.get("type"), properties):
            continue
        point = _geometry_focal_point(geometry)
        if point is None:
            continue
        track_match = None
        if venue_class in {"circuit", "racecourse"}:
            track_match = _nearest_track(point, tracks)
            tolerance = 10 if venue_class == "circuit" else 15
            if track_match is None or track_match[0] > tolerance:
                continue
        lon, lat = point
        osm_id = properties.get("osm_id") or properties.get("@id") or feature.get("id")
        if not isinstance(osm_id, str) or not re.fullmatch(
            r"(?:node|way|relation)/[0-9]+", osm_id
        ):
            continue
        candidate = {
            "osm_focal_id": osm_id,
            "candidate_lat": round(lat, 7),
            "candidate_lon": round(lon, 7),
            "coordinate_system": "EPSG:4326",
            "uncertainty_m": 5 if geometry["type"] != "LineString" else 10,
            "focal_definition": FOCAL_DEFINITIONS[venue_class],
            "derivation_method": _derivation_method(venue_class, geometry["type"]),
            "osm_tags": {
                key: value for key, value in properties.items()
                if key != "osm_id"
                and not key.startswith(("osm_", "@"))
            },
        }
        _copy_element_metadata(candidate, "osm_focal", properties)
        if track_match is not None:
            distance, track_id, track_properties = track_match
            candidate["osm_track_id"] = track_id
            candidate["track_distance_m"] = round(distance, 2)
            _copy_element_metadata(candidate, "osm_track", track_properties)
        candidates.append(candidate)
    return sorted(candidates, key=lambda row: row["osm_focal_id"])


def _copy_element_metadata(target: dict, prefix: str, properties: dict) -> None:
    for field in ("version", "timestamp", "changeset", "uid", "user"):
        value = properties.get(
            f"osm_{field}", properties.get(f"@{field}", properties.get(field))
        )
        if value is not None:
            target[f"{prefix}_{field}"] = value


def _main_track_features(venue_class: str, geojson: dict) -> list[tuple]:
    if venue_class not in {"circuit", "racecourse"}:
        return []
    tracks = []
    for feature in geojson.get("features", []):
        geometry = feature.get("geometry") or {}
        properties = _feature_properties(feature)
        geometry_type = geometry.get("type")
        if geometry_type not in {"LineString", "Polygon"}:
            continue
        if venue_class == "circuit":
            raceway = _normalise(properties.get("raceway"))
            is_track = (
                properties.get("highway") == "raceway"
                and _normalise(properties.get("service")) != "pit lane"
                and raceway not in {"pit lane", "start finish", "finish"}
            )
        else:
            is_track = (
                properties.get("leisure") == "track"
                and _tag_contains(properties.get("sport"), "horse racing")
            ) or _normalise(properties.get("horse_racing")) == "track"
        if not is_track:
            continue
        osm_id = properties.get("osm_id") or properties.get("@id") or feature.get("id")
        if isinstance(osm_id, str) and re.fullmatch(
            r"(?:node|way|relation)/[0-9]+", osm_id
        ):
            tracks.append((osm_id, geometry, properties))
    return tracks


def _tag_contains(value: object, expected: str) -> bool:
    return _normalise(expected) in {
        _normalise(part) for part in re.split(r"[;,]", str(value or ""))
    }


def _nearest_track(
    point: tuple[float, float], tracks: list[tuple]
) -> tuple[float, str, dict] | None:
    matches = []
    for osm_id, geometry, properties in tracks:
        distance = _point_to_geometry_distance_m(point, geometry)
        if distance is not None:
            matches.append((distance, osm_id, properties))
    return min(matches, key=lambda item: (item[0], item[1])) if matches else None


def _point_to_geometry_distance_m(
    point: tuple[float, float], geometry: dict
) -> float | None:
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "LineString":
        return _point_to_line_distance_m(point, coordinates)
    if geometry.get("type") != "Polygon" or not coordinates:
        return None
    if _point_in_ring(point, coordinates[0]) and not any(
        _point_in_ring(point, hole) for hole in coordinates[1:]
    ):
        return 0.0
    distances = [
        _point_to_line_distance_m(point, ring) for ring in coordinates
    ]
    distances = [distance for distance in distances if distance is not None]
    return min(distances) if distances else None


def _point_to_line_distance_m(
    point: tuple[float, float], coordinates: list
) -> float | None:
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    if not all(_coordinate_pair(coordinate) for coordinate in coordinates):
        return None
    lon, lat = point
    radius = 6_371_008.8
    latitude_scale = math.pi * radius / 180
    longitude_scale = latitude_scale * math.cos(math.radians(lat))
    projected = [
        ((coordinate[0] - lon) * longitude_scale,
         (coordinate[1] - lat) * latitude_scale)
        for coordinate in coordinates
    ]
    distances = []
    for first, second in zip(projected, projected[1:]):
        dx = second[0] - first[0]
        dy = second[1] - first[1]
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            distances.append(math.hypot(first[0], first[1]))
            continue
        fraction = max(0.0, min(1.0, -(first[0] * dx + first[1] * dy) / length_squared))
        closest_x = first[0] + fraction * dx
        closest_y = first[1] + fraction * dy
        distances.append(math.hypot(closest_x, closest_y))
    return min(distances) if distances else None


def _feature_properties(feature: dict) -> dict:
    properties = feature.get("properties") or {}
    tags = properties.get("tags")
    if isinstance(tags, dict):
        return {**tags, **{key: value for key, value in properties.items() if key != "tags"}}
    return properties


def _matches_focal_rule(venue_class: str, geometry_type: str, tags: dict) -> bool:
    if venue_class == "stadium":
        return geometry_type == "Polygon" and tags.get("leisure") == "pitch"
    if venue_class == "arena":
        return (
            geometry_type == "Polygon"
            and tags.get("leisure") == "pitch"
            and (tags.get("indoor") == "yes" or tags.get("location") == "indoor")
        )
    if venue_class == "golf":
        reference = _normalise(tags.get("ref") or tags.get("hole"))
        name = _normalise(tags.get("name"))
        return (
            geometry_type == "Polygon"
            and tags.get("golf") == "green"
            and (reference == "18" or "18th green" in name or name == "green 18")
        )
    if venue_class == "circuit":
        values = {
            _normalise(tags.get("raceway")),
            _normalise(tags.get("motor_racing")),
        }
        return geometry_type in {"Point", "LineString"} and bool(
            values & {"start finish"}
        )
    values = {
        _normalise(tags.get("horse_racing")),
        _normalise(tags.get("raceway")),
        _normalise(tags.get("racing")),
    }
    return geometry_type in {"Point", "LineString"} and bool(
        values & {"winning post", "finish"}
    )


def _geometry_focal_point(geometry: dict) -> tuple[float, float] | None:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point":
        if _coordinate_pair(coordinates):
            return coordinates[0], coordinates[1]
        return None
    if geometry_type == "LineString":
        return _line_midpoint(coordinates)
    if geometry_type != "Polygon" or not isinstance(coordinates, list) or not coordinates:
        return None
    ring = coordinates[0]
    point = _polygon_centroid(ring)
    if point is None or not _point_in_ring(point, ring):
        return None
    for hole in coordinates[1:]:
        if _point_in_ring(point, hole):
            return None
    return point


def _polygon_centroid(ring: list) -> tuple[float, float] | None:
    if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
        return None
    area_twice = 0.0
    x_sum = 0.0
    y_sum = 0.0
    for first, second in zip(ring, ring[1:]):
        if not _coordinate_pair(first) or not _coordinate_pair(second):
            return None
        cross = first[0] * second[1] - second[0] * first[1]
        area_twice += cross
        x_sum += (first[0] + second[0]) * cross
        y_sum += (first[1] + second[1]) * cross
    if abs(area_twice) < 1e-15:
        return None
    return x_sum / (3 * area_twice), y_sum / (3 * area_twice)


def _point_in_ring(point: tuple[float, float], ring: list) -> bool:
    x, y = point
    inside = False
    for first, second in zip(ring, ring[1:]):
        x1, y1 = first
        x2, y2 = second
        if (y1 > y) != (y2 > y):
            intersection = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection:
                inside = not inside
    return inside


def _line_midpoint(coordinates: list) -> tuple[float, float] | None:
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    if not all(_coordinate_pair(point) for point in coordinates):
        return None
    lengths = [
        math.hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(coordinates, coordinates[1:])
    ]
    total = sum(lengths)
    if total == 0:
        return None
    remaining = total / 2
    for first, second, length in zip(coordinates, coordinates[1:], lengths):
        if remaining <= length:
            fraction = remaining / length
            return (
                first[0] + (second[0] - first[0]) * fraction,
                first[1] + (second[1] - first[1]) * fraction,
            )
        remaining -= length
    return coordinates[-1][0], coordinates[-1][1]


def _coordinate_pair(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and _valid_lon_lat(value[0], value[1])
    )


def _valid_lon_lat(lon: object, lat: object) -> bool:
    return (
        not isinstance(lon, bool)
        and not isinstance(lat, bool)
        and isinstance(lon, (int, float))
        and isinstance(lat, (int, float))
        and math.isfinite(lon)
        and math.isfinite(lat)
        and -180 <= lon <= 180
        and -90 <= lat <= 90
    )


def _derivation_method(venue_class: str, geometry_type: str) -> str:
    if geometry_type == "Polygon":
        return f"OSM {venue_class} focal polygon geometric centre"
    if geometry_type == "LineString":
        return f"OSM {venue_class} explicit focal line midpoint"
    return f"OSM {venue_class} explicit focal node"


def _manual_record(venue: dict, reason: str, **fields: object) -> dict:
    record = dict(venue)
    for coordinate in ("candidate_lat", "candidate_lon", "final_lat", "final_lon"):
        record.pop(coordinate, None)
    record.update(fields)
    record["status"] = "manual_required"
    record["resolution_reason"] = reason
    return record


def _osm_site_ids(qid: str, geojson: dict) -> list[str]:
    site_ids = set()
    for feature in geojson.get("features", []):
        properties = _feature_properties(feature)
        osm_id = properties.get("osm_id") or properties.get("@id") or feature.get("id")
        if (
            properties.get("wikidata") == qid
            and isinstance(osm_id, str)
            and re.fullmatch(r"(?:node|way|relation)/[0-9]+", osm_id)
        ):
            site_ids.add(osm_id)
    return sorted(site_ids)


def _osm_feature_properties(osm_id: str, geojson: dict) -> dict:
    for feature in geojson.get("features", []):
        properties = _feature_properties(feature)
        feature_id = properties.get("osm_id") or properties.get("@id") or feature.get("id")
        if feature_id == osm_id:
            return properties
    return {}


def resolve_record(
    venue: dict, wikidata_response: dict, osm_geojson: dict | None
) -> dict:
    identity = select_wikidata_candidate(venue, wikidata_response)
    if identity is None:
        return _manual_record(venue, "wikidata_identity_unresolved")
    qid = identity["id"]
    identity_fields = {
        "qid": qid,
        "wd_source_url": f"https://www.wikidata.org/wiki/{qid}",
        "wikidata_label": identity.get("label", ""),
        "wikidata_description": identity.get("description", ""),
        "identity_score": score_wikidata_candidate(venue, identity),
    }
    if osm_geojson is None:
        return _manual_record(venue, "osm_snapshot_unavailable", **identity_fields)
    site_ids = _osm_site_ids(qid, osm_geojson)
    if not site_ids:
        return _manual_record(venue, "osm_identity_unresolved", **identity_fields)
    if len(site_ids) > 1:
        return _manual_record(
            venue,
            "osm_identity_ambiguous",
            **identity_fields,
            osm_identity_count=len(site_ids),
        )
    identity_fields["osm_site_id"] = site_ids[0]
    _copy_element_metadata(
        identity_fields,
        "osm_site",
        _osm_feature_properties(site_ids[0], osm_geojson),
    )
    candidates = derive_focal_candidates(venue["venue_class"], osm_geojson)
    if not candidates:
        return _manual_record(venue, "focal_geometry_unresolved", **identity_fields)
    if len(candidates) > 1:
        return _manual_record(
            venue,
            "focal_geometry_ambiguous",
            **identity_fields,
            focal_candidate_count=len(candidates),
        )
    record = dict(venue)
    record.update(identity_fields)
    record.update(candidates[0])
    record["status"] = "auto_candidate"
    record["resolution_reason"] = "unique_class_specific_focal_geometry"
    return record


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_or_fetch(
    cache_path: Path,
    request: urllib.request.Request,
    offline: bool,
    refresh: bool,
    http_client: JsonHttpClient,
) -> dict | None:
    if cache_path.exists() and not refresh:
        value = _read_json(cache_path)
        return value if isinstance(value, dict) else None
    if offline:
        return None
    value = http_client.fetch(request)
    _write_json(cache_path, value)
    return value


def _overpass_request(query: str, endpoint: str) -> urllib.request.Request:
    return urllib.request.Request(
        endpoint,
        data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )


def _snapshot_metadata(
    cache_path: Path,
    cache_dir: Path,
    payload: dict,
    source: str,
    request: dict,
) -> dict:
    metadata = {
        "source": source,
        "cache_key": cache_path.relative_to(cache_dir).as_posix(),
        "retrieved_at": datetime.fromtimestamp(
            cache_path.stat().st_mtime, timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "request": request,
        "raw_source_metadata": {
            key: value for key, value in payload.items()
            if key not in {"search", "elements"}
        },
    }
    if source == "OpenStreetMap":
        osm_base = payload.get("osm3s", {}).get("timestamp_osm_base")
        if osm_base:
            metadata["osm_base_timestamp"] = osm_base
    return metadata


def _overpass_cache_path(
    cache_dir: Path, qid: str, venue_class: str, query: str
) -> tuple[Path, str]:
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return (
        cache_dir / "overpass" / f"{qid}-{venue_class}-{query_hash}.json",
        query_hash,
    )


def _wikidata_cache_path(
    cache_dir: Path, venue_id: str, request: urllib.request.Request
) -> tuple[Path, str]:
    query_hash = hashlib.sha256(request.full_url.encode("utf-8")).hexdigest()
    return (
        cache_dir / "wikidata"
        / f"{venue_id}-{WIKIDATA_SEARCH_CACHE_VERSION}-{query_hash}.json",
        query_hash,
    )


def run_pipeline(
    input_path: str | Path,
    output_path: str | Path,
    cache_dir: str | Path,
    *,
    offline: bool = False,
    resume: bool = False,
    refresh: bool = False,
    request_timeout: float = 90,
    max_retries: int = 5,
    backoff_base: float = 2,
    request_interval: float = 1,
    http_client: JsonHttpClient | None = None,
    wikidata_endpoint: str = WIKIDATA_ENDPOINT,
    overpass_endpoint: str = OVERPASS_ENDPOINT,
) -> list[dict]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    cache_dir = Path(cache_dir)
    if http_client is None:
        http_client = JsonHttpClient(
            timeout=request_timeout,
            max_retries=max_retries,
            backoff_base=backoff_base,
            request_interval=request_interval,
        )
    venues = _read_json(input_path)
    if not isinstance(venues, list):
        raise ValueError("input must be a JSON array")

    if resume and output_path.exists():
        prior = _read_json(output_path)
        if not isinstance(prior, list):
            raise ValueError("resume output must be a JSON array")
        results = prior
    else:
        results = []
    completed = {
        row.get("venue_id") for row in results
        if isinstance(row, dict) and row.get("venue_id")
    }

    for venue in venues:
        if not isinstance(venue, dict):
            continue
        venue_id = venue.get("venue_id")
        if not venue_id:
            results.append(dict(venue))
            _write_json(output_path, results)
            continue
        if venue_id in completed:
            continue
        try:
            wikidata_request = build_wikidata_request(venue, wikidata_endpoint)
            wikidata_path, wikidata_query_hash = _wikidata_cache_path(
                cache_dir, venue_id, wikidata_request
            )
            wikidata = _load_or_fetch(
                wikidata_path,
                wikidata_request,
                offline,
                refresh,
                http_client,
            )
            if wikidata is None:
                result = _manual_record(venue, "wikidata_snapshot_unavailable")
            else:
                source_snapshots = {
                    "wikidata": _snapshot_metadata(
                        wikidata_path,
                        cache_dir,
                        wikidata,
                        "Wikidata",
                        {
                            "method": wikidata_request.get_method(),
                            "url": wikidata_request.full_url,
                            "query_sha256": wikidata_query_hash,
                        },
                    )
                }
                identity = select_wikidata_candidate(venue, wikidata)
                if identity is None:
                    result = resolve_record(venue, wikidata, None)
                else:
                    qid = identity["id"]
                    overpass_query = build_overpass_query(
                        qid, venue["venue_class"]
                    )
                    overpass_path, query_hash = _overpass_cache_path(
                        cache_dir, qid, venue["venue_class"], overpass_query
                    )
                    overpass_request = _overpass_request(
                        overpass_query, overpass_endpoint
                    )
                    overpass = _load_or_fetch(
                        overpass_path,
                        overpass_request,
                        offline,
                        refresh,
                        http_client,
                    )
                    geojson = overpass_to_geojson(overpass) if overpass is not None else None
                    result = resolve_record(venue, wikidata, geojson)
                    if overpass is not None:
                        source_snapshots["osm"] = _snapshot_metadata(
                            overpass_path,
                            cache_dir,
                            overpass,
                            "OpenStreetMap",
                            {
                                "method": overpass_request.get_method(),
                                "url": overpass_request.full_url,
                                "query_sha256": query_hash,
                            },
                        )
                result["source_snapshots"] = source_snapshots
        except (OSError, ValueError, json.JSONDecodeError) as error:
            result = _manual_record(
                venue, "source_request_failed", resolution_error=str(error)
            )
        results.append(result)
        completed.add(venue_id)
        _write_json(output_path, results)
    if not output_path.exists():
        _write_json(output_path, results)
    return results


def _positive_finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return parsed


def _nonnegative_finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve venue identities and strict OSM focal candidates."
    )
    parser.add_argument("input", type=Path, help="source venue JSON array")
    parser.add_argument("output", type=Path, help="resolved JSON array")
    parser.add_argument(
        "--cache-dir", type=Path, required=True,
        help="directory for raw Wikidata and Overpass response snapshots",
    )
    parser.add_argument(
        "--offline", action="store_true", help="read cache only; make no network requests"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--resume", action="store_true", help="retain output rows already written"
    )
    mode.add_argument(
        "--refresh", action="store_true", help="replace cached responses"
    )
    parser.add_argument(
        "--request-timeout", type=_positive_finite_float, default=90,
        help="HTTP request timeout in seconds (default: 90)",
    )
    parser.add_argument(
        "--max-retries", type=_nonnegative_int, default=5,
        help="retries for HTTP 429 and 5xx responses (default: 5)",
    )
    parser.add_argument(
        "--backoff-base", type=_nonnegative_finite_float, default=2,
        help="initial exponential retry delay in seconds (default: 2)",
    )
    parser.add_argument(
        "--request-interval", type=_nonnegative_finite_float, default=1,
        help="minimum interval between request starts (default: 1)",
    )
    parser.add_argument("--wikidata-endpoint", default=WIKIDATA_ENDPOINT)
    parser.add_argument("--overpass-endpoint", default=OVERPASS_ENDPOINT)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    run_pipeline(
        arguments.input,
        arguments.output,
        arguments.cache_dir,
        offline=arguments.offline,
        resume=arguments.resume,
        refresh=arguments.refresh,
        request_timeout=arguments.request_timeout,
        max_retries=arguments.max_retries,
        backoff_base=arguments.backoff_base,
        request_interval=arguments.request_interval,
        wikidata_endpoint=arguments.wikidata_endpoint,
        overpass_endpoint=arguments.overpass_endpoint,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
