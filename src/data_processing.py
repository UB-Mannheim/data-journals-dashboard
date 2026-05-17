import csv
import io
import time
import click
import requests
import yaml
from pathlib import Path

from utils import (
    load_schema,
    load_journal_data_from_csv,
    parse_csv_rows_with_schema,
    write_csv_to_disk,
    write_yaml_to_disk
)
from config import (
    GITHUB_JOURNAL_DATA_URL,
    METADATA_SCHEMA_PATH,
    RAW_JOURNAL_METADATA_PATH,
    PROCESSED_JOURNAL_METADATA_PATH
)


def get_journal_data_from_github() -> list[list[str]] | None:
    """
    Fetch the latest data journal CSV from GitHub and return parsed rows.
    """
    try:
        click.secho("Fetching data journal data from GitHub...", fg="blue")
        response = requests.get(GITHUB_JOURNAL_DATA_URL)
        response.raise_for_status()
        return list(csv.reader(io.StringIO(response.text.strip())))
    except Exception as e:
        click.secho(f"Error during data crawl: {e}", fg="red")
        return None


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
    doaj_schema_fields = [f for f in (schema_fields or []) if f["source"] == "doaj"]

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


def load_existing_journals() -> list[dict]:
    """
    Load existing journals from the processed YAML file.
    Returns an empty list if the file doesn"t exist or is empty.
    """
    if PROCESSED_JOURNAL_METADATA_PATH.exists():
        with open(PROCESSED_JOURNAL_METADATA_PATH, "r", encoding="utf-8") as f:
            existing_data = yaml.safe_load(f)
        if existing_data:
            return existing_data.get("journals", [])
    return []


def is_duplicate_journal(
    journal: dict,
    existing_journals: list[dict]
) -> tuple[str, int | None]:
    """
    Check whether journal already exists in the collection.

    Returns:
        ("new",       None) — not in collection, add with full processing
        ("duplicate", id)   — exists with identical data, skip
        ("update",    id)   — exists but data has changed, merge in-place
    """
    schema_fields = load_schema()

    incoming_issn = journal.get("issn")
    if not incoming_issn:
        return "new", None

    matched = next(
        (j for j in existing_journals if j.get("issn") == incoming_issn),
        None
    )
    if matched is None:
        return "new", None

    # Check if any of the matched journal's key is updated
    comparable_keys = {
        f["key"] for f in schema_fields
        if f.get("source") in {"csv", "doaj"}
    }
    has_changes = any(
        journal.get(key) is not None and journal.get(key) != matched.get(key)
        for key in comparable_keys
    )

    if not has_changes:
        return "duplicate", matched["id"]

    return "update", matched["id"]


def merge_journal_update(
    existing_journal: dict,
    new_journal: dict,
    schema_fields: list[dict]
) -> tuple[dict | bool]:
    """
    Merge new journal data into existing journal, preserving non-core metadata.
    Only updates fields defined in schema with source 'csv' or 'doaj'.
    """
    # Get all fields that should be updated from CSV/DOAJ
    schema_source_csv = {
        f["key"] for f in schema_fields
        if f.get("source") == "csv"
    }
    schema_source_doaj = {
        f["key"] for f in schema_fields
        if f.get("source") == "doaj"
    }

    # Preserve existing journal, but update with new core/doaj fields
    doaj_metadata_updated = False
    merged = dict(existing_journal)

    for key, value in new_journal.items():
        if key in schema_source_csv and value is not None:
            merged[key] = value
        elif key in schema_source_doaj and value is not None:
            merged[key] = value
            doaj_metadata_updated = True

    return merged, doaj_metadata_updated


def process_single_journal(
    input_fpath: str | Path = None,
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

    schema_core = [f for f in schema_fields if f["source"] == "csv"]

    # Step 1: Parse input → dict with schema keys
    journal = None
    if input_fpath is not None:
        fpath = Path(input_fpath)
        suffix = fpath.suffix.lower()

        # csv
        try:
            if suffix == ".csv":
                rows = load_journal_data_from_csv(fpath)
                if not rows:
                    return False
                parsed = parse_csv_rows_with_schema(rows, schema_fields)
                if not parsed:
                    click.secho("No records found in CSV file.", fg="red")
                    return False
                journal = parsed[0]

            # yaml
            elif suffix in (".yaml", ".yml"):
                with open(fpath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and "journal" in data:
                    journal = data["journal"][0]
                elif isinstance(data, dict) and "journals" in data:
                    journal = data["journals"][0]
                elif isinstance(data, list):
                    journal = data[0]
                else:
                    journal = data

            else:
                click.secho(f"Unsupported file type: {suffix}", fg="red")
                return False
        except Exception as e:
            click.secho(f"Error parsing file: {e}")
            return False
    else:
        click.secho("No input provided. Aborting.", fg="red")
        return False

    # Step 2: Validate required fields
    missing = [
        f["key"] for f in schema_core
        if f.get("required") and not journal.get(f["key"])
    ]
    if missing:
        click.secho(f"Missing required fields: {", ".join(missing)}", fg="red")
        return False

    # Step 3: Duplicate check
    existing_journals = load_existing_journals()
    status, existing_id = is_duplicate_journal(journal, existing_journals)
    if status == "duplicate":
        click.secho(
            f"Journal with ISSN {journal.get("issn", "")} already exists "
            "in collection. Aborting.",
            fg="yellow"
        )
        return False

    # Merge existing journal (same ISSN) with updated metadata
    if status == "update":
        for i, existing_journal in enumerate(existing_journals):
            if existing_journal["id"] == existing_id:
                journal, doaj_metadata_updated = merge_journal_update(
                    existing_journal, journal, schema_fields
                )
                # Enrich if DOAJ metadata was NOT updated (prevent API overwrites)
                if not doaj_metadata_updated:
                    journal = enrich_journals_with_doaj([journal], schema_fields)[0]
                existing_journals[i] = journal
                write_yaml_to_disk(existing_journals, PROCESSED_JOURNAL_METADATA_PATH)
                return True

    # Assign next available ID
    journal["id"] = max((j.get("id", 0) for j in existing_journals), default=0) + 1

    # Sort journal keys
    journal = {"id": journal.pop("id"), **journal}

    # Step 4: DOAJ enrichment
    journal = enrich_journals_with_doaj([journal], schema_fields)[0]

    # Step 5: Append and write
    existing_journals.append(journal)
    write_yaml_to_disk(existing_journals, PROCESSED_JOURNAL_METADATA_PATH)

    return True


def process_all_journals(
    input_fpath: Path = RAW_JOURNAL_METADATA_PATH,
    schema_path: Path | str | None = None,
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
    if not input_fpath.exists():
        rows = get_journal_data_from_github()
        write_csv_to_disk(rows, RAW_JOURNAL_METADATA_PATH)
    else:
        rows = load_journal_data_from_csv(input_fpath)

    if rows is None:
        click.secho("→ No data source provided or data fetch failed.",
                    fg="red")
        return False

    # Step 2: parse rows → list of dicts
    journals = parse_csv_rows_with_schema(rows, schema_fields)
    click.secho(f"Parsed {len(journals)} journals.", fg="blue")

    # Step 3: Filter out duplicates
    existing_journals = load_existing_journals()
    new_journals = []
    merged_ids = set()
    for journal in journals:
        status, existing_id = is_duplicate_journal(
            journal, existing_journals
        )
        if status == "duplicate":
            click.secho(
                f"Journal with ISSN {journal.get("issn", "")} already exists "
                "in collection. Skipping.",
                fg="yellow"
            )
        elif status == "update":
            # Merge existing journal (same ISSN) with new core fields
            for existing_journal in existing_journals:
                if existing_journal["id"] == existing_id:
                    merged = merge_journal_update(
                        existing_journal, journal, schema_fields
                    )
                    new_journals.append(merged)
                    merged_ids.add(existing_id)
                    break
        else:
            # New journal - keep as-is for enrichment
            new_journals.append(journal)
    journals = new_journals

    # Remove merged journals from existing_journals to avoid duplicates
    existing_journals = [
        j for j in existing_journals if j["id"] not in merged_ids
    ]

    # Assign sequential IDs to new journals (merged journals keep their existing ID)
    max_existing_id = max(
        (j.get("id", 0) for j in existing_journals), default=0
    )
    next_new_id = max_existing_id + 1
    for journal in journals:
        # Only assign ID if this journal doesn't already have one (new journal)
        if journal["id"] is None or journal["id"] == 0:
            journal["id"] = next_new_id
            next_new_id += 1
        else:
            # Update max_existing_id to account for merged journal's ID
            max_existing_id = max(max_existing_id, journal["id"])
            next_new_id = max_existing_id + 1

    # Step 4: enrich with DOAJ metadata
    enriched_journals = enrich_journals_with_doaj(journals, schema_fields)

    # Step 5: Append enriched journals and save YAML
    if enriched_journals:
        existing_journals.extend(enriched_journals)
        write_yaml_to_disk(existing_journals, PROCESSED_JOURNAL_METADATA_PATH)
        return True

    return False
