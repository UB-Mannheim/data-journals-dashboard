import csv
import click
import json
import requests
from pathlib import Path


CRAWL_URL = "https://raw.githubusercontent.com/MaxiKi/data-journals/refs/heads/main/data_journals_characteristics.csv"


def ensure_dir(dir_path: Path | str):
    """
    Create a target directory (and parent directories) if it does not exist.
    """
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def get_journal_data_from_github():
    """
    Fetch the latest data journal CSV from GitHub and return parsed rows.
    """
    try:
        click.secho("Fetching data journal data from GitHub...", fg="blue")
        response = requests.get(CRAWL_URL)
        if response.status_code == 200:
            # Split raw text into rows, strip whitespace, split by comma
            data = []
            for row in response.text.split("\n"):
                if row.strip():
                    clean_row = row.strip().replace("\r", "").split(",")
                    data.append(clean_row)
            return data
        click.secho(
            f"Failed to fetch data: HTTP {response.status_code}",
            fg="red"
        )
        return None
    except Exception as e:
        click.secho(f"Error during data crawl: {e}", fg="red")
        return None


def get_journal_data_from_csv(csv_fpath: Path | str):
    """
    Read a local CSV file and return parsed rows.
    """
    csv_fpath = Path(csv_fpath)
    if not csv_fpath.exists():
        click.secho(f"→ Input filepath {csv_fpath} does not exist", fg="red")
        return None
    with open(csv_fpath, "r", encoding="utf-8") as file:
        return list(csv.reader(file))


def parse_journal_data_csv(csv_rows: list[list[str]]):
    """
    Take raw CSV rows, skip the header row, and map to a structured
    journals dictionary.
    """
    journals_dict = {}
    for idx, row in enumerate(csv_rows):
        if idx == 0:  # Skip header row
            continue
        if row:
            journals_dict[idx] = {
                "issn": row[0],
                "journal_title": row[1],
                "publisher": row[2],
                "data_journal_type": row[3]
            }
    return journals_dict


def transform_csv_to_json(journals_dict: dict):
    """
    Convert the parsed journals dictionary into a JSON-serializable structure.
    """
    return journals_dict


def write_json_to_disk(json_data: dict, output_fpath: Path | str):
    """
    Write JSON data to a specified file path with consistent formatting.
    """
    output_fpath = Path(output_fpath)
    output_fpath.parent.mkdir(parents=True, exist_ok=True)
    with open(output_fpath, "w", encoding="utf-8") as file:
        json.dump(json_data, file, indent=4)
    click.secho(f"→ Saved JSON to {output_fpath}", fg="green")


def enrich_journal_metadata(
    journals_dict: dict[str] = None
) -> dict[list[dict]]:
    """
    Enrich the metadata of the plain data journals metadata dict.
    """
    journal_metadata = {
        "id": None,
        "issn": None,
        "publisher": None,
        "data_journal_type": None,
        "is_active": None,
        "research_field": None,
    }

    if not journals_dict:
        click.secho("→ No journals_dict provided ...",
                    fg="red")
        return

    enriched_journals_dict: dict[list[dict]] = {"data_journals": []}
    for idx, (_, journal_data) in enumerate(journals_dict.items()):
        current_journal = {}
        for key in journal_metadata.keys():
            if key == "id":
                current_journal[key] = idx + 1
            elif key in journal_data.keys():
                current_journal[key] = journal_data[key]
            else:
                current_journal[key] = None
        enriched_journals_dict["data_journals"].append(current_journal)

    return enriched_journals_dict


def process_journal_metadata(
    crawl_csv: bool = False,
    csv_fpath: Path | None = None,
    output_dir: Path | None = Path("./data/json")
) -> bool:
    """
    Core processing workflow for journal metadata.
    """
    # Create output_dir if it does not exist
    ensure_dir(output_dir)

    data = None
    if crawl_csv:
        data = get_journal_data_from_github()

    if csv_fpath:
        data = get_journal_data_from_csv(csv_fpath)

    if data is None:
        click.secho(
            "→ No data source provided or data fetch failed.",
            fg="red"
        )
        return False

    # Parse and process journal data
    journals_dict = parse_journal_data_csv(data)
    json_data = transform_csv_to_json(journals_dict)
    write_json_to_disk(json_data, output_dir / "data_journals.json")

    enriched_journals_dict = enrich_journal_metadata(journals_dict)
    write_json_to_disk(
        enriched_journals_dict,
        output_dir / "data_journals_enriched.json"
    )

    return True


@click.command(no_args_is_help=False)
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
    help="Load and parse CSV with data journal metadata.",
)
@click.option(
    "--output_dir", "-o",
    type=click.Path(path_type=Path),
    default="./data/json",
    show_default=True,
    help="Save the parsed data journal metadata as JSON to this location.",
)
def main(
    crawl_csv: bool = False,
    csv_fpath: Path | None = None,
    output_dir: Path | None = None,
):
    """
    CLI wrapper for journal data processing.
    """
    process_journal_metadata(
        crawl_csv=crawl_csv,
        csv_fpath=csv_fpath,
        output_dir=output_dir
    )


if __name__ == "__main__":
    main()
