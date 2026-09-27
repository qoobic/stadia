import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.apply_audit import apply_decisions, main


CANDIDATE = {
    "venue_id": "wembley-stadium-london-england-stadium",
    "canonical_name": "Wembley Stadium",
    "venue_class": "stadium",
    "status": "needs_imagery",
    "resolution_reason": "unique_class_specific_focal_geometry",
    "qid": "Q1",
    "osm_site_id": "way/2",
    "osm_focal_id": "way/3",
    "candidate_lat": 51.556,
    "candidate_lon": -0.2795,
    "uncertainty_m": 40,
    "derivation_method": "venue_outline_centroid",
}
MANUAL_RECORD = {
    "venue_id": "some-obscure-ground-nowhere-country-stadium",
    "canonical_name": "Some Obscure Ground",
    "venue_class": "stadium",
    "status": "manual_required",
    "resolution_reason": "wikidata_identity_unresolved",
}


class ApplyDecisionsTests(unittest.TestCase):
    def test_accept_marks_a_candidate_verified_after_imagery_audit(self):
        acceptance = {
            "venue_id": CANDIDATE["venue_id"],
            "decision": "accept",
            "audited_at": "2026-09-13T12:00:00Z",
        }

        result = apply_decisions([CANDIDATE], [acceptance])

        self.assertEqual(result[0]["status"], "verified")
        self.assertEqual(result[0]["final_lat"], CANDIDATE["candidate_lat"])
        self.assertEqual(result[0]["final_lon"], CANDIDATE["candidate_lon"])
        self.assertEqual(result[0]["audit_decision"], "accept")
        self.assertEqual(result[0]["audited_at"], "2026-09-13T12:00:00Z")

    def test_move_replaces_candidate_point_and_records_audit(self):
        move = {
            "venue_id": CANDIDATE["venue_id"],
            "decision": "move",
            "lat": 51.5560,
            "lon": -0.2796,
            "audited_at": "2026-09-13T12:05:00Z",
        }

        result = apply_decisions([CANDIDATE], [move])

        self.assertEqual(result[0]["status"], "verified")
        self.assertEqual(result[0]["final_lat"], move["lat"])
        self.assertEqual(result[0]["final_lon"], move["lon"])
        self.assertEqual(result[0]["audit_decision"], "move")
        self.assertEqual(result[0]["audited_at"], move["audited_at"])

    def test_reject_marks_record_manual_required_and_clears_coordinates(self):
        reject = {
            "venue_id": CANDIDATE["venue_id"],
            "decision": "reject",
            "audited_at": "2026-09-13T12:10:00Z",
        }

        result = apply_decisions([CANDIDATE], [reject])

        self.assertEqual(result[0]["status"], "manual_required")
        self.assertNotIn("final_lat", result[0])
        self.assertNotIn("final_lon", result[0])
        self.assertNotIn("candidate_lat", result[0])
        self.assertNotIn("candidate_lon", result[0])
        self.assertEqual(result[0]["audit_decision"], "reject")
        self.assertEqual(result[0]["audited_at"], reject["audited_at"])

    def test_accept_without_valid_provenance_stays_manual_required(self):
        acceptance = {
            "venue_id": MANUAL_RECORD["venue_id"],
            "decision": "accept",
            "audited_at": "2026-09-13T12:00:00Z",
        }

        result = apply_decisions([MANUAL_RECORD], [acceptance])

        self.assertEqual(result[0]["status"], "manual_required")
        self.assertNotEqual(result[0]["status"], "verified")

    def test_move_without_valid_provenance_stays_manual_required(self):
        move = {
            "venue_id": MANUAL_RECORD["venue_id"],
            "decision": "move",
            "lat": 10.0,
            "lon": 20.0,
            "audited_at": "2026-09-13T12:00:00Z",
        }

        result = apply_decisions([MANUAL_RECORD], [move])

        self.assertEqual(result[0]["status"], "manual_required")

    def test_incomplete_provenance_on_an_otherwise_auto_candidate_is_not_verified(self):
        missing_osm_focal = {**CANDIDATE}
        del missing_osm_focal["osm_focal_id"]
        acceptance = {
            "venue_id": CANDIDATE["venue_id"],
            "decision": "accept",
            "audited_at": "2026-09-13T12:00:00Z",
        }

        result = apply_decisions([missing_osm_focal], [acceptance])

        self.assertEqual(result[0]["status"], "manual_required")

    def test_records_without_a_matching_decision_are_returned_unchanged(self):
        result = apply_decisions([CANDIDATE], [])

        self.assertEqual(result[0], CANDIDATE)

    def test_move_decision_missing_coordinates_is_rejected(self):
        move = {
            "venue_id": CANDIDATE["venue_id"],
            "decision": "move",
            "audited_at": "2026-09-13T12:00:00Z",
        }

        with self.assertRaises(ValueError):
            apply_decisions([CANDIDATE], [move])

    def test_unknown_decision_value_is_rejected(self):
        bogus = {
            "venue_id": CANDIDATE["venue_id"],
            "decision": "approve",
            "audited_at": "2026-09-13T12:00:00Z",
        }

        with self.assertRaises(ValueError):
            apply_decisions([CANDIDATE], [bogus])

    def test_every_venue_id_is_preserved_exactly_once(self):
        decisions = [
            {"venue_id": CANDIDATE["venue_id"], "decision": "accept", "audited_at": "t"},
        ]

        result = apply_decisions([CANDIDATE, MANUAL_RECORD], decisions)

        self.assertEqual(
            sorted(row["venue_id"] for row in result),
            sorted([CANDIDATE["venue_id"], MANUAL_RECORD["venue_id"]]),
        )


class CliTests(unittest.TestCase):
    def test_cli_merges_decisions_and_writes_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records_path = root / "candidates.json"
            decisions_path = root / "decisions.json"
            output_path = root / "verified.json"
            records_path.write_text(
                json.dumps([CANDIDATE, MANUAL_RECORD]), encoding="utf-8"
            )
            decisions_path.write_text(json.dumps([
                {
                    "venue_id": CANDIDATE["venue_id"],
                    "decision": "accept",
                    "audited_at": "2026-09-13T12:00:00Z",
                },
            ]), encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main([
                    str(records_path), str(decisions_path), str(output_path),
                ])

            self.assertEqual(exit_code, 0)
            written = json.loads(output_path.read_text(encoding="utf-8"))
            by_id = {row["venue_id"]: row for row in written}
            self.assertEqual(by_id[CANDIDATE["venue_id"]]["status"], "verified")
            self.assertEqual(by_id[MANUAL_RECORD["venue_id"]]["status"], "manual_required")


if __name__ == "__main__":
    unittest.main()
