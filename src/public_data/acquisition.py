"""Verified acquisition of the publicly downloadable IES reference files."""

import argparse
import hashlib
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import yaml


class AcquisitionError(ValueError):
    """Raised when a source manifest or downloaded file is invalid."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_source_manifest(path='config/public_data_sources.yaml'):
    with Path(path).open(encoding='utf-8') as handle:
        manifest = yaml.safe_load(handle)
    if not isinstance(manifest, dict) or manifest.get('version') != 1:
        raise AcquisitionError('source manifest must have version 1')
    files = manifest.get('public_reference_files')
    if not isinstance(files, dict) or not files:
        raise AcquisitionError('source manifest has no public reference files')
    for name, item in files.items():
        if not all(item.get(key) for key in ('url', 'filename', 'sha256')):
            raise AcquisitionError(f'incomplete source manifest entry: {name}')
        if len(item['sha256']) != 64:
            raise AcquisitionError(f'invalid SHA-256 in source manifest: {name}')
    return manifest


def acquire_reference_files(destination, manifest_path='config/public_data_sources.yaml',
                            urlopen=urllib.request.urlopen):
    """Download reference files safely, verifying pinned SHA-256 values."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest = load_source_manifest(manifest_path)
    results = {}
    for name, item in manifest['public_reference_files'].items():
        target = destination / item['filename']
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = item['sha256'].lower()
        if target.exists():
            if sha256_file(target) != expected:
                raise AcquisitionError(f'existing {name} has an unexpected SHA-256')
            results[name] = target
            continue
        temporary = tempfile.NamedTemporaryFile(
            delete=False, dir=destination, prefix=f'.{target.name}.', suffix='.tmp')
        staged = Path(temporary.name)
        try:
            with temporary, urlopen(item['url'], timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
            if sha256_file(staged) != expected:
                raise AcquisitionError(f'downloaded {name} has an unexpected SHA-256')
            os.replace(staged, target)
        finally:
            staged.unlink(missing_ok=True)
        results[name] = target
    return results


def extract_zip_archive(archive_path, destination):
    """Safely extract a downloaded archive without overwriting different files."""
    archive_path, destination = Path(archive_path), Path(destination)
    if not archive_path.is_file():
        raise AcquisitionError(f'archive does not exist: {archive_path}')
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            for item in members:
                member = Path(item.filename.replace('\\', '/'))
                if member.is_absolute() or '..' in member.parts:
                    raise AcquisitionError(f'unsafe archive member: {item.filename}')
            with tempfile.TemporaryDirectory(
                    dir=destination.parent, prefix='.archive-stage-') as temporary:
                staged_root = Path(temporary)
                archive.extractall(staged_root)
                pairs = [
                    (staged_root / item.filename, destination / item.filename)
                    for item in members
                ]
                for staged, target in pairs:
                    if target.exists() and sha256_file(staged) != sha256_file(target):
                        raise AcquisitionError(f'existing extracted file differs: {target}')
                for staged, target in pairs:
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(staged, target)
    except zipfile.BadZipFile as exc:
        raise AcquisitionError(f'invalid ZIP archive: {archive_path}') from exc
    return [destination / item.filename for item in members]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Download and verify public IES reference files')
    parser.add_argument('--destination', type=Path,
                        default=Path('data/public/raw'))
    parser.add_argument('--manifest', type=Path,
                        default=Path('config/public_data_sources.yaml'))
    args = parser.parse_args(argv)
    try:
        results = acquire_reference_files(args.destination, args.manifest)
    except (OSError, AcquisitionError) as exc:
        parser.exit(1, f'error: {exc}\n')
    for name, path in results.items():
        print(f'Verified {name}: {path}')


if __name__ == '__main__':
    main()
