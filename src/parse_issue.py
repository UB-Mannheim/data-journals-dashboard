"""
Parse a GitHub issue form body into a journal YAML file for dj process single.

Usage:
    ISSUE_BODY="..." python src/parse_issue.py /tmp/journal_contribution.yaml

Exits 0 on success, 1 on parse/validation error.
"""
import os
import re
import sys
import yaml
from pathlib import Path

# Maps lowercased GitHub form field headers → schema keys
FIELD_MAP = {
    "issn": "issn",
    "journal title": "journal_title",
    "publisher": "publisher",
    "url": "url",
    "data journal type": "data_journal_type",
    "journal status": "is_active",
}

_NO_RESPONSE = {"_no response_", "none", ""}


def parse_issue_body(body: str) -> dict:
    """Split on ### headers and map values to schema keys."""
    sections = re.split(r"^###\s+(.+)$", body, flags=re.MULTILINE)
    journal = {}
    for i in range(1, len(sections), 2):
        if i + 1 >= len(sections):
            break
        header = sections[i].strip().lower()
        value = sections[i + 1].strip()
        if value.lower() in _NO_RESPONSE:
            continue
        if header not in FIELD_MAP:
            continue
        key = FIELD_MAP[header]
        if key == "is_active":
            journal[key] = value.lower() == "active"
        else:
            journal[key] = value
    return journal


if __name__ == "__main__":
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/journal_contribution.yaml")

    body = os.environ.get("ISSUE_BODY", "").strip()
    if not body:
        print("ERROR: ISSUE_BODY environment variable is empty.", file=sys.stderr)
        sys.exit(1)

    journal = parse_issue_body(body)

    if not journal.get("issn"):
        print("ERROR: ISSN field is missing or empty.", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump({"journal": [journal]}, f, default_flow_style=False, allow_unicode=True)

    print(f"Written journal YAML to {output_path}")
    print(f"  issn: {journal.get('issn')}")
    print(f"  title: {journal.get('journal_title')}")
