"""Row-level cleaning for the IES total expenditure file."""

from decimal import Decimal, InvalidOperation
import math
from numbers import Integral, Real

from .mapping import map_expenditure


class ExpenditureDataError(ValueError):
    pass


SOURCE_FIELDS = (
    'uqno', 'uqno_num', 'coicop', 'coicop_type', 'division', 'group',
    'class', 'subclass', 'sixth_group', 'valueannualized_adj',
    'valueannualized_adj_wgt',
)

ALIASES = {
    'uqno': {'uqno', 'unique_number'},
    'uqno_num': {'uqno_num'},
    'coicop': {'coicop', 'detailed_coicop'},
    'coicop_type': {'coicoptype', 'coicop_type'},
    'division': {'division'},
    'group': {'group'},
    'class': {'class', '_class'},
    'subclass': {'subclass'},
    'sixth_group': {'sixthgroup', 'sixth_group'},
    'valueannualized_adj': {'valueannualized_adj'},
    'valueannualized_adj_wgt': {'valueannualized_adj_wgt'},
}

OUTPUT_COLUMNS = [
    *SOURCE_FIELDS,
    'item_description', 'coicop_type_description', 'division_description',
    'group_description', 'class_description', 'subclass_description',
    'sixth_group_description', 'province', 'metro_code', 'settlement_type',
    'survey_date', 'codebook_match_status', 'personal_category', 'personal_subcategory',
    'comparability', 'mapping_rule_id', 'mapping_rationale',
]

CODE_WIDTHS = {
    'coicop': 8, 'division': 2, 'group': 3, 'class': 4,
    'subclass': 5, 'sixth_group': 6,
}

COICOP_TYPE_DESCRIPTIONS = {
    '1': 'Consumption', '2': 'In kind consumption', '3': 'Income',
    '4': 'In kind income', '5': 'Savings', '6': 'Taxes',
    '7': 'Transfers to others', '8': 'Other Products Not Consumption',
    '9': 'Debts outstanding', '10': 'Debts monthly repayment',
    '11': 'Not for CPI purposes',
}


def _text(value):
    if value is None:
        return ''
    if isinstance(value, Real) and not isinstance(value, Integral):
        if math.isnan(float(value)):
            return ''
        if float(value).is_integer():
            return str(int(value))
    text = str(value).strip()
    return '' if text == '<NA>' else text


def resolve_schema(fieldnames):
    if not fieldnames:
        raise ExpenditureDataError('total expenditure file has no header')
    normalized = {name.strip().lower().replace(' ', '_'): name for name in fieldnames}
    resolved = {}
    for canonical, aliases in ALIASES.items():
        candidates = [normalized[name] for name in aliases if name in normalized]
        if candidates:
            resolved[canonical] = candidates[0]
    required = set(SOURCE_FIELDS) - {'uqno_num'}
    missing = sorted(required - resolved.keys())
    if missing:
        raise ExpenditureDataError(f'missing total expenditure columns: {missing}')
    return resolved


def _money(value, field):
    value = (value or '').strip()
    if not value:
        return ''
    try:
        amount = Decimal(value.replace(',', ''))
    except InvalidOperation as exc:
        raise ExpenditureDataError(f'invalid {field}: {value!r}') from exc
    if not amount.is_finite() or amount < 0:
        raise ExpenditureDataError(f'{field} must be a non-negative finite value')
    return format(amount, 'f')


def clean_row(raw, schema, codebook, mapping, geography=None):
    row = {field: _text(raw.get(source)) for field, source in schema.items()}
    row.setdefault('uqno_num', '')
    for field, width in CODE_WIDTHS.items():
        if row.get(field, '').isdigit():
            row[field] = row[field].zfill(width)
    if not row['uqno']:
        raise ExpenditureDataError('uqno is missing')
    if not row['coicop'].isdigit() or len(row['coicop']) != 8:
        raise ExpenditureDataError(f'invalid COICOP code: {row["coicop"]!r}')
    row['valueannualized_adj'] = _money(
        row['valueannualized_adj'], 'valueannualized_adj')
    row['valueannualized_adj_wgt'] = _money(
        row['valueannualized_adj_wgt'], 'valueannualized_adj_wgt')
    reference = codebook.get(row['coicop'])
    row['coicop_type_description'] = COICOP_TYPE_DESCRIPTIONS.get(
        row['coicop_type'], '')
    description_fields = (
        'item_description', 'division_description', 'group_description',
        'class_description', 'subclass_description',
        'sixth_group_description')
    if reference is None:
        row['codebook_match_status'] = 'code_absent_from_codebook'
        for field in description_fields:
            row[field] = ''
    else:
        for field in ('division', 'group', 'class', 'subclass', 'sixth_group'):
            if row[field] != reference[field]:
                raise ExpenditureDataError(
                    f'{field} {row[field]!r} conflicts with codebook for {row["coicop"]}')
        row['codebook_match_status'] = (
            'matched' if row['coicop_type'] == reference['coicop_type']
            else 'coicop_type_conflict')
        for field in description_fields:
            row[field] = reference[field]
    geo = (geography or {}).get(row['uqno'], {})
    row.update({
        'province': geo.get('province', ''),
        'metro_code': geo.get('metro_code', ''),
        'settlement_type': geo.get('settlement_type', ''),
        'survey_date': geo.get('survey_date', ''),
    })
    row.update(map_expenditure(row, mapping))
    return {column: row.get(column, '') for column in OUTPUT_COLUMNS}
