import click
from pathlib import Path

from data_processing import (
    get_journal_data_from_github,
    get_journal_data_from_csv,
    save_csv_to_disk,
    process_all_journals,
    process_single_journal,
    RAW_CSV_PATH,
)


@click.group(no_args_is_help=True)
def cli():
    """
    Data Journal Dashboard CLI Helper.
    """
    pass


@cli.command("collect", no_args_is_help=True)
@click.option(
    "--github", "-g",
    is_flag=True,
    default=False,
    help="Fetch data journal metadata CSV from GitHub.",
)
@click.option(
    "--csv_fpath", "-f",
    type=click.Path(path_type=Path),
    default=None,
    help="Load a local CSV with data journal metadata.",
)
def collect(github: bool, csv_fpath: Path | None):
    """
    Fetch or parse raw journal metadata from GitHub or a local
    CSV containing data journal metadata.
    """
    if github:
        rows = get_journal_data_from_github()
    elif csv_fpath:
        rows = get_journal_data_from_csv(csv_fpath)
    else:
        raise click.UsageError("Provide --github or --csv_fpath.")
    if rows:
        save_csv_to_disk(rows, RAW_CSV_PATH)


@cli.group("process", no_args_is_help=True)
def process():
    """
    Process raw journal metadata by validating it against the
    journal_metadata_schema and enriching it with DOAJ.org metadata.
    """
    pass


@process.command("all", no_args_is_help=False)
@click.option(
    "--schema_path", "-s",
    type=click.Path(path_type=Path),
    default="journal_metadata_schema/schema.yaml",
    show_default=True,
    help="Path to the journal metadata schema YAML file.",
)
@click.option(
    "--max_num", "-m",
    type=int,
    default=None,
    help="Maximum number of journals to process.",
)
def process_all(schema_path: Path, max_num: int | None):
    """
    Process all journals in one go.
    """
    process_all_journals(schema_path=schema_path, max_num=max_num,)


@process.command("single", no_args_is_help=True)
@click.option(
    "--input_fpath", "-f",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to a single-journal file (.csv, .yaml, .json).",
)
@click.option(
    "--schema_path", "-s",
    type=click.Path(path_type=Path),
    default="journal_metadata_schema/schema.yaml",
    show_default=True,
    help="Path to the journal metadata schema YAML file.",
)
def process_single(
    input_fpath: Path | None,
    schema_path: Path,
):
    """
    Process a single journal.
    """
    process_single_journal(
        input_fpath=input_fpath,
        schema_path=schema_path,
    )


if __name__ == "__main__":
    cli()
