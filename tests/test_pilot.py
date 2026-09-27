import unittest

from tools.pilot import FOCAL_DEFINITIONS, COUNTRY_REGIONS, select_pilot


SAMPLE_VENUES = [
    {
        "venue_id": f"{venue_class}-{index}",
        "canonical_name": f"{venue_class.title()} {index}",
        "city": f"City {index}",
        "country": country,
        "venue_class": venue_class,
        "source_line": index,
    }
    for index, (venue_class, country) in enumerate(
        [(venue_class, country) for venue_class in
         ("stadium", "arena", "circuit", "racecourse", "golf")
         for country in ("England", "United States", "Japan", "Qatar", "South Africa")],
        1,
    )
]


class PilotSelectionTests(unittest.TestCase):
    def test_pilot_contains_every_venue_class_and_is_limited_to_25_rows(self):
        pilot = select_pilot(SAMPLE_VENUES)
        self.assertEqual(len(pilot), 25)
        self.assertEqual(
            {row["venue_class"] for row in pilot},
            {"stadium", "arena", "circuit", "racecourse", "golf"},
        )

    def test_pilot_records_are_manual_and_have_empty_review_evidence(self):
        pilot = select_pilot(SAMPLE_VENUES)
        for row in pilot:
            self.assertTrue(row["focal_definition"])
            self.assertEqual(row["status"], "manual_required")
            self.assertEqual(row["reviewer_a_result"], "")
            self.assertEqual(row["reviewer_b_result"], "")
            self.assertEqual(row["reviewer_a_notes"], "")
            self.assertEqual(row["reviewer_b_notes"], "")

    def test_selection_is_order_invariant_and_spans_multiple_regions(self):
        pilot = select_pilot(SAMPLE_VENUES)
        shuffled = select_pilot(list(reversed(SAMPLE_VENUES)))
        self.assertEqual(pilot, shuffled)
        self.assertGreaterEqual(len({COUNTRY_REGIONS[row["country"]] for row in pilot}), 3)

    def test_focal_definitions_are_exact_for_each_class(self):
        for row in select_pilot(SAMPLE_VENUES):
            self.assertEqual(row["focal_definition"], FOCAL_DEFINITIONS[row["venue_class"]])


if __name__ == "__main__":
    unittest.main()
