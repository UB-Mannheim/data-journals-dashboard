import click
import csv
import json
import yaml
from pathlib import Path

from config import METADATA_SCHEMA_PATH


def ensure_dir(dir_path: Path | str):
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def ensure_output_fpath(
    output_fpath: Path | str | None,
    input_fpath: Path | str | None,
    suffix: str,
    issn: str | None = None,
) -> Path:
    """
    Ensure that output_fpath always returns a file_path with file suffix
    despite it possibly being a directory.
    """
    default_name = f"{issn}{suffix}" if issn else Path(input_fpath).with_suffix(suffix).name

    if output_fpath:
        p = Path(output_fpath)
        if p.is_dir() or not p.suffix:
            return p / default_name
        return p

    return Path("./exports") / default_name


def load_schema(
    schema_path: Path | str = METADATA_SCHEMA_PATH
) -> list[dict]:
    """
    Load the journal metadata schema and return the list of field definitions.
    """
    try:
        with open(schema_path, "r", encoding="utf-8") as file:
            schema = yaml.safe_load(file)
        return schema.get("fields", [])
    except Exception as e:
        click.secho(f"Error loading schema from {schema_path}: {e}", fg="red")
        return []


def load_schema_core(
    schema_path: Path | str = METADATA_SCHEMA_PATH,
    djd_fields: bool = False
):
    """
    Load schema[schema_level] = "core" with or without "djd" fields.
    """
    schema = load_schema(schema_path=schema_path)

    if djd_fields:
        schema_core = [f["key"] for f in schema if f["schema_level"] == "core"]
    else:
        schema_core = [
            f["key"] for f in schema
            if f["schema_level"] == "core" and f.get("source") != "djd"
        ]

    return schema_core


def _load_journals_from_json(fpath: Path, verbose: bool = True) -> list[dict]:
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        if verbose:
            click.secho(f"Error reading JSON {fpath}: {e}", fg="red")
        return []
    if not data or "journals" not in data:
        if verbose:
            click.secho(
                f"Invalid JSON structure in {fpath}: missing 'journals' key.",
                fg="red"
            )
        return []
    return [
        {"id": idx, "issn": issn, **fields}
        for idx, (issn, fields) in enumerate(data["journals"].items(), start=1)
    ]


def load_journal_data_from_csv(fpath: Path) -> list[list[str]] | None:
    """
    Read a local CSV file and return parsed rows (header first).
    """
    try:
        with open(fpath, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))
    except Exception as e:
        click.secho(f"Error reading CSV {fpath}: {e}", fg="red")
        return None


def parse_csv_rows_with_schema(
    rows: list[list[str]],
    schema_fields: list[dict],
) -> list[dict]:
    """
    Convert CSV rows to list of dicts, only including fields defined in
    schema with source "csv" or "djd".
    """
    if not rows:
        return []

    # Get CSV fields from schema
    header = [col.strip() for col in rows[0]]
    csv_fields = [f for f in schema_fields if f["source"] == "csv"]
    csv_col_to_field = {f["csv_column"].strip(): f for f in csv_fields}

    # Get djd fields from schema (id)
    djd_fields = [f for f in schema_fields if f["source"] == "djd"]

    journals = []
    for idx, row in enumerate(rows[1:], start=1):
        # Add djd fields first (id)
        record = {}
        for gf in djd_fields:
            if gf["key"] == "id":
                record["id"] = idx
            else:
                record[gf["key"]] = gf.get("default")

        # Map CSV columns
        for col, val in zip(header, row):
            col_clean = col.strip()
            if col_clean in csv_col_to_field:
                field = csv_col_to_field[col_clean]
                record[field["key"]] = _coerce_value(
                    val.strip(), field.get("type", "string")
                )
        journals.append(record)

    return journals


def _coerce_value(val: str, field_type: str):
    """
    Cast a CSV string value to the type declared in the schema.
    """
    if field_type == "boolean":
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False
        return None
    if field_type == "integer":
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    return val


def write_csv_to_disk(
    rows: list[list[str]],
    fpath: Path,
    verbose: bool = True,
    quoting: csv = csv.QUOTE_MINIMAL | csv.QUOTE_ALL,
) -> None:
    """
    Write raw CSV rows to disk.
    """
    ensure_dir(fpath.parent)
    with open(fpath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=quoting)
        writer.writerows(rows)
    if verbose:
        click.secho(f"Saved raw CSV → {fpath}", fg="green")


class _IgnoreAliases(yaml.Dumper):
    """
    Prevent PyYAML from emitting anchors/aliases for repeated objects.
    """
    def ignore_aliases(self, _data):
        return True


def write_yaml_to_disk(
    journals: list[dict],
    fpath: Path,
    sort_by_id: bool = True,
    verbose: bool = True
):
    """
    Write enriched journal records to a YAML file.
    """
    # Make sure output_dir exists
    ensure_dir(fpath.parent)

    if sort_by_id:
        journals = sorted(journals, key=lambda x: x["id"])

    with open(fpath, "w", encoding="utf-8") as file:
        yaml.dump(
            {"journals": journals},
            file,
            Dumper=_IgnoreAliases,
            allow_unicode=True,
            sort_keys=False
        )
    if verbose:
        click.secho(f"Saved enriched YAML → {fpath}", fg="green")


def get_journal_by_issn(yaml_path: Path, issn: str) -> dict | None:
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for journal in data.get("journals", []):
        if journal.get("issn") == issn:
            return journal
    return None


def to_yaml(
    input_fpath: Path | str = None,
    output_fpath: Path | str = None,
    scope: str = "core",
    schema_path: Path | str = METADATA_SCHEMA_PATH,
    verbose: bool = True,
    issn: str | None = None,
) -> list[dict]:
    """
    Parse a CSV or JSON journal collection and transform it to a YAML journal
    collection. Optionally, save it to disk.
    """
    schema = load_schema(schema_path=schema_path)

    # Determine allowed keys based on scope
    if scope == "base":
        allowed_keys = {
            f["key"] for f in schema if f.get("source") == "csv"
        }
    elif scope == "core":
        allowed_keys = {
            f["key"] for f in schema if f.get("schema_level") == "core"
        }
    elif scope == "full":
        allowed_keys = {
            f["key"] for f in schema
            if f.get("schema_level") in ["internal", "core", "full"]
        }
    else:
        allowed_keys = None

    input_path = Path(input_fpath)
    suffix = input_path.suffix.lower()

    if suffix == ".csv":
        rows = load_journal_data_from_csv(input_path)
        if not rows:
            if verbose:
                click.secho(
                    f"Could not parse CSV for filepath: {input_path}. "
                    "Please make sure the file contains valid CSV data.",
                    fg="red"
                )
            return []
        journals = parse_csv_rows_with_schema(rows, schema)
    elif suffix == ".json":
        journals = _load_journals_from_json(input_path, verbose=verbose)
        if not journals:
            return []
    else:
        if verbose:
            click.secho(
                f"Unsupported input format: {suffix}. Use .csv or .json.",
                fg="red"
            )
        return []

    # Sort keys
    allowed_keys = sorted(allowed_keys, key=lambda k: (k != "issn", k))

    if allowed_keys is not None:
        journals = [
            {k: v for k, v in j.items() if k in allowed_keys}
            for j in journals
        ]

    if output_fpath is not None or issn is not None:
        resolved = ensure_output_fpath(output_fpath, input_path, ".yaml", issn)
        write_yaml_to_disk(journals, resolved, sort_by_id=False, verbose=verbose)

    return journals


def to_csv(
    input_fpath: Path = None,
    output_fpath: Path = None,
    scope: str = "core",
    schema_path: Path | str = METADATA_SCHEMA_PATH,
    sort: bool = True,
    verbose: bool = True,
    issn: str | None = None,
) -> dict:
    """
    Parse an existing YAML or JSON journal collection and transform it to CSV.
    Optionally, save it to disk.
    """
    schema = load_schema(schema_path=schema_path)

    # Determine allowed keys based on scope
    if scope == "base":
        csv_fields = [f for f in schema if f.get("source") == "csv"]
        csv_quote_level = csv.QUOTE_MINIMAL
    elif scope == "core":
        csv_fields = [f for f in schema if f.get("schema_level") == "core"]
        csv_quote_level = csv.QUOTE_MINIMAL
    elif scope == "full":
        csv_fields = [
            f for f in schema
            if f.get("schema_level") in ["core", "full"]
        ]
        csv_quote_level = csv.QUOTE_ALL

    input_path = Path(input_fpath)
    suffix = input_path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                journal_data = yaml.safe_load(f)
        except Exception as e:
            if verbose:
                click.secho(f"Error reading YAML {input_path}: {e}", fg="red")
            return {}
        if not journal_data or "journals" not in journal_data:
            if verbose:
                click.secho(
                    f"Could not parse YAML for filepath: {input_path}. "
                    "Please make sure the file contains valid YAML data.",
                    fg="red"
                )
            return {}
        journals = journal_data["journals"]
    elif suffix == ".json":
        journals = _load_journals_from_json(input_path, verbose=verbose)
        if not journals:
            return {}
    else:
        if verbose:
            click.secho(
                f"Unsupported input format: {suffix}. Use .yaml, .yml, or .json.",
                fg="red"
            )
        return {}

    csv_header = [
        f.get("csv_column") or f.get("doaj_path") for f in csv_fields
    ]
    rows = [csv_header]
    for journal in journals:
        row = [str(journal.get(f["key"], "")) for f in csv_fields]
        rows.append(row)

    if sort:
        # Sort rows based on journal_title
        rows = sorted(rows[1:], key=lambda x: x[1].lower())
        rows.insert(0, csv_header)

    # Optionally: write csv to disk
    if output_fpath is not None or issn is not None:
        resolved = ensure_output_fpath(output_fpath, input_path, ".csv", issn)
        ensure_dir(resolved.parent)
        write_csv_to_disk(rows, resolved, verbose, quoting=csv_quote_level)

    return rows


def to_json(
    input_fpath: Path | str = None,
    output_fpath: Path | str = None,
    scope: str = "core",
    schema_path: Path | str = METADATA_SCHEMA_PATH,
    verbose: bool = True,
    issn: str | None = None,
) -> list[dict]:
    """
    Convert a CSV or YAML journal collection to a JSON file.
    Optionally, save it to disk.
    """
    schema = load_schema(schema_path=schema_path)

    # Determine allowed keys based on scope
    if scope == "base":
        allowed_keys = {
            f["key"] for f in schema if f.get("source") == "csv"
        }
    elif scope == "core":
        allowed_keys = {
            f["key"] for f in schema if f.get("schema_level") == "core"
        }
    elif scope == "full":
        allowed_keys = {
            f["key"] for f in schema
            if f.get("schema_level") in ["internal", "core", "full"]
        }
    else:
        allowed_keys = None

    input_path = Path(input_fpath)
    suffix = input_path.suffix.lower()
    journals = []

    # Parse input file based on type
    if suffix == ".csv":
        rows = load_journal_data_from_csv(input_path)
        if not rows:
            if verbose:
                click.secho(
                    f"Could not parse CSV for filepath: {input_path}. "
                    "Please make sure the file contains valid CSV data.",
                    fg="red"
                )
            return []
        journals = parse_csv_rows_with_schema(rows, schema)

    elif suffix in (".yaml", ".yml"):
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                journal_data = yaml.safe_load(f)
        except Exception as e:
            if verbose:
                click.secho(
                    f"Error reading YAML {input_path}: {e}", fg="red"
                )
            return []
        if not journal_data or "journals" not in journal_data:
            if verbose:
                click.secho(
                    f"Invalid YAML structure in {input_path}: missing "
                    "'journals' key.",
                    fg="red"
                )
            return []
        journals = journal_data["journals"]

    else:
        if verbose:
            click.secho(
                f"Unsupported input format: {suffix}. Use .csv, .yaml, or .yml.",
                fg="red"
            )
        return []

    # Apply scope filtering
    if allowed_keys is not None:
        allowed_keys = sorted(allowed_keys, key=lambda k: (k != "issn", k))

    # Building the export json dict
    journals_dict = {}
    for j in journals:
        j_issn = j.get("issn")
        journals_dict[j_issn] = {}
        for key, value in j.items():
            if key in allowed_keys and key != "issn":
                journals_dict[j_issn][key] = value

    # Write JSON to disk if output path is provided
    if output_fpath is not None or issn is not None:
        resolved = ensure_output_fpath(output_fpath, input_path, ".json", issn)
        ensure_dir(resolved.parent)
        with open(resolved, "w", encoding="utf-8") as f:
            json.dump({"journals": journals_dict}, f, indent=2, ensure_ascii=False)
        if verbose:
            click.secho(f"Saved JSON → {resolved}", fg="green")

    return journals_dict
