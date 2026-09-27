"""Serve the coordinate finder and apply reviewed venues to the live dataset."""

import json
import math
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LIVE_PATH = ROOT / "data" / "live-venues.json"
CATALOGUE_PATH = ROOT / "data" / "venues.json"
MANIFEST_PATH = ROOT / "tools" / "coordinate-queues.json"
WRITE_LOCK = Lock()
BANDS = ("l1", "l2", "l3", "l4", "l5")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/live":
            self._send_json(200, _read_json(LIVE_PATH))
            return
        if path == "/api/queues":
            self._send_json(200, _queue_manifest())
            return
        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/apply":
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 1 or content_length > 65536:
                raise ValueError("request body must be between 1 byte and 64 KB")
            payload = json.loads(self.rfile.read(content_length))
            result = _apply_to_live(payload)
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
            return
        except OSError as error:
            self._send_json(500, {"error": "could not write the live venue data: " + str(error)})
            return
        self._send_json(200, result)

    def _send_json(self, status, value):
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _queue_manifest():
    manifest = _read_json(MANIFEST_PATH)
    live = _read_json(LIVE_PATH)
    for queue in manifest:
        data = live if queue["type"] == "live" else _read_queue_data(queue)
        if queue["type"] == "live":
            queue["total_count"] = sum(len(data.get(band, [])) for band in BANDS)
            queue["point_count"] = sum(
                1 for band in BANDS for record in data.get(band, [])
                if _valid_coordinate(record.get("lat"), record.get("lng"))
            )
        else:
            queue["total_count"] = len(data)
            queue["point_count"] = sum(
                1 for record in data
                if _valid_coordinate(record.get("candidate_lat"), record.get("candidate_lon"))
            )
    return manifest


def _read_queue_data(queue):
    path = (ROOT / "tools" / queue["url"]).resolve()
    if ROOT not in path.parents:
        raise ValueError("queue path must stay inside the working folder")
    return _read_json(path)


def _apply_to_live(payload):
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    queue_id = payload.get("queue_id")
    venue_id = payload.get("venue_id")
    difficulty = payload.get("difficulty")
    lat = payload.get("lat")
    lon = payload.get("lon")
    if not isinstance(queue_id, str) or not isinstance(venue_id, str):
        raise ValueError("queue_id and venue_id are required")
    if not _valid_coordinate(lat, lon):
        raise ValueError("latitude or longitude is invalid")
    if isinstance(difficulty, bool) or not isinstance(difficulty, int) or difficulty not in range(1, 6):
        raise ValueError("difficulty must be an integer from 1 to 5")

    manifest = _read_json(MANIFEST_PATH)
    queue = next((item for item in manifest if item.get("id") == queue_id), None)
    if not queue:
        raise ValueError("unknown queue")

    live = _read_json(LIVE_PATH)
    existing = _find_live_venue(live, venue_id)
    if queue["type"] == "live":
        if existing is None:
            raise ValueError("venue is no longer in the live dataset")
        source = existing["record"]
    else:
        records = _read_queue_data(queue)
        source = next((record for record in records if record.get("venue_id") == venue_id), None)
        if source is None or not _valid_coordinate(source.get("candidate_lat"), source.get("candidate_lon")):
            raise ValueError("venue is not a mappable item in the selected queue")

    catalogue = _read_json(CATALOGUE_PATH)
    metadata = next((record for record in catalogue if record.get("venue_id") == venue_id), {})
    band = "l" + str(difficulty)
    audited_at = payload.get("audited_at")

    if existing:
        venue = dict(existing["record"])
        venue["lat"] = lat
        venue["lng"] = lon
        venue["venueId"] = venue.get("venueId") or venue_id
        venue["venueClass"] = venue.get("venueClass") or source.get("venue_class") or metadata.get("venue_class", "stadium")
    else:
        name = source.get("canonical_name") or source.get("name") or metadata.get("canonical_name")
        city = source.get("city") or metadata.get("city")
        country = source.get("country") or metadata.get("country")
        if not name or not city or not country:
            raise ValueError("venue name, city, and country are required")
        venue_class = source.get("venue_class") or source.get("venueClass") or metadata.get("venue_class", "stadium")
        venue = {
            "id": venue_id,
            "venueId": venue_id,
            "name": name,
            "city": city,
            "country": country,
            "venueClass": venue_class,
            "aliases": source.get("aliases", []),
            "lat": lat,
            "lng": lon,
            "zoom": 16,
        }

    if audited_at:
        venue["coordinate_review"] = {"decision": "apply", "audited_at": audited_at}

    for current_band in BANDS:
        live[current_band] = [
            record for record in live.get(current_band, [])
            if record.get("venueId") != venue_id and record.get("id") != venue_id
        ]
    live[band].append(venue)
    _write_json_atomic(LIVE_PATH, live)

    return {
        "venue_id": venue_id,
        "name": venue["name"],
        "difficulty": difficulty,
        "already_live": existing is not None,
        "action": "updated" if existing else "added",
    }


def _find_live_venue(live, venue_id):
    matches = [
        (band, record)
        for band in BANDS
        for record in live.get(band, [])
        if record.get("venueId") == venue_id or record.get("id") == venue_id
    ]
    if len(matches) > 1:
        raise ValueError("venue appears more than once in live data; resolve duplicates first")
    return {"band": matches[0][0], "record": matches[0][1]} if matches else None


def _write_json_atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with WRITE_LOCK:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)


def _valid_coordinate(lat, lon):
    return (
        _finite_number(lat) and _finite_number(lon)
        and -90 <= lat <= 90 and -180 <= lon <= 180
    )


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Coordinate finder listening at http://localhost:8000/tools/audit.html")
    server.serve_forever()
