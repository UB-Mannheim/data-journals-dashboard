import click
from pathlib import Path

from data_processing import process_journal_metadata


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
    default="journal_metadata_schema/schema.yaml",
    show_default=True,
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
