"""Apply merchant and expenditure rules without changing movement semantics."""

from .merchant_normaliser import identify_merchant

EXPENSE_MOVEMENTS = {'Purchase', 'Bank Fee'}
NON_EXPENSE_MOVEMENTS = {
    'Income', 'Incoming Transfer', 'Outgoing Transfer', 'Refund',
    'Cash Withdrawal', 'Reversal', 'Informational',
}


def _classification(**overrides):
    result = {
        'clean_merchant': '',
        'category': '',
        'subcategory': '',
        'classification_method': 'unclassified',
        'classification_confidence': 'unknown',
        'category_review_required': True,
        'spending_classification_status': 'requires_review',
    }
    result.update(overrides)
    return result


def classify_transaction(record, rules):
    movement = record['movement_type']
    if movement in NON_EXPENSE_MOVEMENTS:
        return _classification(
            classification_method='movement_exclusion',
            classification_confidence='high',
            category_review_required=False,
            spending_classification_status='not_applicable',
        )
    if movement == 'Unknown':
        return _classification(
            category='Uncategorised',
            subcategory='Needs Review',
        )
    if movement == 'Bank Fee':
        return _classification(
            category='Financial Charges',
            subcategory='Transaction Fees',
            classification_method='transaction_rule',
            classification_confidence='high',
            category_review_required=False,
            spending_classification_status='applicable',
        )
    transaction_type = str(record.get('transaction_type') or '').strip().casefold()
    if movement == 'Purchase' and transaction_type == 'airtime debit':
        return _classification(
            category='Utilities & Communication',
            subcategory='Airtime',
            classification_method='transaction_rule',
            classification_confidence='high',
            category_review_required=False,
            spending_classification_status='applicable',
        )
    if movement not in EXPENSE_MOVEMENTS:
        return _classification()
    match = identify_merchant(record.get('cleaned_description'), rules)
    if not match:
        return _classification(
            category='Uncategorised',
            subcategory='Needs Review',
        )
    if match['ambiguous']:
        return _classification(
            classification_method='merchant_rule',
        )
    if not match['category']:
        return _classification(
            clean_merchant=match['merchant'],
            classification_method='merchant_rule',
            classification_confidence=match['confidence'],
        )
    review = match['review_required'] or match['confidence'] in {'low', 'unknown'}
    return _classification(
        clean_merchant=match['merchant'],
        category=match['category'],
        subcategory=match['subcategory'],
        classification_method='merchant_rule',
        classification_confidence=match['confidence'],
        category_review_required=review,
        spending_classification_status=(
            'requires_review' if review else 'applicable'
        ),
    )
