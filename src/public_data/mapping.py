"""Validated mapping from official COICOP codes to personal categories."""

from pathlib import Path

import yaml


class MappingError(ValueError):
    pass


ALLOWED_COMPARABILITY = {'adjustment_required', 'not_comparable'}


def load_mapping(path='config/expenditure_mapping.yaml',
                 categories_path='config/categories.yaml'):
    with Path(path).open(encoding='utf-8') as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or config.get('version') != 1:
        raise MappingError('expenditure mapping must have version 1')
    rules = config.get('rules')
    if not isinstance(rules, list) or not rules:
        raise MappingError('expenditure mapping requires rules')
    with Path(categories_path).open(encoding='utf-8') as handle:
        category_config = yaml.safe_load(handle)
    hierarchy = {
        item['name']: set(item['subcategories'])
        for item in category_config.get('categories', [])
    }
    default = config.get('default')
    if not isinstance(default, dict) or default.get('comparability') != 'not_comparable':
        raise MappingError('mapping default must be not_comparable')
    ids = set()
    signatures = set()
    for rule in rules:
        required = {'id', 'field', 'prefix', 'category', 'subcategory',
                    'comparability', 'rationale'}
        if not required.issubset(rule):
            raise MappingError('mapping rule is missing required fields')
        if rule['id'] in ids:
            raise MappingError(f'duplicate mapping rule ID: {rule["id"]}')
        if rule['field'] not in {'division', 'group', 'class', 'subclass', 'coicop'}:
            raise MappingError(f'invalid mapping field: {rule["field"]}')
        if rule['comparability'] not in ALLOWED_COMPARABILITY:
            raise MappingError(f'invalid comparability: {rule["comparability"]}')
        if (rule['category'] not in hierarchy or
                rule['subcategory'] not in hierarchy[rule['category']]):
            raise MappingError(f'mapping rule {rule["id"]} uses an invalid category')
        signature = (rule['field'], str(rule['prefix']))
        if signature in signatures:
            raise MappingError(f'duplicate mapping selector: {signature}')
        ids.add(rule['id'])
        signatures.add(signature)
    return config


def map_expenditure(record, config):
    matches = []
    for rule in config['rules']:
        value = str(record.get(rule['field'], ''))
        if value.startswith(str(rule['prefix'])):
            matches.append(rule)
    if matches:
        rule = max(matches, key=lambda item: (len(str(item['prefix'])), item['field']))
        return {
            'personal_category': rule['category'],
            'personal_subcategory': rule['subcategory'],
            'comparability': rule['comparability'],
            'mapping_rule_id': rule['id'],
            'mapping_rationale': rule['rationale'],
        }
    default = config['default']
    return {
        'personal_category': default.get('category') or '',
        'personal_subcategory': default.get('subcategory') or '',
        'comparability': default['comparability'],
        'mapping_rule_id': '',
        'mapping_rationale': default['rationale'],
    }
