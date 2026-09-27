import unittest
import math

from tools.review import can_export, validate_review


class ReviewValidationTests(unittest.TestCase):
    def test_complete_verified_record_can_be_exported(self):
        self.assertTrue(can_export({
            'status': 'verified', 'final_lat': 51.0, 'final_lon': -0.2,
            'reviewer_a_id': 'a', 'reviewer_a_evidence': 'source a',
            'reviewer_b_id': 'b', 'reviewer_b_evidence': 'source b',
            'reviewer_a_result': 'pass', 'reviewer_b_result': 'pass',
            'venue_class': 'stadium', 'reviewer_agreement_m': 10,
        }))
    def test_unverified_coordinate_cannot_be_exported(self):
        self.assertFalse(can_export({'status': 'manual_required'}))

    def test_verified_coordinate_requires_coordinate_and_two_reviews(self):
        errors = validate_review(
            {'status': 'verified', 'final_lat': 51.0, 'final_lon': -0.2}
        )
        self.assertIn('reviewer_a_result is required', errors)
        self.assertIn('reviewer_b_result is required', errors)

    def test_verified_record_requires_final_latitude(self):
        errors = validate_review(
            {
                'status': 'verified',
                'final_lon': -0.2,
                'reviewer_a_result': 'pass',
                'reviewer_b_result': 'pass',
            }
        )
        self.assertIn('final_lat is required', errors)

    def test_verified_record_requires_final_longitude(self):
        errors = validate_review(
            {
                'status': 'verified',
                'final_lat': 51.0,
                'reviewer_a_result': 'pass',
                'reviewer_b_result': 'pass',
            }
        )
        self.assertIn('final_lon is required', errors)

    def test_verified_record_requires_successful_reviewer_results(self):
        errors = validate_review(
            {
                'status': 'verified',
                'final_lat': 51.0,
                'final_lon': -0.2,
                'reviewer_a_result': 'fail',
                'reviewer_b_result': 'pending',
            }
        )
        self.assertIn('reviewer_a_result must be pass', errors)
        self.assertIn('reviewer_b_result must be pass', errors)

    def test_verified_record_rejects_out_of_range_coordinates(self):
        errors = validate_review(
            {
                'status': 'verified',
                'final_lat': 91,
                'final_lon': -181,
                'reviewer_a_result': 'pass',
                'reviewer_b_result': 'pass',
            }
        )
        self.assertIn('final_lat must be between -90 and 90', errors)
        self.assertIn('final_lon must be between -180 and 180', errors)

    def test_verified_record_rejects_non_numeric_coordinates(self):
        for value in (True, '51.0', math.nan, math.inf, -math.inf):
            errors = validate_review({'status': 'verified', 'final_lat': value,
                                      'final_lon': -0.2})
            self.assertIn('final_lat must be a finite number', errors)

    def test_verified_record_requires_distinct_reviewers_and_evidence(self):
        errors = validate_review({
            'status': 'verified', 'final_lat': 51.0, 'final_lon': -0.2,
            'reviewer_a_id': 'same', 'reviewer_b_id': 'same',
            'reviewer_a_evidence': '', 'reviewer_b_evidence': '',
        })
        self.assertIn('reviewer identifiers must be distinct', errors)
        self.assertIn('reviewer_a_evidence is required', errors)
        self.assertIn('reviewer_b_evidence is required', errors)

    def test_agreement_threshold_depends_on_venue_class(self):
        for venue_class, delta in (('stadium', 15), ('arena', 15),
                                   ('golf', 20), ('circuit', 25),
                                   ('racecourse', 25)):
            record = {'status': 'verified', 'final_lat': 51.0,
                      'final_lon': -0.2, 'reviewer_a_id': 'a',
                      'reviewer_b_id': 'b', 'reviewer_a_evidence': 'a',
                      'reviewer_b_evidence': 'b', 'venue_class': venue_class,
                      'reviewer_a_result': 'pass', 'reviewer_b_result': 'pass',
                      'reviewer_agreement_m': delta}
            self.assertTrue(can_export(record))
            record['reviewer_agreement_m'] = delta + 0.1
            self.assertFalse(can_export(record))

    def test_adjudication_can_approve_out_of_threshold_agreement(self):
        record = {'status': 'verified', 'final_lat': 51.0, 'final_lon': -0.2,
                  'reviewer_a_id': 'a', 'reviewer_b_id': 'b',
                  'reviewer_a_evidence': 'a', 'reviewer_b_evidence': 'b',
                  'reviewer_a_result': 'pass', 'reviewer_b_result': 'pass',
                  'venue_class': 'stadium', 'reviewer_agreement_m': 99,
                  'adjudication_result': 'pass'}
        self.assertTrue(can_export(record))


if __name__ == '__main__':
    unittest.main()
