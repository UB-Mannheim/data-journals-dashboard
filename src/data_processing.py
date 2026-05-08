import csv
import io
import time
import click
import requests
import yaml
from pathlib import Path


CRAWL_URL = "https://raw.githubusercontent.com/MaxiKi/data-journals/refs/heads/main/data_journals_characteristics.csv"
RAW_CSV_PATH = Path("data/raw/data_journals.csv")
PROCESSED_YAML_PATH = Path("data/processed/data_journals.yaml")


def ensure_dir(dir_path: Path | str):
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def get_journal_data_from_github() -> list[list[str]] | None:
    """
    Fetch the latest data journal CSV from GitHub and return parsed rows.
    """
    try:
        click.secho("Fetching data journal data from GitHub...", fg="blue")
        response = requests.get(CRAWL_URL)
        response.raise_for_status()
        return list(csv.reader(io.StringIO(response.text)))
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


def parse_csv_rows(rows: list[list[str]]) -> list[dict]:
    """
    Convert CSV rows (header + data) to list of dicts with sequential id.
    """
    if not rows:
        return []
    header = rows[0]
    journals = []
    for idx, row in enumerate(rows[1:], start=1):
        record = {"id": idx}
        for col, val in zip(header, row):
            record[col.strip()] = val.strip()
        journals.append(record)
    return journals


def get_doaj_metadata(issn: str, timeout: int = 20) -> dict:
    """
    Query DOAJ API and extract all bibjson fields.
    """
    doaj_api_url = f"https://doaj.org/api/search/journals/issn:{issn}"
    try:
        response = requests.get(doaj_api_url, timeout=timeout)
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            return {}

        # Get bibjson data (contains relevant metadata)
        b = results[0].get("bibjson", {})

        # Get research fields and subjects
        research_field = []
        for subject in b.get("subject", []):
            if "term" in subject:
                research_field.append(subject["term"])
                subject_codes = {
                    "term": subject["term"],
                    "code": subject.get("code"),
                    "scheme": subject.get("scheme")
                }

        # Return complete metadata for current ISSN
        return {
            # Identifiers
            "eissn": b.get("eissn"),
            "pissn": b.get("pissn"),
            "title": b.get("title"),
            "language": b.get("language", []),
            "oa_start": b.get("oa_start"),
            "boai": b.get("boai"),
            "publication_time_weeks": b.get("publication_time_weeks"),
            "keywords": b.get("keywords", []),

            # Subjects and research fields
            "research_field": research_field,
            "subject_codes": subject_codes,

            # Publisher & institution
            "publisher_name": b.get("publisher", {}).get("name"),
            "publisher_country": b.get("publisher", {}).get("country"),
            "institution_name": b.get("institution", {}).get("name"),
            "institution_country": b.get("institution", {}).get("country"),

            # Editorial
            "review_process": b.get("editorial", {}).get("review_process", []),
            "review_url": b.get("editorial", {}).get("review_url"),
            "board_url": b.get("editorial", {}).get("board_url"),

            # Licensing
            "license_types": [l["type"] for l in b.get("license", [])],
            "license_details": b.get("license", []),

            # APC
            "apc_has": b.get("apc", {}).get("has_apc"),
            "apc_max": b.get("apc", {}).get("max", []),
            "apc_url": b.get("apc", {}).get("url"),
            "other_charges": b.get("other_charges", {}).get(
                "has_other_charges"
            ),

            # Waiver
            "waiver_has": b.get("waiver", {}).get("has_waiver"),
            "waiver_url": b.get("waiver", {}).get("url"),

            # Preservation
            "preservation_has": b.get("preservation", {}).get(
                "has_preservation"
            ),
            "preservation_services": b.get("preservation", {}).get(
                "service", []
            ),
            "preservation_url": b.get("preservation", {}).get("url"),

            # PIDs
            "pid_schemes": b.get("pid_scheme", {}).get("scheme", []),

            # Plagiarism detection
            "plagiarism_detection": b.get("plagiarism", {}).get("detection"),
            "plagiarism_url": b.get("plagiarism", {}).get("url"),

            # Copyright
            "copyright_author_retains": b.get("copyright", {}).get(
                "author_retains"
            ),
            "copyright_url": b.get("copyright", {}).get("url"),

            # Deposit policy
            "deposit_policy_has": b.get("deposit_policy", {}).get(
                "has_policy"
            ),
            "deposit_policy_services": b.get("deposit_policy", {}).get(
                "service", []
            ),
            "deposit_policy_url": b.get("deposit_policy", {}).get("url"),

            # Article licenses
            "article_license_display": b.get("article", {}).get(
                "license_display", []
            ),
            "article_license_example_url": b.get("article", {}).get(
                "license_display_example_url"
            ),

            # Refs
            "ref_journal": b.get("ref", {}).get("journal"),
            "ref_aims_scope": b.get("ref", {}).get("aims_scope"),
            "ref_oa_statement": b.get("ref", {}).get("oa_statement"),
            "ref_author_instructions": b.get("ref", {}).get(
                "author_instructions"
            ),
            "ref_license_terms": b.get("ref", {}).get("license_terms"),
        }
    except Exception as e:
        click.secho(f"Error fetching DOAJ metadata for {issn}: {e}", fg="red")
    return {}


def enrich_journal_metadata(journals: list[dict]) -> list[dict]:
    """
    Enrich each journal dict with DOAJ metadata.
    """
    enriched = []
    total = len(journals)
    for i, journal in enumerate(journals, start=1):
        issn = journal.get("ISSN", "")
        if issn:
            click.secho(
                f"[{i}/{total}] Adding metadata from doaj.org to {issn}...",
                fg="blue"
            )
            doaj = get_doaj_metadata(issn)
            enriched.append({**journal, **doaj})
            time.sleep(0.5)
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


def create_journal_content_for_hugo(
    data_journals_fpath: Path,
    content_dir: Path
) -> None:
    """
    Enrich the journals.yaml data with DOAJ metadata and generate
    Hugo content files.
    """
    with open(data_journals_fpath) as file:
        data = yaml.safe_load(file)

    for journal in data["journals"]:
        issn = journal["issn"]
        print(f"Processing {issn}...")

        doaj = get_doaj_metadata(issn)
        journal.update(doaj)
        time.sleep(0.5)

        issn_slug = issn.replace("-", "")
        filepath = content_dir / f"{issn_slug}.md"

        front_matter = yaml.dump(
            {**journal},
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False
        )
        filepath.write_text(f"---\n{front_matter}---\n")

    with open(data_journals_fpath, "w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    print(f"Done. Generated {len(data['journals'])} journal pages.")


def process_journal_metadata(
    crawl_csv: bool = False,
    csv_fpath: Path | None = None,
    schema_path: Path | str | None = None,
) -> bool:
    """
    Core processing workflow: fetch → save CSV → parse → enrich → save YAML.
    """
    # Step 1: load raw CSV rows
    rows = None
    if crawl_csv:
        rows = get_journal_data_from_github()
    elif csv_fpath:
        rows = get_journal_data_from_csv(csv_fpath)

    if rows is None:
        click.secho(
            "→ No data source provided or data fetch failed.",
            fg="red"
        )
        return False

    # Step 2: save raw CSV
    save_csv_to_disk(rows, RAW_CSV_PATH)

    # Step 3: parse rows → list of dicts
    journals = parse_csv_rows(rows)
    click.secho(f"Parsed {len(journals)} journals.", fg="blue")

    # Step 4: enrich with DOAJ metadata
    enriched = enrich_journal_metadata(journals)

    # Step 5: save enriched YAML
    write_yaml_to_disk(enriched, PROCESSED_YAML_PATH)
    
    # Step 6: Create hugo content files

    return True


@click.command(no_args_is_help=True)
@click.option(
    "--crawl_csv", "-c",
    is_flag=True,
    default=False,
    help="Crawl the data journal metadata from GitHub.",
)
@click.option(
    "--csv_fpath", "-f",
    type=click.Path(path_type=Path),
    default=None,
    show_default=False,
    help="Load and parse a local CSV with data journal metadata.",
)
@click.option(
    "--schema_path", "-s",
    type=click.Path(path_type=Path),
    default=None,
    show_default=False,
    help="Path to the journal metadata schema YAML file.",
)
def main(
    crawl_csv: bool = False,
    csv_fpath: Path | None = None,
    schema_path: Path | None = None,
):
    """
    Process data journal metadata: fetch CSV, enrich with DOAJ, save YAML.
    """
    process_journal_metadata(
        crawl_csv=crawl_csv,
        csv_fpath=csv_fpath,
        schema_path=schema_path,
    )


if __name__ == "__main__":
    main()
