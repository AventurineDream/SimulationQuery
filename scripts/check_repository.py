#!/usr/bin/env python3
"""Check local documentation links, structured files, and the public boundary."""
from __future__ import annotations

from fnmatch import fnmatch
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PATTERNS = (
    '.env', '.env.local', '.env.production', '*.sqlite', '*.sqlite3',
    '*.sqlite-wal', '*.sqlite-shm', '*.sqlite3-wal', '*.sqlite3-shm', '*.log',
    'private/*', 'season1/*', '.rehearsal-data/*',
    'research/AVEN_LABELS_SEALED*.jsonl', 'archive/adjacent-projects/*',
    'benchmarks/season-1-porch-rehearsal-batch-*.json',
    'benchmarks/season-1-porch-rehearsal-events-*.csv',
    'benchmarks/season-1-porch-rehearsal-summary-*.csv',
)


def public_files():
    result = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=ROOT, check=True, capture_output=True,
    )
    return sorted({ROOT / name for name in result.stdout.decode().split('\0')
                   if name and (ROOT / name).is_file()})


def prose_only(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            token = match.group(1)[0]
            if fence is None:
                fence = token
            elif fence == token:
                fence = None
            continue
        if fence is None:
            lines.append(re.sub(r'`[^`]*`', '', line))
    return '\n'.join(lines)


def local_links(text):
    prose = prose_only(text)
    inline = re.findall(r'\]\(\s*(<[^>]+>|[^\s)]+)', prose)
    reference = re.findall(r'^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)', prose, re.MULTILINE)
    for raw in inline + reference:
        target = raw.strip('<>')
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        yield unquote(parsed.path)


def main():
    errors = []
    paths = public_files()
    links = 0
    structured = 0
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if any(fnmatch(relative, pattern) for pattern in PRIVATE_PATTERNS):
            errors.append(f'Private artifact in public tree: {relative}')
        if path.suffix in ('.json', '.yaml', '.yml'):
            try:
                if path.suffix == '.json':
                    json.loads(path.read_text())
                else:
                    list(yaml.safe_load_all(path.read_text()))
                structured += 1
            except (ValueError, yaml.YAMLError) as error:
                errors.append(f'Invalid structured file {relative}: {error}')
        if path.suffix == '.md':
            for target in local_links(path.read_text()):
                links += 1
                destination = (ROOT / target.lstrip('/')) if target.startswith('/') else path.parent / target
                if not destination.exists():
                    errors.append(f'Missing link in {relative}: {target}')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'Repository check passed: {len(paths)} files, {links} local links, '
          f'{structured} JSON/YAML files; private artifact boundary passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
