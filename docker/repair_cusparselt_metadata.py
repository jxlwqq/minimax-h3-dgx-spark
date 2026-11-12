#!/usr/bin/env python3
"""Repair the known cuSPARSELt 0.8.1 ARM wheel tag, without changing binaries.

Upstream: https://github.com/pytorch/pytorch/issues/202632
The filename correctly says aarch64; WHEEL incorrectly says sbsa. PyTorch 2.15
pins this version, so validate the installed AArch64 libraries before applying
NVIDIA's metadata correction and updating the WHEEL entry in RECORD.
"""
import base64
import csv
import hashlib
from importlib import metadata
import io
import json
from pathlib import Path
import platform
import struct


def encoded_hash(digest):
    return 'sha256=' + base64.urlsafe_b64encode(digest).decode().rstrip('=')


def repair(dist, audit_path, machine=None, system=None):
    if (machine or platform.machine()).lower() not in ('aarch64', 'arm64') or (system or platform.system()) != 'Linux':
        return False
    if dist.version != '0.8.1':
        return False
    files = list(dist.files or [])
    wheel_entry = next(p for p in files if str(p).endswith('.dist-info/WHEEL'))
    record_entry = next(p for p in files if str(p).endswith('.dist-info/RECORD'))
    wheel = Path(dist.locate_file(wheel_entry))
    record = Path(dist.locate_file(record_entry))
    content = wheel.read_bytes()
    bad = b'Tag: py3-none-manylinux2014_sbsa'
    good = b'Tag: py3-none-manylinux2014_aarch64'
    tags = [line for line in content.splitlines() if line.startswith(b'Tag:')]
    if tags == [good]:
        return False
    if tags != [bad]:
        raise ValueError(f'Unexpected cuSPARSELt wheel tags: {tags!r}')
    rows = list(csv.reader(io.StringIO(record.read_text())))
    recorded = {row[0]: row[1] for row in rows}
    libraries = [p for p in files if '.so' in p.name]
    if not libraries:
        raise ValueError('No cuSPARSELt native libraries found')
    audited = []
    for entry in libraries:
        path = Path(dist.locate_file(entry))
        with path.open('rb') as stream:
            header = stream.read(64)
            if len(header) < 20 or header[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', header, 18)[0] != 183:
                raise ValueError(f'Not an ELF64 AArch64 library: {entry}')
            stream.seek(0)
            digest = hashlib.file_digest(stream, 'sha256').digest()
        if recorded.get(str(entry)) != encoded_hash(digest):
            raise ValueError(f'Native library RECORD checksum mismatch: {entry}')
        audited.append({'path': str(entry), 'sha256': digest.hex()})
    updated = content.replace(bad, good)
    target = str(wheel_entry)
    if sum(row[0] == target for row in rows) != 1:
        raise ValueError('Missing or duplicate WHEEL entry in RECORD')
    for row in rows:
        if row[0] == target:
            row[1:] = [encoded_hash(hashlib.sha256(updated).digest()), str(len(updated))]
    output = io.StringIO()
    csv.writer(output, lineterminator='\n').writerows(rows)
    wheel.write_bytes(updated)
    record.write_text(output.getvalue())
    Path(audit_path).write_text(json.dumps({
        'package': 'nvidia-cusparselt-cu13', 'version': dist.version,
        'old_tag': bad.decode(), 'new_tag': good.decode(),
        'native_libraries': audited,
        'upstream': 'https://github.com/pytorch/pytorch/issues/202632',
    }, indent=2) + '\n')
    return True


if __name__ == '__main__':
    changed = repair(metadata.distribution('nvidia-cusparselt-cu13'), '/opt/h3-runtime-adjustments.json')
    if not changed:
        Path('/opt/h3-runtime-adjustments.json').write_text('{"metadata_repair": "not needed"}\n')
    print('cuSPARSELt metadata:', 'corrected after AArch64/RECORD validation' if changed else 'no correction needed')
