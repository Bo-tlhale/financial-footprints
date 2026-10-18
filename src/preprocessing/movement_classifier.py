"""Deterministic, transparent transaction movement classification."""

import re
from decimal import Decimal

PURCHASE_TYPES = {'pos purchase', 'overseas purchase', 'airtime debit'}
INCOMING_TRANSFER_TYPES = {
    'acb credit', 'digital payment cr', 'payshap ext credit',
}
OUTGOING_TRANSFER_TYPES = {
    'cashsend digital', 'cashsend mobile', 'digital payment dt',
    'digital transf dt', 'mobile payment dt', 'payshap ext debit',
}
REFUND_TYPES = {'pos o/sea refund'}
CASH_WITHDRAWAL_TYPES = {'atm withdrawal', 'sas atm withdrawal'}
BANK_FEE_TYPES = {'transaction fee'}
REVERSAL_TYPES = {'can cashsend mb', 'can cashsend ib'}
INFORMATIONAL_TYPES = {'notific fee sms'}

INCOME_DESCRIPTION = re.compile(r'\b(salary|payroll|wages?|pension)\b', re.I)
REFUND_DESCRIPTION = re.compile(r'\b(refund|cashback)\b', re.I)
REVERSAL_DESCRIPTION = re.compile(r'\b(reversal|reversed|cancelled|canceled)\b', re.I)


def _result(movement_type, method, review_required=False):
    return {
        'movement_type': movement_type,
        'movement_classification_method': method,
        'movement_review_required': bool(review_required),
    }


def classify_movement(record):
    """Classify a validated row without treating direction as spending or income."""
    transaction_type = str(record.get('transaction_type', '')).strip().casefold()
    description = str(record.get('cleaned_description', ''))
    debit = Decimal(record['debit'])
    credit = Decimal(record['credit'])
    fee = Decimal(record['fee'])
    has_debit = debit > 0
    has_credit = credit > 0
    has_fee = fee > 0
    no_movement = not (has_debit or has_credit or has_fee)
    debit_only = has_debit and not (has_credit or has_fee)
    credit_only = has_credit and not (has_debit or has_fee)
    fee_only = has_fee and not (has_debit or has_credit)

    if transaction_type in PURCHASE_TYPES:
        return (_result('Purchase', 'bank_transaction_type') if debit_only
                else _result('Unknown', 'unclassified', True))
    if transaction_type in REFUND_TYPES:
        return (_result('Refund', 'bank_transaction_type') if credit_only
                else _result('Unknown', 'unclassified', True))
    if transaction_type in CASH_WITHDRAWAL_TYPES:
        return (_result('Cash Withdrawal', 'bank_transaction_type') if debit_only
                else _result('Unknown', 'unclassified', True))
    if transaction_type in BANK_FEE_TYPES:
        return (_result('Bank Fee', 'bank_transaction_type') if fee_only
                else _result('Unknown', 'unclassified', True))
    if transaction_type in REVERSAL_TYPES:
        return (_result('Reversal', 'bank_transaction_type') if credit_only
                else _result('Unknown', 'unclassified', True))
    if transaction_type in INFORMATIONAL_TYPES:
        return (_result('Informational', 'bank_transaction_type') if no_movement
                else _result('Unknown', 'unclassified', True))

    if credit_only and INCOME_DESCRIPTION.search(description):
        return _result('Income', 'description_rule')
    if credit_only and REFUND_DESCRIPTION.search(description):
        return _result('Refund', 'description_rule')
    if ((debit_only or credit_only)
            and REVERSAL_DESCRIPTION.search(description)):
        return _result('Reversal', 'description_rule', True)

    if transaction_type in INCOMING_TRANSFER_TYPES:
        return (_result('Incoming Transfer', 'bank_transaction_type') if credit_only
                else _result('Unknown', 'unclassified', True))
    if transaction_type in OUTGOING_TRANSFER_TYPES:
        return (_result('Outgoing Transfer', 'bank_transaction_type') if debit_only
                else _result('Unknown', 'unclassified', True))
    if fee_only:
        return _result('Bank Fee', 'manual_rule', True)
    if no_movement:
        return _result('Informational', 'manual_rule', True)
    return _result('Unknown', 'unclassified', True)
