import click
import copy
import yaml
from pathlib import Path
from datetime import datetime

from utils import load_schema, _IgnoreAliases
from config import METADATA_SCHEMA_PATH


def load_input(input_fpath: Path) -> list[dict]:
    """
    Load input YAML file, expecting top-level 'journals' key with a list of journal entries.
    """
    try:
        with open(input_fpath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML file: {e}")

    if not isinstance(data, dict) or "journals" not in data:
        raise ValueError(
            "Input YAML must contain a top-level 'journals' key with "
            "a list of journal entries."
        )

    journals = data["journals"]
    if not isinstance(journals, list):
        raise ValueError(
            "'journals' key must contain a list of journal dictionaries."
        )

    return journals


def validate_compliance(
    journals: list[dict],
    schema_fields: list[dict],
    scope: str = "full"
) -> list[str]:
    """
    Check if each journal has all required fields defined in the schema.

    Scope: "base", "core", "full".
    """
    # Determine required fields based on scope
    if scope == "base":
        required_fields = {
            f["key"] for f in schema_fields if f.get("source") == "csv"
        }
    elif scope == "core":
        required_fields = {
            f["key"] for f in schema_fields if f.get("schema_level") == "core"
        }
    elif scope == "full":
        required_fields = {
            f["key"] for f in schema_fields
            if f.get("schema_level") in ["internal", "core", "full"]
        }
    else:
        required_fields = None

    errors = []
    for idx, journal in enumerate(journals):
        journal_title = journal.get("journal_title", f"journal_{idx}")
        journal_id = journal.get("id", "N/A")

        for field in required_fields:
            # Check if metadata field is in journal
            if field not in journal:
                errors.append(
                    f"Missing required metadata field '{field}' in Journal "
                    f"'{journal_title}' (id: {journal_id})"
                )
    return errors


def check_duplicates(journals: list[dict]) -> list[str]:
    """
    Check for duplicate non-null values of 'id', 'issn', and 'journal_title'.
    """
    errors = []
    keys_to_check = ["id", "issn", "journal_title"]

    for key in keys_to_check:
        value_indices = {}
        for idx, journal in enumerate(journals):
            value = journal.get(key)
            if value is not None:
                if value not in value_indices:
                    value_indices[value] = []
                value_indices[value].append(idx)

        for value, indices in value_indices.items():
            if len(indices) > 1:
                titles = [journals[i].get(
                    "journal_title", f"journal_{i}"
                ) for i in indices]
                errors.append(
                    f"Duplicate '{key}': '{value}' found in journals at "
                    f"indices {indices} (titles: {titles})."
                )
    return errors


def _schema_key_order(schema_fields: list[dict]) -> list[str]:
    return [f["key"] for f in schema_fields]


def _reorder_journal(journal: dict, template_order: list[str]) -> dict:
    reordered = {}
    if "id" in journal:
        reordered["id"] = journal["id"]
    for key in template_order:
        if key in journal:
            reordered[key] = journal[key]
    for key in journal:
        if key not in reordered:
            reordered[key] = journal[key]
    return reordered


def repair_journals(
    journals: list[dict],
    schema_fields: list[dict],
    template_order: list[str] | None = None,
) -> tuple[dict[str], list[str]]:
    """
    Add missing keys to each journal using schema default values
    (never overwrites existing keys), then reorder keys to match template.
    """
    default_map = {f["key"]: f.get("default") for f in schema_fields}
    repaired = copy.deepcopy(journals)

    repairs_list = []
    for journal in repaired:
        for key, default_val in default_map.items():
            if key not in journal or journal[key] is None:
                journal[key] = copy.deepcopy(default_val)
                repairs_list.append(
                    f"Added missing '{key}' key to Journal "
                    f"'{journal.get("journal_title")}' (id: {journal.get("id")}) "
                    f"with default value: '{default_val}'"
                )
    if template_order:
        repaired = [_reorder_journal(j, template_order) for j in repaired]

    return repaired, repairs_list


def validate_types(
    journals: list[dict],
    schema_fields: list[dict],
) -> list[str]:
    """
    Check that each journal field's value matches the schema-defined type.
    None values are skipped (absence is handled by validate_compliance).
    """
    _type_map = {
        "string": str,
        "integer": int,
        "list": list,
        "boolean": bool,
    }

    type_map = {
        f["key"]: _type_map[f["type"]]
        for f in schema_fields
        if f.get("type") in _type_map
    }

    errors = []
    for idx, journal in enumerate(journals):
        journal_title = journal.get("journal_title", f"journal_{idx}")
        journal_id = journal.get("id", "N/A")
        for key, value in journal.items():
            if value is None or key not in type_map:
                continue
            expected = type_map[key]
            if not isinstance(value, expected):
                errors.append(
                    f"Journal '{journal_title}' (id: {journal_id}): field '{key}' "
                    f"has value of type '{type(value).__name__}' but schema expects "
                    f"'{expected.__name__}'."
                )

    return errors


def generate_log(errors: list[str]) -> str:
    """
    Generate a human-readable validation log with timestamp and summary.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines = [f"Validation Log - {timestamp}"]

    if errors:
        log_lines.append(f"Total issues found: {len(errors)}")
        log_lines.extend(f"- {error}" for error in errors)
    else:
        log_lines.append("No validation issues found.")

    return "\n".join(log_lines)


def write_log(log: str, output_fpath: Path | None, text_color: str = "blue"):
    """
    Write validation log to file or stdout.
    """
    if output_fpath is not None:
        try:
            with open(output_fpath, "w", encoding="utf-8") as f:
                f.write(log + "\n")
        except IOError as e:
            raise RuntimeError(f"Failed to write log to {output_fpath}: {e}")
    else:
        click.secho(log, fg=text_color)


def run_validation(
    input_fpath: Path,
    output_fpath: Path | None,
    repair: bool = False,
    issn: str | None = None,
    scope: str = "full",
):
    """
    Main validation workflow: load schema, validate, log results,
    optionally repair.
    """
    # Load schema (load_schema returns fields list directly)
    try:
        schema_fields = load_schema(schema_path=METADATA_SCHEMA_PATH)
    except Exception as e:
        raise RuntimeError(f"Failed to load schema: {e}")

    if not schema_fields:
        raise RuntimeError("Schema has no fields defined.")

    # Load input journals
    try:
        journals = load_input(input_fpath)
    except Exception as e:
        raise RuntimeError(f"Failed to load input file: {e}")

    if issn:
        journals = [j for j in journals if j.get("issn") == issn]
        if not journals:
            raise ValueError(f"No journal with ISSN '{issn}' found in input file.")

    # Run validation checks
    compliance_errors = validate_compliance(journals, schema_fields, scope=scope)
    type_errors = validate_types(journals, schema_fields)
    duplicate_errors = check_duplicates(journals)
    all_errors = compliance_errors + type_errors + duplicate_errors

    # Repair input file if requested
    if repair:
        schema_key_order = _schema_key_order(schema_fields)
        repaired_journals, repairs_list = repair_journals(
            journals, schema_fields, schema_key_order
        )
        try:
            with open(input_fpath, "w", encoding="utf-8") as f:
                yaml.dump(
                    {"journals": repaired_journals},
                    f,
                    Dumper=_IgnoreAliases,
                    allow_unicode=True,
                    sort_keys=False,
                )
        except IOError as e:
            raise RuntimeError(
                f"Failed to write repaired data to {input_fpath}: {e}"
            )

    # Generate and write logs
    error_log = generate_log(all_errors)
    write_log(error_log, output_fpath, text_color="red")

    if repair:
        repairs_log = generate_log(repairs_list)
        write_log(repairs_log, output_fpath, text_color="green")
