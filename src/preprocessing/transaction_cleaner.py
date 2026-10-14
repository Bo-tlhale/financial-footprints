"""Non-destructive cleaning helpers for extracted transaction records."""

import re
from datetime import date

CONTROL_CHARACTERS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
REPEATED_WHITESPACE = re.compile(r'\s+')


def normalize_posting_date(value):
    """Return a strict ISO posting date or raise a useful validation error."""
    text = str(value).strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f'invalid transaction_date: {value!r}') from exc
    return parsed.isoformat()


def normalize_effective_date(value):
    """Normalize an optional effective date without weakening posting-date checks."""
    text = '' if value is None else str(value).strip()
    if not text or text == '00/00/0000':
        return ''
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f'invalid effective_date: {value!r}') from exc
    return parsed.isoformat()


def clean_description(value):
    """Create a comparison-friendly description while preserving the source field."""
    text = '' if value is None else str(value)
    text = CONTROL_CHARACTERS.sub(' ', text)
    return REPEATED_WHITESPACE.sub(' ', text).strip().lower()


def clean_record(record):
    """Copy a source row, standardize dates and append a cleaned description."""
    cleaned = dict(record)
    cleaned['transaction_date'] = normalize_posting_date(record['transaction_date'])
    cleaned['effective_date'] = normalize_effective_date(record['effective_date'])
    cleaned['cleaned_description'] = clean_description(record['description'])
    return cleaned
