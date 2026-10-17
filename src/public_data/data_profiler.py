"""Streaming profile counters for the processed public expenditure data."""

from collections import Counter
from decimal import Decimal

from .expenditure_cleaner import OUTPUT_COLUMNS


class ExpenditureProfiler:
    def __init__(self):
        self.rows = 0
        self.households = set()
        self.keys = set()
        self.duplicate_household_coicop_rows = 0
        self.missing_adjusted_values = 0
        self.missing_weighted_values = 0
        self.zero_adjusted_values = 0
        self.missing_geography_rows = 0
        self.coicop_types = Counter()
        self.divisions = Counter()
        self.comparability = Counter()
        self.mapping_rules = Counter()
        self.missing_values = Counter()
        self.coicop_codes = set()
        self.unmapped_coicop_codes = set()
        self.minimum_adjusted_value = None
        self.maximum_adjusted_value = None
        self.codebook_status = Counter()
        self.codebook_exception_codes = set()

    def add(self, row):
        self.rows += 1
        self.households.add(row['uqno'])
        key = (row['uqno'], row['coicop'])
        if key in self.keys:
            self.duplicate_household_coicop_rows += 1
        self.keys.add(key)
        if row['valueannualized_adj'] == '':
            self.missing_adjusted_values += 1
        elif Decimal(row['valueannualized_adj']) == 0:
            self.zero_adjusted_values += 1
        if row['valueannualized_adj'] != '':
            amount = Decimal(row['valueannualized_adj'])
            if self.minimum_adjusted_value is None or amount < self.minimum_adjusted_value:
                self.minimum_adjusted_value = amount
            if self.maximum_adjusted_value is None or amount > self.maximum_adjusted_value:
                self.maximum_adjusted_value = amount
        if row['valueannualized_adj_wgt'] == '':
            self.missing_weighted_values += 1
        if not row['province']:
            self.missing_geography_rows += 1
        self.coicop_types[row['coicop_type']] += 1
        self.divisions[row['division']] += 1
        self.comparability[row['comparability']] += 1
        self.mapping_rules[row['mapping_rule_id'] or 'unmapped'] += 1
        self.coicop_codes.add(row['coicop'])
        if not row['mapping_rule_id']:
            self.unmapped_coicop_codes.add(row['coicop'])
        self.codebook_status[row['codebook_match_status']] += 1
        if row['codebook_match_status'] != 'matched':
            self.codebook_exception_codes.add(row['coicop'])
        for field in OUTPUT_COLUMNS:
            if row[field] == '':
                self.missing_values[field] += 1

    def report(self):
        return {
            'row_count': self.rows,
            'household_count': len(self.households),
            'duplicate_household_coicop_rows': self.duplicate_household_coicop_rows,
            'duplicate_policy': (
                'Reported, not removed: repeated household/COICOP records can reflect '
                'separate expenditure observations and require source-specific review.'),
            'missing_adjusted_values': self.missing_adjusted_values,
            'missing_weighted_values': self.missing_weighted_values,
            'zero_adjusted_values': self.zero_adjusted_values,
            'minimum_adjusted_value': (
                None if self.minimum_adjusted_value is None
                else format(self.minimum_adjusted_value, 'f')),
            'maximum_adjusted_value': (
                None if self.maximum_adjusted_value is None
                else format(self.maximum_adjusted_value, 'f')),
            'missing_geography_rows': self.missing_geography_rows,
            'coicop_type_counts': dict(sorted(self.coicop_types.items())),
            'division_counts': dict(sorted(self.divisions.items())),
            'comparability_counts': dict(sorted(self.comparability.items())),
            'mapping_rule_counts': dict(sorted(self.mapping_rules.items())),
            'unique_coicop_code_count': len(self.coicop_codes),
            'unmapped_coicop_codes': sorted(self.unmapped_coicop_codes),
            'codebook_match_status_counts': dict(sorted(self.codebook_status.items())),
            'codebook_exception_codes': sorted(self.codebook_exception_codes),
            'missing_value_counts': {
                field: self.missing_values[field] for field in OUTPUT_COLUMNS
            },
        }
