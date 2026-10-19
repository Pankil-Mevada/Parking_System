"""Scan the current tracked source snapshot; never print matched secret values.

This bounded signature check supplements provider scanning and human review. It
does not scan Git history, ignored local configuration, or arbitrary credentials.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RULES = (
    ('private-key', re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----')),
    ('github-token', re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{60,255})\b')),
    ('aws-access-key', re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('slack-token', re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,255}\b')),
    ('credential-url', re.compile(rb'\b(?:postgres(?:ql)?|mysql|amqps?)://[^\s/:]+:[^\s/@]+@', re.I)),
)


def findings(path, data):
    results = []
    for name, pattern in RULES:
        for match in pattern.finditer(data):
            results.append((path, data.count(b'\n', 0, match.start()) + 1, name))
    return results


def scan(root=ROOT):
    output = subprocess.run(
        ['git', 'ls-files', '-z'], cwd=root, check=True, capture_output=True
    ).stdout
    results = []
    for raw in output.split(b'\0'):
        if not raw:
            continue
        relative = raw.decode('utf-8', errors='surrogateescape')
        path = root / relative
        # A symlink could lead into private files outside the repository.
        if path.is_symlink():
            raise RuntimeError('Tracked symlinks require separate secret review')
        if path.is_file():
            results.extend(findings(relative, path.read_bytes()))
    return results


def main():
    try:
        results = scan()
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        print('Secret scan failed; source could not be fully inspected.', file=sys.stderr)
        return 2
    for path, line, rule in results:
        # repr prevents filenames containing terminal control characters from
        # becoming executable output or GitHub workflow commands.
        print(f'{path!r}:{line}: {rule} (value redacted)')
    print(f'Tracked snapshot secret scan: {len(results)} finding(s). History and ignored files excluded.')
    return 1 if results else 0


if __name__ == '__main__':
    raise SystemExit(main())
