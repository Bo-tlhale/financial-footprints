"""Configuration, schema and integrity validation for categorisation."""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.preprocessing.transaction_validator import (
    CLASSIFICATION_METHODS as MOVEMENT_CLASSIFICATION_METHODS,
    OUTPUT_COLUMNS as PREPROCESSED_COLUMNS,
    MOVEMENT_TYPES,
    parse_money,
)
from src.preprocessing.transaction_cleaner import (
    clean_description,
    normalize_effective_date,
    normalize_posting_date,
)

ADDED_COLUMNS = [
    'clean_merchant',
    'category',
    'subcategory',
    'classification_method',
    'classification_confidence',
    'category_review_required',
    'spending_classification_status',
]
OUTPUT_COLUMNS = [*PREPROCESSED_COLUMNS, *ADDED_COLUMNS]
REVIEW_COLUMNS = [
    'transaction_id',
    'transaction_date',
    'original_description',
    'clean_merchant',
    'movement_type',
    'suggested_category',
    'suggested_subcategory',
    'classification_method',
    'classification_confidence',
    'review_required',
    'reviewed_merchant',
    'reviewed_category',
    'reviewed_subcategory',
    'review_status',
    'review_notes',
    'decision_version',
]
CLASSIFICATION_METHODS = {
    'merchant_rule', 'transaction_rule', 'movement_exclusion', 'unclassified',
}
CONFIDENCE_LEVELS = {'high', 'medium', 'low', 'unknown'}
SPENDING_STATUSES = {'applicable', 'not_applicable', 'requires_review'}
MATCH_TYPES = {'exact', 'regex'}


class CategoryValidationError(ValueError):
    """Raised when categorisation cannot safely continue."""


@dataclass(frozen=True)
class MerchantRule:
    rule_id: str
    pattern: str
    match_type: str
    merchant: str
    category: str
    subcategory: str
    confidence: str
    priority: int
    review_required: bool
    explanation: str

    @property
    def specificity(self):
        return len(self.pattern)


def _load_yaml(path):
    path = Path(path)
    if not path.is_file():
        raise CategoryValidationError(f'configuration file does not exist: {path}')
    try:
        with path.open(encoding='utf-8') as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        raise CategoryValidationError(f'invalid YAML configuration: {path}') from exc
    if not isinstance(data, dict):
        raise CategoryValidationError(f'configuration must be a mapping: {path}')
    return data


def load_category_hierarchy(path):
    data = _load_yaml(path)
    if data.get('version') != 1 or not isinstance(data.get('categories'), list):
        raise CategoryValidationError('category configuration must use version 1')
    hierarchy = {}
    for index, item in enumerate(data['categories'], start=1):
        if not isinstance(item, dict):
            raise CategoryValidationError(f'category {index} must be a mapping')
        name = str(item.get('name') or '').strip()
        subcategories = item.get('subcategories')
        if not name or not isinstance(subcategories, list) or not subcategories:
            raise CategoryValidationError(
                f'category {index} requires a name and non-empty subcategories'
            )
        cleaned = tuple(str(value).strip() for value in subcategories)
        if any(not value for value in cleaned) or len(set(cleaned)) != len(cleaned):
            raise CategoryValidationError(f'category {name!r} has invalid subcategories')
        if name in hierarchy:
            raise CategoryValidationError(f'duplicate category: {name}')
        hierarchy[name] = frozenset(cleaned)
    return hierarchy


def load_merchant_rules(path, hierarchy):
    data = _load_yaml(path)
    if data.get('version') != 1 or not isinstance(data.get('rules'), list):
        raise CategoryValidationError('merchant-rule configuration must use version 1')
    rules = []
    ids = set()
    fingerprints = {}
    for index, item in enumerate(data['rules'], start=1):
        if not isinstance(item, dict):
            raise CategoryValidationError(f'merchant rule {index} must be a mapping')
        rule_id = str(item.get('id') or '').strip()
        pattern = str(item.get('pattern') or '').strip()
        match_type = str(item.get('match_type') or '').strip()
        merchant = str(item.get('merchant') or '').strip()
        category = str(item.get('category') or '').strip()
        subcategory = str(item.get('subcategory') or '').strip()
        confidence = str(item.get('confidence') or '').strip()
        priority = item.get('priority')
        review_required = item.get('review_required', False)
        explanation = str(item.get('explanation') or '').strip()
        if not rule_id or rule_id in ids:
            raise CategoryValidationError(f'invalid or duplicate merchant rule id: {rule_id!r}')
        if not pattern or match_type not in MATCH_TYPES or not merchant:
            raise CategoryValidationError(f'merchant rule {rule_id!r} is incomplete')
        if confidence not in CONFIDENCE_LEVELS:
            raise CategoryValidationError(f'merchant rule {rule_id!r} has invalid confidence')
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise CategoryValidationError(f'merchant rule {rule_id!r} needs integer priority')
        if not isinstance(review_required, bool):
            raise CategoryValidationError(f'merchant rule {rule_id!r} has invalid review flag')
        if bool(category) != bool(subcategory):
            raise CategoryValidationError(
                f'merchant rule {rule_id!r} must set both category and subcategory'
            )
        if category and (category not in hierarchy or subcategory not in hierarchy[category]):
            raise CategoryValidationError(f'merchant rule {rule_id!r} uses an invalid category')
        if match_type == 'regex':
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise CategoryValidationError(
                    f'merchant rule {rule_id!r} has invalid regex'
                ) from exc
        fingerprint = (match_type, pattern.casefold())
        outcome = (merchant, category, subcategory)
        if fingerprint in fingerprints:
            prior_id, prior_outcome = fingerprints[fingerprint]
            label = 'conflicting' if prior_outcome != outcome else 'duplicate'
            raise CategoryValidationError(
                f'{label} merchant rules: {prior_id!r} and {rule_id!r}'
            )
        fingerprints[fingerprint] = (rule_id, outcome)
        ids.add(rule_id)
        rules.append(MerchantRule(
            rule_id, pattern, match_type, merchant, category, subcategory,
            confidence, priority, review_required, explanation,
        ))
    return tuple(sorted(
        rules,
        key=lambda rule: (-rule.priority, -rule.specificity, rule.rule_id),
    ))


def validate_input_schema(fieldnames):
    actual = list(fieldnames or [])
    if actual != list(PREPROCESSED_COLUMNS):
        raise CategoryValidationError('unsupported preprocessed input schema')


def validate_input_records(records):
    if not records:
        raise CategoryValidationError('source dataset is empty')
    ids = []
    for row_number, record in enumerate(records, start=2):
        transaction_id = str(record.get('transaction_id') or '').strip()
        if not transaction_id:
            raise CategoryValidationError(f'row {row_number}: missing transaction_id')
        ids.append(transaction_id)
        try:
            if normalize_posting_date(record.get('transaction_date')) != record.get('transaction_date'):
                raise ValueError('transaction_date is not normalized')
            if normalize_effective_date(record.get('effective_date')) != record.get('effective_date'):
                raise ValueError('effective_date is not normalized')
        except ValueError as exc:
            raise CategoryValidationError(f'row {row_number}: {exc}') from exc
        for field in ('debit', 'credit', 'fee', 'balance'):
            try:
                parse_money(record.get(field), field=field, row_number=row_number)
            except ValueError as exc:
                raise CategoryValidationError(str(exc)) from exc
        if record.get('movement_type') not in MOVEMENT_TYPES:
            raise CategoryValidationError(f'row {row_number}: invalid movement_type')
        if record.get('movement_classification_method') not in MOVEMENT_CLASSIFICATION_METHODS:
            raise CategoryValidationError(
                f'row {row_number}: invalid movement_classification_method'
            )
        if record.get('movement_review_required') not in {'True', 'False'}:
            raise CategoryValidationError(
                f'row {row_number}: invalid movement_review_required'
            )
        if record.get('cleaned_description') != clean_description(record.get('description')):
            raise CategoryValidationError(
                f'row {row_number}: cleaned_description is inconsistent'
            )
        if not str(record.get('source_file') or '').strip():
            raise CategoryValidationError(f'row {row_number}: missing source_file')
        try:
            if int(record.get('page_number')) < 1:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise CategoryValidationError(
                f'row {row_number}: invalid page_number'
            ) from exc
    duplicates = [value for value, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise CategoryValidationError(
            f'duplicate transaction_id values detected ({len(duplicates)})'
        )


def validate_output_records(source_records, output_records, hierarchy):
    if len(source_records) != len(output_records):
        raise CategoryValidationError('record count changed during categorisation')
    identified = categorised = review_required = excluded = 0
    for row_number, (source, output) in enumerate(
            zip(source_records, output_records), start=2):
        if list(output) != OUTPUT_COLUMNS:
            raise CategoryValidationError(f'row {row_number}: invalid output schema')
        for field in PREPROCESSED_COLUMNS:
            if output[field] != source[field]:
                raise CategoryValidationError(
                    f'row {row_number}: source field {field} changed'
                )
        category = output['category']
        subcategory = output['subcategory']
        if bool(category) != bool(subcategory):
            raise CategoryValidationError(f'row {row_number}: incomplete category')
        if category and (category not in hierarchy or subcategory not in hierarchy[category]):
            raise CategoryValidationError(f'row {row_number}: invalid category')
        if output['classification_method'] not in CLASSIFICATION_METHODS:
            raise CategoryValidationError(f'row {row_number}: invalid method')
        if output['classification_confidence'] not in CONFIDENCE_LEVELS:
            raise CategoryValidationError(f'row {row_number}: invalid confidence')
        if output['spending_classification_status'] not in SPENDING_STATUSES:
            raise CategoryValidationError(f'row {row_number}: invalid spending status')
        if not isinstance(output['category_review_required'], bool):
            raise CategoryValidationError(f'row {row_number}: invalid review flag')
        identified += bool(output['clean_merchant'])
        categorised += bool(category) and category != 'Uncategorised'
        review_required += output['category_review_required']
        excluded += output['spending_classification_status'] == 'not_applicable'
    return {
        'processed': len(output_records),
        'merchants_identified': identified,
        'categorised': categorised,
        'review_required': review_required,
        'excluded': excluded,
        'validation_status': 'passed',
    }
