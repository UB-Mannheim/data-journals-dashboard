import csv
import io
import time
import click
import requests
import yaml
from pathlib import Path
import json


CRAWL_URL = "https://raw.githubusercontent.com/MaxiKi/data-journals/refs/heads/main/data_journals_characteristics.csv"
METADATA_SCHEMA_PATH = Path("journal_metadata_schema/schema.yaml")
RAW_CSV_PATH = Path("data/raw/data_journals.csv")
PROCESSED_YAML_PATH = Path("data/processed/data_journals.yaml")


def ensure_dir(dir_path: Path | str):
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def load_schema(schema_path: Path) -> list[dict]:
    """
    Load the journal metadata schema and return the list of field definitions.
    """
    try:
        with open(schema_path, 'r', encoding='utf-8') as file:
            schema = yaml.safe_load(file)
        return schema.get('fields', [])
    except Exception as e:
        click.secho(f"Error loading schema from {schema_path}: {e}", fg="red")
        return []


def get_journal_data_from_github() -> list[list[str]] | None:
    """
    Fetch the latest data journal CSV from GitHub and return parsed rows.
    """
    try:
        click.secho("Fetching data journal data from GitHub...", fg="blue")
        response = requests.get(CRAWL_URL)
        response.raise_for_status()
        return list(csv.reader(io.StringIO(response.text.strip())))
    except Exception as e:
        click.secho(f"Error during data crawl: {e}", fg="red")
        return None


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


def save_csv_to_disk(rows: list[list[str]], fpath: Path):
    """
    Write raw CSV rows to disk.
    """
    ensure_dir(fpath.parent)
    with open(fpath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerows(rows)
    click.secho(f"Saved raw CSV → {fpath}", fg="green")


def parse_csv_rows_with_schema(
    rows: list[list[str]],
    schema_fields: list[dict]
) -> list[dict]:
    """
    Convert CSV rows to list of dicts, only including fields defined in
    schema with source 'csv' or 'generated'.
    """
    if not rows:
        return []

    # Get CSV fields from schema
    header = [col.strip() for col in rows[0]]
    csv_fields = [f for f in schema_fields if f['source'] == 'csv']
    csv_col_to_key = {f['csv_column'].strip(): f['key'] for f in csv_fields}

    # Get generated fields from schema (id)
    generated_fields = [f for f in schema_fields if f['source'] == 'generated']

    journals = []
    for idx, row in enumerate(rows[1:], start=1):
        # Add generated fields first (id)
        record = {}
        for gf in generated_fields:
            if gf['key'] == 'id':
                record['id'] = idx
            else:
                record[gf['key']] = gf.get('default')

        # Map CSV columns
        for col, val in zip(header, row):
            col_clean = col.strip()
            if col_clean in csv_col_to_key:
                key = csv_col_to_key[col_clean]
                record[key] = val.strip()
        journals.append(record)

    return journals


def extract_doaj_value(bibjson: dict, doaj_path: str, default):
    """
    Extract a value from a DOAJ bibjson dict using a doaj_path expression.

    Supported patterns:
      "eissn"             → bibjson["eissn"]
      "publisher.name"    → bibjson["publisher"]["name"]
      "subject[]"         → bibjson["subject"]  (full list)
      "subject[].term"    → [s["term"] for s in bibjson["subject"]]
    """
    # Example: subject[] and subject[].term
    if "[]" in doaj_path:
        bracket_index = doaj_path.index("[]")
        list_key = doaj_path[:bracket_index]  # subject
        nested_key = doaj_path[bracket_index + 2:].lstrip(".")  # term
        nested_items = bibjson.get(list_key, [])

        if not isinstance(nested_items, list):
            return default

        if nested_key:
            nested_values = []
            for item in nested_items:
                if isinstance(item, dict) and item.get(nested_key) is not None:
                    nested_values.append(item[nested_key])
            return nested_values

        return nested_items or default

    # Example: publisher.name
    if "." in doaj_path:
        obj = bibjson
        for part in doaj_path.split("."):
            if not isinstance(obj, dict):
                return default

            obj = obj.get(part)
            if obj is None:
                return default
        return obj

    # Example: plain key like "eissn" etc.
    val = bibjson.get(doaj_path)
    return val if val is not None else default


def enrich_journals_with_doaj(
    journals: list[dict],
    schema_fields: list[dict] | None = None,
    max_num: int = None,
    timeout: int = 20,
    sleep: float = 0.5
) -> list[dict]:
    """
    Enrich each journal dict with DOAJ metadata, optionally filtered by schema.
    """
    doaj_schema_fields = [f for f in (schema_fields or []) if f['source'] == 'doaj']

    enriched = []
    total = len(journals)
    for i, journal in enumerate(journals, start=1):
        if max_num and i > max_num:
            break

        issn = journal.get("issn", "") or journal.get("ISSN", "")
        if not issn:
            enriched.append(journal)
            continue

        click.secho(
            f"[{i}/{total}] Adding metadata from doaj.org to {issn}...",
            fg="blue"
        )
        try:
            doaj_api_url = f"https://doaj.org/api/search/journals/issn:{issn}"
            response = requests.get(doaj_api_url, timeout=timeout)
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                click.secho(f"  No DOAJ entry found for {issn}.", fg="yellow")
                enriched.append(journal)
                time.sleep(sleep)
                continue

            # Get bibjson metadata section from response
            bibjson = results[0].get("bibjson", {})

            # Parse bibjson based on schema.yaml
            doaj_metadata = {}
            for field in doaj_schema_fields:
                result = extract_doaj_value(
                    bibjson, field["doaj_path"], field.get("default")
                )
                doaj_metadata[field["key"]] = result
            enriched.append({**journal, **doaj_metadata})
            time.sleep(sleep)

        except Exception as e:
            click.secho(
                f"Error getting metadata from doaj.org for ISSN {issn}: {e}",
                fg="red"
            )
            enriched.append(journal)

    return enriched


def write_yaml_to_disk(journals: list[dict], fpath: Path):
    """
    Write enriched journal records to a YAML file.
    """
    ensure_dir(fpath.parent)
    with open(fpath, "w", encoding="utf-8") as file:
        yaml.dump(
            {"journals": journals},
            file,
            allow_unicode=True,
            sort_keys=False
        )
    click.secho(f"Saved enriched YAML → {fpath}", fg="green")


def process_single_journal(
    input_fpath: str | Path = None,
    csv_string: str = None,
    yaml_string: str = None,
    json_string: str = None,
    schema_path: Path | str | None = METADATA_SCHEMA_PATH,
) -> bool:
    """
    Process a single data journal from various inputs.
    """
    # Load schema
    schema_path = Path(schema_path) if schema_path else METADATA_SCHEMA_PATH
    schema_fields = load_schema(schema_path)
    if not schema_fields:
        click.secho("Failed to load schema. Aborting.", fg="red")
        return False

    core_metadata = [f for f in schema_fields if f['source'] == 'csv']

    # Step 1: Parse input → dict with schema keys
    journal = None

    # csv string
    if csv_string is not None:
        rows = list(csv.reader(io.StringIO(csv_string.strip())))
        if not rows:
            click.secho("Empty CSV string.", fg="red")
            return False

        # Detect if first row is a header
        known_columns = {f['csv_column'] for f in core_metadata}
        if rows[0][0].strip() not in known_columns:
            header = [f['csv_column'] for f in core_metadata]
            rows = [header] + rows

        parsed = parse_csv_rows_with_schema(rows, schema_fields)
        if not parsed:
            click.secho("Failed to parse CSV string.", fg="red")
            return False

        journal = parsed[0]

    # yaml string
    elif yaml_string is not None:
        data = yaml.safe_load(yaml_string)
        journal = (
            data['journals'][0] if isinstance(data, dict)
            and 'journals' in data else data
        )

    # json string
    elif json_string is not None:
        data = json.loads(json_string)
        journal = (
            data['journals'][0] if isinstance(data, dict)
            and 'journals' in data else data
        )

    # Load filepaths (csv, yaml, json)
    elif input_fpath is not None:
        fpath = Path(input_fpath)
        suffix = fpath.suffix.lower()

        if suffix == '.csv':
            rows = get_journal_data_from_csv(fpath)
            if not rows:
                return False
            parsed = parse_csv_rows_with_schema(rows, schema_fields)
            if not parsed:
                click.secho("No records found in CSV file.", fg="red")
                return False
            journal = parsed[0]

        elif suffix in ('.yaml', '.yml'):
            with open(fpath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            journal = (
                data['journals'][0] if isinstance(data, dict)
                and 'journals' in data else data
            )

        elif suffix == '.json':
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            journal = (
                data['journals'][0] if isinstance(data, dict)
                and 'journals' in data else data
            )

        else:
            click.secho(f"Unsupported file type: {suffix}", fg="red")
            return False
    else:
        click.secho("No input provided. Aborting.", fg="red")
        return False

    # Step 2: Validate required fields
    missing = [
        f['key'] for f in core_metadata
        if f.get('required') and not journal.get(f['key'])
    ]
    if missing:
        click.secho(f"Missing required fields: {', '.join(missing)}", fg="red")
        return False

    # Step 3: Duplicate check
    existing_journals = []
    if PROCESSED_YAML_PATH.exists():
        with open(PROCESSED_YAML_PATH, 'r', encoding='utf-8') as f:
            existing_data = yaml.safe_load(f)
        if existing_data:
            existing_journals = existing_data.get('journals', [])
        else:
            []

    issn = journal.get('issn', '')
    if any(j.get('issn') == issn for j in existing_journals):
        click.secho(
            f"Journal with ISSN {issn} already exists. Aborting.",
            fg="yellow"
        )
        return False

    # Assign next available ID
    journal['id'] = max(
        (j.get('id', 0) for j in existing_journals), default=0
    ) + 1

    # Step 4: DOAJ enrichment
    journal = enrich_journals_with_doaj([journal], schema_fields)[0]

    # Step 5: Append and write
    existing_journals.append(journal)
    write_yaml_to_disk(existing_journals, PROCESSED_YAML_PATH)

    return True


def process_all_journals(
    schema_path: Path | str | None = None,
    max_num: int | None = None,
) -> bool:
    """
    Core processing workflow: fetch → save CSV → parse → enrich → save YAML.
    """
    # Load metadata schema
    schema_fields = None
    if schema_path:
        schema_path = Path(schema_path)
        if schema_path.exists():
            schema_fields = load_schema(schema_path)
    else:
        click.secho(f"Schema does not exist: {schema_path}. Aborting.",
                    fg="yellow")
        return False

    # Step 1: Load collected raw journal metadata
    rows = None
    if not RAW_CSV_PATH.exists():
        rows = get_journal_data_from_github()
        save_csv_to_disk(rows, RAW_CSV_PATH)
    else:
        rows = get_journal_data_from_csv(RAW_CSV_PATH)

    if rows is None:
        click.secho("→ No data source provided or data fetch failed.",
                    fg="red")
        return False

    # Step 2: parse rows → list of dicts
    journals = parse_csv_rows_with_schema(rows, schema_fields)
    click.secho(f"Parsed {len(journals)} journals.", fg="blue")

    # Step 3: enrich with DOAJ metadata
    enriched_journals = enrich_journals_with_doaj(journals, schema_fields, max_num=max_num)

    # Step 4: save enriched YAML
    write_yaml_to_disk(enriched_journals, PROCESSED_YAML_PATH)
