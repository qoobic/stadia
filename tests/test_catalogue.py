import unittest
import json
import tempfile
from pathlib import Path

from tools.catalogue import parse_catalogue


class CatalogueTests(unittest.TestCase):
    def test_parse_catalogue_preserves_source_fields_and_generates_stable_id(self):
        rows = parse_catalogue('Wembley Stadium | London | England | stadium\n')
        self.assertEqual(rows, [{
            'venue_id': 'wembley-stadium-london-england-stadium',
            'canonical_name': 'Wembley Stadium',
            'city': 'London',
            'country': 'England',
            'venue_class': 'stadium',
            'source_line': 1,
        }])

    def test_skips_blank_and_indented_comments_preserving_source_line(self):
        rows = parse_catalogue("\n  # comment\nA | B | C | arena\n")
        self.assertEqual(rows[0]["source_line"], 3)

    def test_retains_malformed_rows_and_continues(self):
        rows = parse_catalogue("bad row\nA | B | C | arena\n")
        self.assertEqual(rows[0]["source_line"], 1)
        self.assertEqual(rows[0]["raw_source_line"], "bad row")
        self.assertEqual(rows[0]["status"], "parse_error")
        self.assertEqual(rows[1]["canonical_name"], "A")

    def test_rejects_lossy_slug_collisions_with_source_lines(self):
        with self.assertRaisesRegex(ValueError, r"lines 1 and 2"):
            parse_catalogue("A&B | C | D | stadium\nA B | C | D | stadium\n")

    def test_write_catalogue_outputs_json(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            output = Path(directory) / "venues.json"
            source.write_text("A | B | C | arena\n", encoding="utf-8")
            from tools.catalogue import write_catalogue
            write_catalogue(str(source), str(output))
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))[0]["venue_id"], "a-b-c-arena")
