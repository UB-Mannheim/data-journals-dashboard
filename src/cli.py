import click
from pathlib import Path

from data_processing import (
    get_journal_data_from_github,
    get_journal_data_from_csv,
    save_csv_to_disk,
    process_all_journals,
    process_single_journal,
    METADATA_SCHEMA_PATH,
    RAW_JOURNAL_METADATA_PATH,
    PROCESSED_JOURNAL_METADATA_PATH,
)


class OrderedGroup(click.Group):
    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(["collect", "process", "hugo"])


@click.group(cls=OrderedGroup, no_args_is_help=True)
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
        save_csv_to_disk(rows, RAW_JOURNAL_METADATA_PATH)


@cli.group("process", no_args_is_help=True)
def process():
    """
    Process raw journal metadata by validating it against the
    journal_metadata_schema and enriching it with DOAJ.org metadata.
    """
    pass


@process.command("all", no_args_is_help=False)
@click.option(
    "--input_fpath", "-f",
    type=click.Path(path_type=Path),
    default=RAW_JOURNAL_METADATA_PATH,
    show_default=True,
    help="Path to the journal metadata CSV file.",
)
@click.option(
    "--schema_path", "-s",
    type=click.Path(path_type=Path),
    default=METADATA_SCHEMA_PATH,
    show_default=True,
    help="Path to the journal metadata schema YAML file.",
)
def process_all(
    input_fpath: Path,
    schema_path: Path,
):
    """
    Process all journals in one go.
    """
    if not input_fpath.exists():
        click.secho("No input provided. Aborting.", fg="red")
        return

    process_all_journals(input_fpath=input_fpath, schema_path=schema_path)


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
    if not input_fpath.exists():
        click.secho("No input provided. Aborting.", fg="red")

    process_single_journal(input_fpath=input_fpath, schema_path=schema_path)


@cli.group("hugo", no_args_is_help=True)
def hugo():
    """
    Generate Hugo static site content from processed journal data.
    """
    pass


@hugo.command("generate", no_args_is_help=False)
@click.option(
    "--input_fpath", "-f",
    type=click.Path(path_type=Path),
    default=PROCESSED_JOURNAL_METADATA_PATH,
    show_default=True,
    help="Path to the processed journal YAML file.",
)
@click.option(
    "--output_dir", "-o",
    type=click.Path(path_type=Path),
    default=Path("."),
    show_default=True,
    help="Hugo site root directory.",
)
@click.option(
    "--schema_path", "-s",
    type=click.Path(path_type=Path),
    default=METADATA_SCHEMA_PATH,
    show_default=True,
    help="Path to the journal metadata schema YAML file.",
)
def hugo_generate(input_fpath: Path, output_dir: Path, schema_path: Path):
    """
    Generate Hugo-compatible markdown files from processed journal data.
    """
    from hugo_transform import create_journal_content_for_hugo, generate_field_descriptions_data

    if not input_fpath.exists():
        click.secho(f"Input file not found: {input_fpath}", fg="red")
        return

    count = create_journal_content_for_hugo(input_fpath, output_dir / "content/journals")
    generate_field_descriptions_data(schema_path, output_dir)
    click.secho(f"Generated {count} journal pages for Hugo.", fg="green")


@hugo.command("init", no_args_is_help=False)
@click.option(
    "--output_dir", "-o",
    type=click.Path(path_type=Path),
    default=Path("."),
    show_default=True,
    help="Output directory for Hugo site structure.",
)
def hugo_init(output_dir: Path):
    """
    Initialize Hugo site configuration and templates.
    """
    from hugo_transform import generate_hugo_site_config, generate_hugo_archetype

    generate_hugo_site_config(output_dir)
    generate_hugo_archetype(output_dir)
    click.secho("Hugo site structure initialized.", fg="green")


if __name__ == "__main__":
    cli()
