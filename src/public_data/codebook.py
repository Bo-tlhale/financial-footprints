"""Minimal, dependency-free reader for the official single-sheet XLSX codebook."""

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


class CodebookError(ValueError):
    pass


_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def load_coicop_codebook(path):
    path = Path(path)
    if not path.is_file():
        raise CodebookError(f'COICOP codebook does not exist: {path}')
    try:
        with zipfile.ZipFile(path) as archive:
            shared_root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            shared = [
                ''.join(node.text or '' for node in item.iter(f'{_NS}t'))
                for item in shared_root
            ]
            sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise CodebookError(f'invalid COICOP XLSX: {path}') from exc
    rows = []
    for row in sheet.iter(f'{_NS}row'):
        values = {}
        for cell in row.findall(f'{_NS}c'):
            match = re.match(r'[A-Z]+', cell.get('r', ''))
            value = cell.find(f'{_NS}v')
            text = '' if value is None else (value.text or '')
            if cell.get('t') == 's' and text:
                text = shared[int(text)]
            if match:
                values[match.group()] = text.strip()
        rows.append(values)
    if not rows:
        raise CodebookError('COICOP codebook is empty')
    columns = {
        'A': 'coicop', 'B': 'item_description', 'C': 'coicop_type',
        'D': 'coicop_type_description', 'E': 'division',
        'F': 'division_description', 'G': 'group',
        'H': 'group_description', 'I': 'class', 'J': 'class_description',
        'K': 'subclass', 'L': 'subclass_description',
        'M': 'sixth_group', 'N': 'sixth_group_description',
    }
    expected = {letter: name for letter, name in columns.items()}
    header = {letter: rows[0].get(letter, '').strip().lower() for letter in columns}
    if header['A'] != 'coicop' or header['E'] != 'division':
        raise CodebookError('unexpected COICOP codebook schema')
    records = {}
    for raw in rows[1:]:
        record = {name: raw.get(letter, '') for letter, name in expected.items()}
        code = record['coicop']
        if not re.fullmatch(r'\d{8}', code):
            raise CodebookError(f'invalid COICOP code: {code!r}')
        if code in records:
            existing = records[code]
            hierarchy_fields = set(record) - {'item_description'}
            if any(existing[field] != record[field] for field in hierarchy_fields):
                raise CodebookError(f'conflicting COICOP hierarchy for code: {code}')
            descriptions = existing['item_description'].split(' / ')
            if record['item_description'] not in descriptions:
                existing['item_description'] += f' / {record["item_description"]}'
            continue
        records[code] = record
    return records
