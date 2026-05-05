import csv
import click
import json
from pathlib import Path


def add_journal_metadata(journals_dict: dict[str] = None) -> dict[list[dict]]:
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


@click.command(no_args_is_help=False)
@click.option(
    "--csv_fpath", "-csv",
    type=click.Path(path_type=Path),
    default="./data/01_data_journals.csv",
    show_default=True,
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
    csv_fpath: str | Path = None,
    output_dir: str | Path = None,
):
    """
    Main data processing function
    """
    if csv_fpath:
        csv_fpath = Path(csv_fpath)
        if not csv_fpath.exists():
            click.secho(f"→ Input filepath {csv_fpath} does not exist",
                        fg="red")
            return

    if output_dir:
        output_dir = Path(output_dir)
        if not output_dir.exists():
            output_dir.mkdir(exist_ok=True, parents=True)

    # Parse csv
    with open(csv_fpath, "r", encoding="utf-8") as file:
        data = csv.reader(file)

        # Transform to json
        journals_dict: dict[str] = {}
        for idx, row in enumerate(data):
            if idx == 0:  # Skip column headers
                continue
            if row:
                journals_dict[idx] = {
                    "issn": row[0],
                    "journal_title": row[1],
                    "publisher": row[2],
                    "data_journal_type": row[3]
                }

    # Save json
    output_fpath = Path(output_dir).joinpath("data_journals.json")
    with open(output_fpath, "w", encoding="utf-8") as file:
        json.dump(journals_dict, file, indent=4)

    # Enrich journals_dict metadata
    enriched_journals_dict = add_journal_metadata(journals_dict)

    # Save json
    output_fpath = Path(output_dir).joinpath("data_journals_enriched.json")
    with open(output_fpath, "w", encoding="utf-8") as file:
        json.dump(enriched_journals_dict, file, indent=4)


if __name__ == "__main__":
    main()
