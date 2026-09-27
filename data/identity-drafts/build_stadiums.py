#!/usr/bin/env python3

import difflib
import html
import json
import re
import ssl
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = Path("/tmp/stadia-wikidata-cache.json")
API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "StadiaCatalogue/1.0 (Wikidata identity research)"}
SSL_CONTEXT = ssl._create_unverified_context()
GENERIC = {
    "arena", "centre", "center", "complex", "field", "ground", "national",
    "olympic", "park", "sports", "sport", "stadion", "stadium",
}


def normalise(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def meaningful_tokens(value):
    return {token for token in normalise(value).split() if token not in GENERIC}


def similarity(left, right):
    left_normalised = normalise(left)
    right_normalised = normalise(right)
    sequence = difflib.SequenceMatcher(None, left_normalised, right_normalised).ratio()
    left_tokens = meaningful_tokens(left)
    right_tokens = meaningful_tokens(right)
    token_score = (
        len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        if left_tokens and right_tokens else 0
    )
    return max(sequence, token_score)


def api(params, cache, delay=1.05):
    key = urllib.parse.urlencode(sorted((key, str(value)) for key, value in params.items()))
    if key in cache:
        return cache[key]
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(7):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, context=SSL_CONTEXT, timeout=45) as response:
                result = json.load(response)
            cache[key] = result
            CACHE_PATH.write_text(json.dumps(cache))
            time.sleep(delay)
            return result
        except urllib.error.HTTPError as error:
            if attempt == 6:
                raise
            retry_after = int(error.headers.get("Retry-After", "0"))
            time.sleep(max(retry_after + 5, min(60, 2 ** attempt)))
        except Exception:
            if attempt == 6:
                raise
            time.sleep(min(60, 2 ** attempt))


def load_remaining():
    venues = json.loads((ROOT / "data/venues.json").read_text())
    excluded = {
        row["venue_id"]
        for row in json.loads((ROOT / "data/pilot-venues.json").read_text())
    }
    for path in sorted((ROOT / "data/coordinate-drafts/batches").glob("*.json")):
        excluded.update(row["venue_id"] for row in json.loads(path.read_text()))
    return [
        row for row in venues
        if row.get("venue_class") == "stadium"
        and isinstance(row.get("venue_id"), str)
        and isinstance(row.get("canonical_name"), str)
        and isinstance(row.get("city"), str)
        and isinstance(row.get("country"), str)
        and row["venue_id"] not in excluded
    ]


def discover(venue, cache):
    candidates = {}
    searches = [
        ("fulltext", f'{venue["canonical_name"]} {venue["city"]}'),
    ]
    for source, query in searches:
        if source == "wbsearch":
            result = api({
                "action": "wbsearchentities", "format": "json", "language": "en",
                "uselang": "en", "type": "item", "limit": 10, "search": query,
            }, cache)
            rows = result.get("search", [])
            for rank, row in enumerate(rows):
                candidates.setdefault(row["id"], []).append((source, rank))
        else:
            result = api({
                "action": "query", "format": "json", "list": "search",
                "srnamespace": 0, "srlimit": 10, "srsearch": query,
            }, cache)
            rows = result.get("query", {}).get("search", [])
            for rank, row in enumerate(rows):
                if re.fullmatch(r"Q\d+", row["title"]):
                    candidates.setdefault(row["title"], []).append((source, rank))
    if not candidates:
        result = api({
            "action": "wbsearchentities", "format": "json", "language": "en",
            "uselang": "en", "type": "item", "limit": 10,
            "search": venue["canonical_name"],
        }, cache)
        for rank, row in enumerate(result.get("search", [])):
            candidates.setdefault(row["id"], []).append(("wbsearch", rank))
    return candidates


def get_entities(qids, cache):
    entities = {}
    qids = sorted(qids, key=lambda value: int(value[1:]))
    for offset in range(0, len(qids), 50):
        batch = qids[offset:offset + 50]
        result = api({
            "action": "wbgetentities", "format": "json", "ids": "|".join(batch),
            "props": "labels|descriptions|aliases|claims|sitelinks", "languages": "en",
            "sitefilter": "enwiki",
        }, cache)
        entities.update(result.get("entities", {}))
    return entities


def claim_values(entity, prop):
    values = []
    for claim in entity.get("claims", {}).get(prop, []):
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") != "value":
            continue
        value = snak.get("datavalue", {}).get("value")
        if value is not None:
            values.append(value)
    return values


def linked_qids(entity):
    result = set()
    for prop in ("P17", "P131"):
        for value in claim_values(entity, prop):
            if isinstance(value, dict) and "id" in value:
                result.add(value["id"])
    return result


def entity_text(entity, linked):
    parts = []
    for bucket in ("labels", "descriptions"):
        value = entity.get(bucket, {}).get("en", {}).get("value")
        if value:
            parts.append(value)
    parts.extend(alias["value"] for alias in entity.get("aliases", {}).get("en", []))
    title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
    if title:
        parts.append(title)
    for qid in linked_qids(entity):
        linked_entity = linked.get(qid, {})
        label = linked_entity.get("labels", {}).get("en", {}).get("value")
        description = linked_entity.get("descriptions", {}).get("en", {}).get("value")
        if label:
            parts.append(label)
        if description:
            parts.append(description)
    return " | ".join(parts)


def coordinate(entity):
    values = claim_values(entity, "P625")
    if not values:
        return None, None
    value = values[0]
    return value.get("latitude"), value.get("longitude")


def osm_id(entity):
    for prop, kind in (("P402", "relation"), ("P10689", "way"), ("P11693", "node")):
        values = claim_values(entity, prop)
        if values:
            return f"{kind}/{values[0]}"
    return None


def score_candidate(venue, entity, discoveries, linked):
    label = entity.get("labels", {}).get("en", {}).get("value", "")
    aliases = [alias["value"] for alias in entity.get("aliases", {}).get("en", [])]
    title = entity.get("sitelinks", {}).get("enwiki", {}).get("title", "")
    name_score = max([similarity(venue["canonical_name"], value) for value in [label, title] + aliases] or [0])
    text = normalise(entity_text(entity, linked))
    city_match = normalise(venue["city"]) in text
    country = normalise(venue["country"])
    country_match = country in text
    if country == "england":
        country_match = country_match or "united kingdom" in text
    if country in {"scotland", "wales"}:
        country_match = country_match or "united kingdom" in text
    search_bonus = max((max(0, 5 - rank) for _, rank in discoveries), default=0)
    lat, lon = coordinate(entity)
    score = name_score * 60 + search_bonus
    score += 22 if city_match else 0
    score += 10 if country_match else 0
    score += 4 if lat is not None and lon is not None else 0
    score += 4 if osm_id(entity) else 0
    return score, name_score, city_match, country_match


def make_row(venue, entity, score_data, linked):
    qid = entity["id"]
    score, name_score, city_match, country_match = score_data
    lat, lon = coordinate(entity)
    site_id = osm_id(entity)
    if name_score >= 0.88 and city_match and (country_match or site_id):
        confidence = "high"
    elif name_score >= 0.76 and (city_match or country_match):
        confidence = "medium"
    else:
        confidence = "low"
    evidence_url = (
        f"https://www.openstreetmap.org/{site_id}"
        if site_id else f"https://www.wikidata.org/wiki/{qid}"
    )
    match_parts = []
    if city_match:
        match_parts.append("city")
    if country_match:
        match_parts.append("country")
    if site_id:
        match_parts.append("Wikidata OSM identifier")
    context = ", ".join(match_parts) or "name/search context only"
    label = entity.get("labels", {}).get("en", {}).get("value", qid)
    return {
        "venue_id": venue["venue_id"],
        "qid": qid,
        "wd_lat": lat,
        "wd_lon": lon,
        "wd_source_url": f"https://www.wikidata.org/wiki/{qid}",
        "candidate_confidence": confidence,
        "osm_site_id": site_id,
        "identity_evidence_url": evidence_url,
        "notes": f'Candidate label "{label}" matched on {context}; Wikidata coordinates are raw discovery data only.',
    }


def unresolved_row(venue, note):
    return {
        "venue_id": venue["venue_id"],
        "qid": None,
        "wd_lat": None,
        "wd_lon": None,
        "wd_source_url": None,
        "candidate_confidence": "low",
        "osm_site_id": None,
        "identity_evidence_url": None,
        "notes": note,
    }


def main():
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    venues = load_remaining()
    discoveries = {venue["venue_id"]: discover(venue, cache) for venue in venues}
    all_qids = {qid for candidates in discoveries.values() for qid in candidates}
    entities = get_entities(all_qids, cache)
    direct_links = {qid for entity in entities.values() for qid in linked_qids(entity)}
    linked = get_entities(direct_links, cache)
    rows = []
    for venue in venues:
        ranked = []
        for qid, sources in discoveries[venue["venue_id"]].items():
            entity = entities.get(qid)
            if not entity or entity.get("missing") is not None:
                continue
            score_data = score_candidate(venue, entity, sources, linked)
            ranked.append((score_data[0], qid, score_data))
        ranked.sort(reverse=True)
        if not ranked:
            rows.append(unresolved_row(venue, "No plausible Wikidata candidate was discovered from canonical name, city, and country searches."))
            continue
        _, qid, score_data = ranked[0]
        if score_data[1] < 0.55 or (not score_data[2] and not score_data[3]):
            rows.append(unresolved_row(venue, "Wikidata search results did not provide a candidate with sufficient name and location agreement."))
            continue
        rows.append(make_row(venue, entities[qid], score_data, linked))
    output = ROOT / "data/identity-drafts/stadiums.json"
    output.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "rows": len(rows),
        "resolved": sum(row["qid"] is not None for row in rows),
        "high": sum(row["candidate_confidence"] == "high" for row in rows),
        "medium": sum(row["candidate_confidence"] == "medium" for row in rows),
        "low": sum(row["candidate_confidence"] == "low" for row in rows),
        "osm": sum(row["osm_site_id"] is not None for row in rows),
    }, indent=2))


if __name__ == "__main__":
    main()
