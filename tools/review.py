"""Validation rules for coordinate review records."""

import math


def validate_review(record: dict) -> list[str]:
    """Return validation errors for a reviewed coordinate record."""
    if record.get('status') != 'verified':
        return []

    errors = []
    for field in ('final_lat', 'final_lon'):
        if field not in record or record[field] is None:
            errors.append(f'{field} is required')

    for field, minimum, maximum in (
        ('final_lat', -90, 90),
        ('final_lon', -180, 180),
    ):
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            if value is not None:
                errors.append(f'{field} must be a finite number')
            continue
        if not minimum <= value <= maximum:
            errors.append(f'{field} must be between {minimum} and {maximum}')

    reviewer_a = record.get('reviewer_a_id')
    reviewer_b = record.get('reviewer_b_id')
    if not reviewer_a:
        errors.append('reviewer_a_id is required')
    if not reviewer_b:
        errors.append('reviewer_b_id is required')
    if reviewer_a and reviewer_b and reviewer_a == reviewer_b:
        errors.append('reviewer identifiers must be distinct')
    for field in ('reviewer_a_evidence', 'reviewer_b_evidence'):
        if not isinstance(record.get(field), str) or not record[field].strip():
            errors.append(f'{field} is required')

    if record.get('adjudication_result') == 'pass':
        return errors

    limits = {'stadium': 15, 'arena': 15, 'golf': 20,
              'circuit': 25, 'racecourse': 25}
    venue_class = record.get('venue_class')
    agreement = record.get('reviewer_agreement_m')
    if venue_class not in limits:
        errors.append('venue_class is required or must be supported')
    elif isinstance(agreement, bool) or not isinstance(agreement, (int, float)) or not math.isfinite(agreement):
        errors.append('reviewer_agreement_m is required')
    elif agreement > limits[venue_class]:
        errors.append(f'reviewer agreement exceeds {limits[venue_class]}m for {venue_class}')

    for reviewer in ('reviewer_a_result', 'reviewer_b_result'):
        if not record.get(reviewer):
            errors.append(f'{reviewer} is required')
        elif record[reviewer] != 'pass':
            errors.append(f'{reviewer} must be pass')

    return errors


def can_export(record: dict) -> bool:
    """Return whether a record is eligible for playable export."""
    return record.get('status') == 'verified' and not validate_review(record)
