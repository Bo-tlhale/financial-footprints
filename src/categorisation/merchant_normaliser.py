"""Deterministic merchant matching using validated configurable rules."""

import re


def _matches(rule, description):
    if rule.match_type == 'exact':
        return description.casefold() == rule.pattern.casefold()
    return re.search(rule.pattern, description, re.IGNORECASE) is not None


def identify_merchant(cleaned_description, rules):
    """Return the most specific match or an auditable ambiguous result."""
    description = str(cleaned_description or '').strip()
    if not description:
        return None
    matches = [rule for rule in rules if _matches(rule, description)]
    if not matches:
        return None
    best_key = max((rule.priority, rule.specificity) for rule in matches)
    best = [
        rule for rule in matches
        if (rule.priority, rule.specificity) == best_key
    ]
    outcomes = {
        (rule.merchant, rule.category, rule.subcategory) for rule in best
    }
    if len(outcomes) > 1:
        return {
            'ambiguous': True,
            'merchant': '',
            'category': '',
            'subcategory': '',
            'confidence': 'unknown',
            'review_required': True,
            'rule_ids': tuple(rule.rule_id for rule in best),
        }
    selected = best[0]
    return {
        'ambiguous': False,
        'merchant': selected.merchant,
        'category': selected.category,
        'subcategory': selected.subcategory,
        'confidence': selected.confidence,
        'review_required': selected.review_required,
        'rule_ids': (selected.rule_id,),
    }
