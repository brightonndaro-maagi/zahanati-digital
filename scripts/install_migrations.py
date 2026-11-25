"""Installs the hand-written migrations shipped in scripts/*_migration.template on top of YOUR migration history.
Safe to run again: templates whose revision is already installed are skipped.

Run from the project root:   python scripts/install_migrations.py
Then:                        flask db upgrade
"""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
versions = root / "migrations" / "versions"

if not versions.is_dir():
    sys.exit("migrations/versions not found. Run this from the project root after 'flask db init'.")


def history():
    revisions, parents = set(), set()
    for f in versions.glob("*.py"):
        text = f.read_text()
        rev = re.search(r"^revision\s*=\s*[\"']([^\"']+)[\"']", text, re.M)
        down = re.search(r"^down_revision\s*=\s*(.+)$", text, re.M)
        if rev:
            revisions.add(rev.group(1))
        if down:
            parents.update(re.findall(r"[\"']([^\"']+)[\"']", down.group(1)))
    return revisions, revisions - parents


installed = 0
for template in sorted((root / "scripts").glob("*_migration.template")):
    text = template.read_text()
    rev = re.search(r"^revision\s*=\s*[\"']([^\"']+)[\"']", text, re.M).group(1)
    revisions, heads = history()
    if rev in revisions:
        continue
    if len(heads) != 1:
        sys.exit(f"Expected exactly one current migration head, found {sorted(heads)}.")
    head = next(iter(heads))
    name = template.name.replace("_migration.template", "")
    (versions / f"{rev}_{name}.py").write_text(text.replace("__DOWN_REVISION__", head))
    print(f"Installed {name} migration ({rev}) on top of {head}")
    installed += 1

print("Now run: flask db upgrade" if installed else "Nothing to install - migrations are up to date.")
