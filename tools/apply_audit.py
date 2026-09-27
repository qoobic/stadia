"""Merge imagery-audit decisions into resolver candidate records."""

import argparse
import json
import math
from pathlib import Path

VALID_DECISIONS = frozenset({"accept", "move", "reject", "unknown"})
PROVENANCE_FIELDS = ("qid", "osm_site_id", "osm_focal_id", "candidate_lat", "candidate_lon")
CANDIDATE_COORDINATE_FIELDS = ("candidate_lat", "candidate_lon", "final_lat", "final_lon")


def apply_decisions(records: list[dict] | dict, decisions: list[dict]) -> list[dict] | dict:
    by_id = {decision["venue_id"]: decision for decision in decisions}
    if isinstance(records, dict):
        outcome = dict(records)
        for band in ("l1", "l2", "l3", "l4", "l5"):
            if isinstance(records.get(band), list):
                outcome[band] = [
                    _apply_live_one(record, by_id.get(record.get("venueId") or record.get("id")))
                    for record in records[band]
                ]
        return outcome
    return [_apply_one(record, by_id.get(record.get("venue_id"))) for record in records]


def _apply_live_one(record: dict, decision: dict | None) -> dict:
    if decision is None:
        return dict(record)

    kind = decision.get("decision")
    if kind not in VALID_DECISIONS:
        raise ValueError(f"unknown audit decision: {kind!r}")

    outcome = dict(record)
    outcome["coordinate_review"] = {
        "decision": kind,
        "audited_at": decision.get("audited_at"),
    }
    if kind == "move":
        lat, lon = decision.get("lat"), decision.get("lon")
        if not _is_finite_coordinate(lat) or not _is_finite_coordinate(lon):
            raise ValueError("move decision requires numeric lat/lon")
        outcome["lat"] = lat
        outcome["lng"] = lon
    elif kind == "reject":
        outcome.pop("lat", None)
        outcome.pop("lng", None)
    return outcome


def _apply_one(record: dict, decision: dict | None) -> dict:
    if decision is None:
        return dict(record)

    kind = decision.get("decision")
    if kind not in VALID_DECISIONS:
        raise ValueError(f"unknown audit decision: {kind!r}")

    outcome = dict(record)
    outcome["audit_decision"] = kind
    outcome["audited_at"] = decision.get("audited_at")

    if kind == "reject":
        for field in CANDIDATE_COORDINATE_FIELDS:
            outcome.pop(field, None)
        outcome["status"] = "manual_required"
        outcome["resolution_reason"] = "imagery_audit_rejected"
        return outcome

    if kind == "unknown":
        outcome.pop("final_lat", None)
        outcome.pop("final_lon", None)
        outcome["status"] = "manual_required"
        outcome["resolution_reason"] = "imagery_audit_unknown"
        return outcome

    if kind == "accept":
        lat, lon = record.get("candidate_lat"), record.get("candidate_lon")
    else:
        lat, lon = decision.get("lat"), decision.get("lon")
        if not _is_finite_coordinate(lat) or not _is_finite_coordinate(lon):
            raise ValueError("move decision requires numeric lat/lon")

    outcome["final_lat"] = lat
    outcome["final_lon"] = lon

    if _has_valid_provenance(record):
        outcome["status"] = "verified"
        outcome["resolution_reason"] = (
            "imagery_audit_accepted" if kind == "accept" else "imagery_audit_repositioned"
        )
    else:
        outcome["status"] = "manual_required"
        outcome["resolution_reason"] = "imagery_audit_missing_provenance"

    return outcome


def _has_valid_provenance(record: dict) -> bool:
    if any(not record.get(field) for field in PROVENANCE_FIELDS):
        return False
    return _is_finite_coordinate(record["candidate_lat"]) and _is_finite_coordinate(
        record["candidate_lon"]
    )


def _is_finite_coordinate(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    records = json.loads(arguments.records.read_text(encoding="utf-8"))
    decisions = json.loads(arguments.decisions.read_text(encoding="utf-8"))
    merged = apply_decisions(records, decisions)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
