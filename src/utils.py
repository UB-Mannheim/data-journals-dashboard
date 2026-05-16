import click
import csv
import yaml
from pathlib import Path

from config import METADATA_SCHEMA_PATH


def ensure_dir(dir_path: Path | str):
    Path(dir_path).mkdir(parents=True, exist_ok=True)


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
    schema_path: Path | str = METADATA_SCHEMA_PATH
):
    """
    Load schema[schema_level] = "core"
    """
    schema = load_schema(schema_path=schema_path)
    return [
        f["key"] for f in schema
        if f["schema_level"] == "core" and f.get("source") != "generated"
    ]


def get_journal_data_from_csv(fpath: Path) -> list[list[str]] | None:
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
    schema with source "csv" or "generated".
    """
    if not rows:
        return []

    # Get CSV fields from schema
    header = [col.strip() for col in rows[0]]
    csv_fields = [f for f in schema_fields if f["source"] == "csv"]
    csv_col_to_field = {f["csv_column"].strip(): f for f in csv_fields}

    # Get generated fields from schema (id)
    generated_fields = [f for f in schema_fields if f["source"] == "generated"]

    journals = []
    for idx, row in enumerate(rows[1:], start=1):
        # Add generated fields first (id)
        record = {}
        for gf in generated_fields:
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


def write_yaml_to_disk(
    journals: list[dict],
    fpath: Path,
    sort_by_id: bool = True,
    verbose: bool = True
):
    """
    Write enriched journal records to a YAML file.
    """
    class _IgnoreAliases(yaml.Dumper):
        """
        Class overwrite for pyyaml to prevent the inclusion of object aliases
        ("&id001 []") during write execution for identical objects.
        """
        def ignore_aliases(self, _data):
            return True

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


def csv_to_yaml(
    csv_fpath: Path | str = None,
    output_fpath: Path | str = None,
    schema_path: Path | str = METADATA_SCHEMA_PATH,
    verbose: bool = True,
) -> list[dict]:
    """
    Parse a core-schema CSV (e.g. an export) and transform it to a YAML journal
    collection. Optionally, save it to disk.
    """
    schema = load_schema(schema_path=schema_path)

    rows = get_journal_data_from_csv(csv_fpath)
    if not rows:
        if verbose:
            click.secho(
                f"Could not parse CSV for filepath: {csv_fpath}. "
                "Please make sure the file contains valid CSV data.",
                fg="red"
            )
        return []

    journals = parse_csv_rows_with_schema(rows, schema)

    if output_fpath:
        write_yaml_to_disk(
            journals, Path(output_fpath), sort_by_id=False, verbose=verbose
        )

    return journals


def yaml_to_csv(
    yaml_fpath: list[dict] = None,
    output_fpath: Path | str = None,
    schema_path: Path | str = METADATA_SCHEMA_PATH,
    verbose: bool = True,
) -> dict:
    """
    Parse an existing yaml journal collection and transform it to csv.
    Optionally, save it to disk.
    """
    schema = load_schema(schema_path=schema_path)
    csv_fields = [f for f in schema if f.get("source") == "csv"]

    # Load yaml data
    with open(yaml_fpath, "r", encoding="utf-8") as f:
        journal_data = yaml.safe_load(f)

    if not journal_data:
        if verbose:
            click.secho(
                f"Could not parse YAML for filepath: {yaml_fpath}."
                "Please make sure the file contains valid YAML data.",
                fg="red"
            )
        return {}

    rows = [[f["csv_column"] for f in csv_fields]]
    for journal in journal_data["journals"]:
        row = [str(journal.get(f["key"], "")) for f in csv_fields]
        rows.append(row)

    # Optionally: write csv to disk
    if output_fpath:
        write_csv_to_disk(
            rows, Path(output_fpath), verbose, quoting=csv.QUOTE_MINIMAL
        )

    return rows
