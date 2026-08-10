import csv
import io
import time
from pathlib import Path

import click
import requests
import yaml

from config import (
    GITHUB_JOURNAL_DATA_URL,
    JOURNAL_COLLECTION_PATH,
    METADATA_SCHEMA_PATH,
    RAW_JOURNAL_METADATA_PATH,
)
from utils import (
    load_journal_data_from_csv,
    load_schema,
    parse_csv_rows_with_schema,
    write_csv_to_disk,
    write_yaml_to_disk,
)

DOAJ_ENRICHMENT_SOURCE = "doaj.org"
PROTECTED_FIELDS = {"id", "issn"}
ISSN_KEYS = ("issn", "eissn", "pissn")

def normalize_issn(value: str | None) -> str | None:
    """
    Normalize an ISSN for comparison: strip, uppercase, hyphenate.
    """
    if not value:
        return None

    issn = "".join(str(value).split()).upper()
    if len(issn) == 8 and "-" not in issn:
        issn = f"{issn[:4]}-{issn[4:]}"
    return issn or None


def build_issn_index(existing_journals: list[dict]) -> dict[str, dict]:
    """
    Map every known ISSN (issn, eissn, pissn) to its journal.

    A primary "issn" always wins over a secondary ISSN of another journal, so
    that an incoming record is attached to the entry it actually identifies.
    """
    index: dict[str, dict] = {}

    for key in ISSN_KEYS:
        for journal in existing_journals:
            issn = normalize_issn(journal.get(key))
            if not issn:
                continue
            # "issn" is filled in first, later keys must not override it
            index.setdefault(issn, journal)

    return index


def journal_issns(journal: dict) -> set[str]:
    """
    Return all normalized ISSNs of a journal.
    """
    return {
        issn for issn in (normalize_issn(journal.get(k)) for k in ISSN_KEYS)
        if issn
    }


def apply_djd_defaults(journal: dict, schema_fields: list[dict]) -> dict:
    """
    Fill in the collection-managed ("djd") fields of a new journal.

    Only applied to journals that are not yet in the collection: for existing
    entries these values are curated (e.g. is_active=False for a dead journal)
    and must never be reset to a schema default.
    """
    for field in schema_fields:
        if field.get("source") == "djd" and field["name"] != "id":
            journal.setdefault(field["name"], field.get("default"))
    return journal


def should_update_from_doaj(existing_journal: dict) -> bool:
    """
    Whether an existing journal may be refreshed from the DOAJ API.

    Only entries whose metadata came from DOAJ alone are refreshed. Manually
    curated entries — including mixed sources such as
    "doaj.org, journal homepage" — are left untouched.
    """
    source = existing_journal.get("enrichment_source") or ""
    return source.strip() == DOAJ_ENRICHMENT_SOURCE


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
        click.secho(f"Error retrieving journal metadata from GitHub: {e}", fg="red")
        return None


def extract_doaj_value(bibjson: dict, source_path: str):
    """
    Extract a value from a DOAJ bibjson dict using a source_path expression.

    Supported patterns:
      "eissn"             → bibjson["eissn"]
      "publisher.name"    → bibjson["publisher"]["name"]
      "subject[]"         → bibjson["subject"]  (full list)
      "subject[].term"    → [s["term"] for s in bibjson["subject"]]
    """
    # Example: subject[] and subject[].term
    if "[]" in source_path:
        bracket_index = source_path.index("[]")
        list_key = source_path[:bracket_index]  # subject
        nested_key = source_path[bracket_index + 2:].lstrip(".")  # term
        nested_items = bibjson.get(list_key, [])

        if not isinstance(nested_items, list):
            return

        if nested_key:
            nested_values = []
            for item in nested_items:
                if isinstance(item, dict) and item.get(nested_key) is not None:
                    nested_values.append(item[nested_key])
            return nested_values

        return nested_items

    # Example: publisher.name
    if "." in source_path:
        obj = bibjson
        for part in source_path.split("."):
            if not isinstance(obj, dict):
                return

            obj = obj.get(part)
            if obj is None or obj == "":
                return
        return obj

    # Example: plain key like "eissn" etc.
    val = bibjson.get(source_path)
    return val if val is not None else None


def enrich_journal_with_doaj(
    journal: dict,
    doaj_schema_fields: list[dict],
    timeout: int = 20,
    sleep: float = 0.5,
) -> dict:
    """
    Enrich a single journal dict with DOAJ metadata.

    On a miss or an API error the journal is returned unchanged: an existing
    "enrichment_source" and previously collected metadata are never wiped.
    """
    issn = journal.get("issn", "") or journal.get("ISSN", "")
    if not issn:
        journal.setdefault("enrichment_source", None)
        return journal

    try:
        doaj_api_url = f"https://doaj.org/api/search/journals/issn:{issn}"
        response = requests.get(doaj_api_url, timeout=timeout)
        response.raise_for_status()
        results = response.json().get("results", [])
        time.sleep(sleep)

        if not results:
            click.secho(f"  No DOAJ entry found for {issn}.", fg="yellow")
            journal.setdefault("enrichment_source", None)
            return journal

        # Get bibjson metadata section from response
        bibjson = results[0].get("bibjson", {})

        # Parse bibjson based on schema.yaml; keep falsy values such as
        # "boai: false" — only a missing value is skipped
        doaj_metadata = {}
        for field in doaj_schema_fields:
            result = extract_doaj_value(bibjson, field["source_path"])
            if result is not None:
                doaj_metadata[field["name"]] = result

        return {
            **journal,
            **doaj_metadata,
            "enrichment_source": DOAJ_ENRICHMENT_SOURCE,
        }

    except Exception as e:
        click.secho(
            f"Error getting metadata from doaj.org for ISSN {issn}: {e}",
            fg="red"
        )
        journal.setdefault("enrichment_source", None)
        return journal


def enrich_journals_with_doaj(
    journals: list[dict],
    schema_fields: list[dict] | None = None,
    max_num: int | None = None,
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
            enriched.append(journal)
            continue

        issn = journal.get("issn", "") or journal.get("ISSN", "")
        if issn:
            click.secho(
                f"[{i}/{total}] Adding metadata from doaj.org to {issn}...",
                fg="blue"
            )

        enriched.append(
            enrich_journal_with_doaj(
                journal, doaj_schema_fields, timeout=timeout, sleep=sleep
            )
        )

    return enriched


def load_existing_journals(
    fpath: Path = JOURNAL_COLLECTION_PATH
) -> list[dict]:
    """
    Load existing journals from the processed YAML file.
    Returns an empty list if the file doesn"t exist or is empty.
    """
    fpath = Path(fpath)
    if fpath.exists() and fpath.is_file():
        with open(fpath, "r", encoding="utf-8") as f:
            existing_data = yaml.safe_load(f)
        if existing_data:
            return existing_data.get("journals", [])
    return []


def is_duplicate_journal(
    journal: dict,
    issn_index: dict[str, dict],
    schema_fields: list[dict] | None = None,
) -> tuple[str, dict | None]:
    """
    Check whether journal already exists in the collection.

    Matching is done on all ISSNs of an entry (issn, eissn, pissn) so that an
    input row identifying a journal by its print ISSN still finds the entry
    that stores it as its electronic one.

    Returns:
        ("new",       None)    — not in collection, add with full processing
        ("duplicate", journal) — exists with identical data, skip
        ("update",    journal) — exists but data has changed, merge in-place
    """
    if schema_fields is None:
        schema_fields = load_schema()

    incoming_issns = journal_issns(journal)
    if not incoming_issns:
        return "new", None

    matched = next(
        (issn_index[issn] for issn in incoming_issns if issn in issn_index),
        None
    )
    if matched is None:
        return "new", None

    # Compare only schema fields the input actually provides — a CSV brings
    # its columns, a curated YAML may bring DOAJ-level fields too. "id" and
    # "issn" are excluded: they belong to the collection, not to the input.
    comparable_keys = (
        {f["name"] for f in schema_fields} & set(journal) - PROTECTED_FIELDS
    )

    has_changes = any(
        journal.get(key) is not None and journal.get(key) != matched.get(key)
        for key in comparable_keys
    )

    # An unknown ISSN on a matched journal is new information too
    if not incoming_issns <= journal_issns(matched):
        has_changes = True

    if not has_changes:
        return "duplicate", matched

    return "update", matched


def merge_journal_update(
    existing_journal: dict,
    new_journal: dict,
    schema_fields: list[dict]
) -> tuple[dict, bool]:
    """
    Merge new journal data into existing journal, preserving non-core metadata.
    Only updates fields defined in schema with source 'csv' or 'doaj'.
    """
    # Get all fields that should be updated from CSV/DOAJ
    schema_level_base_or_core = {
        f["name"] for f in schema_fields
        if f.get("schema_level") in {"base", "core"}
    }
    schema_level_full = {
        f["name"] for f in schema_fields
        if f.get("schema_level") == "full"
    }

    # Preserve existing journal, but update with new base/core/doaj fields.
    # "id" and "issn" identify the entry and are never taken from the input.
    doaj_metadata_updated = False
    merged = dict(existing_journal)

    for key, value in new_journal.items():
        if key in PROTECTED_FIELDS or value is None:
            continue
        if key in schema_level_base_or_core:
            merged[key] = value
        elif key in schema_level_full:
            merged[key] = value
            doaj_metadata_updated = True

    return merged, doaj_metadata_updated


def process_single_journal(
    input_fpath: Path | str | None = None,
    schema_path: Path | str | None = METADATA_SCHEMA_PATH,
    output_fpath: Path = JOURNAL_COLLECTION_PATH,
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

        try:
            # csv
            if suffix == ".csv":
                rows = load_journal_data_from_csv(fpath)
                if not rows:
                    return False
                parsed = parse_csv_rows_with_schema(
                    rows, schema_fields, assign_djd_defaults=False
                )
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
            click.secho(
                f"Error parsing file: {e}"
                "Does your file align with the metadata specs?"
            )
            return False
    else:
        click.secho("No input provided. Aborting.", fg="red")
        return False

    # Step 2: Validate required fields
    missing = [
        f["name"] for f in schema_core
        if f.get("required") and not journal.get(f["name"])
    ]
    if missing:
        click.secho(f"Missing required fields: {", ".join(missing)}", fg="red")
        return False

    # Step 3: Duplicate check
    existing_journals = load_existing_journals(output_fpath)
    issn_index = build_issn_index(existing_journals)
    status, matched = is_duplicate_journal(journal, issn_index, schema_fields)
    if status == "duplicate":
        # Nothing to do is not an error: reruns must stay green
        click.secho(
            f"Journal with ISSN {journal.get("issn", "")} already exists "
            "in collection with identical data. Skipping.",
            fg="yellow"
        )
        return True

    # Merge existing journal (same ISSN) with updated metadata
    if status == "update":
        for i, existing_journal in enumerate(existing_journals):
            if existing_journal["id"] == matched["id"]:
                merged, doaj_metadata_updated = merge_journal_update(
                    existing_journal, journal, schema_fields
                )
                # Only refresh from DOAJ when the entry is DOAJ-sourced and the
                # input did not bring its own metadata (prevents API overwrites)
                if (
                    not doaj_metadata_updated
                    and should_update_from_doaj(existing_journal)
                ):
                    merged = enrich_journals_with_doaj([merged], schema_fields)[0]
                existing_journals[i] = merged
                write_yaml_to_disk(existing_journals, output_fpath)
                return True

    # Assign next available ID
    journal["id"] = max(
        (j.get("id") or 0 for j in existing_journals), default=0
    ) + 1
    apply_djd_defaults(journal, schema_fields)

    # Sort journal keys
    journal = {"id": journal.pop("id"), **journal}

    # Step 4: DOAJ enrichment
    journal = enrich_journals_with_doaj([journal], schema_fields)[0]

    # Step 5: Append and write
    existing_journals.append(journal)
    write_yaml_to_disk(existing_journals, output_fpath)

    return True


def process_all_journals(
    input_fpath: Path = RAW_JOURNAL_METADATA_PATH,
    schema_path: Path | str | None = None,
    output_fpath: Path = JOURNAL_COLLECTION_PATH,
    dry_run: bool = False,
    force_doaj: bool = False,
) -> bool:
    """
    Core processing workflow: fetch → save CSV → parse → enrich → save YAML.

    Journals already present in the collection are matched by ISSN and merged
    in place, keeping their id. They are only refreshed from the DOAJ API when
    their "enrichment_source" is exactly "doaj.org" (or when force_doaj is
    set); manually curated entries are left alone. Journals that are in the
    collection but not in the input are passed through untouched.
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

    # Step 2: parse rows → list of dicts.
    journals = parse_csv_rows_with_schema(
        rows, schema_fields, assign_djd_defaults=False
    )
    click.secho(f"Parsed {len(journals)} journals.", fg="blue")

    # Step 3: Match incoming journals against the collection by ISSN
    existing_journals = load_existing_journals(output_fpath)
    issn_index = build_issn_index(existing_journals)

    updated_by_id: dict[int, dict] = {}  # existing id → merged journal
    new_journals: list[dict] = []        # not in the collection yet
    enrich_ids: set[int] = set()         # existing ids needing a DOAJ lookup
    counts = {"new": 0, "updated": 0, "unchanged": 0, "protected": 0}

    for journal in journals:
        status, matched = is_duplicate_journal(
            journal, issn_index, schema_fields
        )

        if status == "new":
            new_journals.append(journal)
            counts["new"] += 1
            continue

        # Merge existing journal (same ISSN) with new core fields; the merged
        # copy replaces the existing entry under its unchanged id.
        base = updated_by_id.get(matched["id"], matched)
        merged, _ = merge_journal_update(base, journal, schema_fields)
        updated_by_id[matched["id"]] = merged

        if status == "duplicate":
            counts["unchanged"] += 1
        else:
            counts["updated"] += 1

        # Refresh from DOAJ only for DOAJ-sourced entries — hand-curated
        # metadata (e.g. "journal homepage") must not be overwritten
        if force_doaj or should_update_from_doaj(matched):
            enrich_ids.add(matched["id"])
        else:
            counts["protected"] += 1

    # Step 4: Assign ids to genuinely new journals; existing ids are untouched
    next_id = max(
        (j.get("id") or 0 for j in existing_journals), default=0
    ) + 1
    schema_order = [f["name"] for f in schema_fields]
    for journal in new_journals:
        journal["id"] = next_id
        next_id += 1
        apply_djd_defaults(journal, schema_fields)
        # Sort keys like the schema so new entries match existing ones.
        # Done in place: to_enrich holds references to these dicts.
        ordered = {key: journal[key] for key in schema_order if key in journal}
        extras = {k: v for k, v in journal.items() if k not in ordered}
        journal.clear()
        journal.update(ordered)
        journal.update(extras)

    untouched = len(existing_journals) - len(updated_by_id)
    click.secho(
        f"{len(existing_journals)} in collection · {len(journals)} input rows: "
        f"{counts["new"]} new, {counts["updated"]} updated, "
        f"{counts["unchanged"]} unchanged ({counts["protected"]} protected "
        f"from DOAJ), {untouched} not in input.",
        fg="blue"
    )
    to_enrich = [updated_by_id[i] for i in enrich_ids] + new_journals
    click.secho(f"{len(to_enrich)} journals to enrich via doaj.org.", fg="blue")

    if dry_run:
        click.secho("Dry run — no DOAJ requests, nothing written.", fg="yellow")
        return True

    # Step 5: enrich with DOAJ metadata
    enriched_by_id = {
        j["id"]: j
        for j in enrich_journals_with_doaj(to_enrich, schema_fields)
    }

    # Step 6: Rebuild the collection in its original order. Entries missing
    # from the input are carried over unchanged.
    final_journals = [
        enriched_by_id.get(j["id"], updated_by_id.get(j["id"], j))
        for j in existing_journals
    ]
    final_journals.extend(
        enriched_by_id.get(j["id"], j) for j in new_journals
    )

    write_yaml_to_disk(final_journals, output_fpath)
    return True
