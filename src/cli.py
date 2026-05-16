import click
from datetime import datetime
from pathlib import Path

from data_processing import (
    get_journal_data_from_github,
    write_csv_to_disk,
    process_all_journals,
    process_single_journal,
    METADATA_SCHEMA_PATH,
    RAW_JOURNAL_METADATA_PATH,
    PROCESSED_JOURNAL_METADATA_PATH,
)
from utils import ensure_dir, to_csv, to_yaml, to_json


class OrderedGroup(click.Group):
    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(["collect", "process", "hugo", "export"])


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
    help="Fetch data journal metadata CSV from https://github.com/MaxiKi/data-journals.",
)
def collect(github: bool):
    """
    Fetch or parse raw journal metadata from GitHub or a local
    CSV containing data journal metadata.
    """
    if github:
        rows = get_journal_data_from_github()
    else:
        raise click.UsageError("Provide --github")
    if rows:
        write_csv_to_disk(rows, RAW_JOURNAL_METADATA_PATH)


@cli.group("process", no_args_is_help=True)
def process():
    """
    Process raw journal metadata by validating it against the
    journal_metadata_schema and enriching it with DOAJ.org metadata.
    """
    pass


@process.command("all", no_args_is_help=False)
@click.option(
    "--input_fpath", "-i",
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
    "--input_fpath", "-i",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to a single-journal file (.csv, .yaml, .json).",
)
@click.option(
    "--schema_path", "-s",
    type=click.Path(path_type=Path),
    default=METADATA_SCHEMA_PATH,
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
    "--input_fpath", "-i",
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
    from hugo_transform import (
        create_journal_content_for_hugo,
        generate_field_descriptions_data
    )

    if not input_fpath.exists():
        click.secho(f"Input file not found: {input_fpath}", fg="red")
        return

    count = create_journal_content_for_hugo(
        input_fpath, output_dir / "content/journals"
    )
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
    from hugo_transform import (
        generate_hugo_site_config,
        generate_hugo_archetype
    )

    timestamp = f"v{datetime.now().strftime("%Y-%m-%d")}"
    generate_hugo_site_config(output_dir, version=timestamp)
    generate_hugo_archetype(output_dir)
    click.secho("Hugo site structure initialized.", fg="green")


@cli.group("export", no_args_is_help=True)
def export():
    """
    Export data journal metadata to different file types.
    """
    pass


@export.command("csv", no_args_is_help=True)
@click.option(
    "--input_fpath", "-i",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to journal metadata YAML file.",
)
@click.option(
    "--output_dir", "-o",
    type=click.Path(path_type=Path),
    default=Path("./exports"),
    show_default=True,
    help="Folder where exported files are saved.",
)
@click.option(
    "--scope", "-s",
    type=click.Choice(["base", "core", "full"]),
    default="base",
    show_default=True,
    help=(
        "base: core metadata without 'is_active' field; "
        "core: core metadata; full: complete metadata"
    ),
)
def export_csv(input_fpath: Path, output_dir: Path, scope: str):
    """
    Export YAML metadata to a core-schema CSV.
    """
    if not Path(input_fpath).exists():
        click.secho(f"Input filepath does not exist: {input_fpath}", fg="red")
        return

    ensure_dir(output_dir)
    output_fpath = Path(output_dir) / Path(input_fpath.name).with_suffix(".csv")
    to_csv(input_fpath, output_fpath, scope)


@export.command("yaml", no_args_is_help=True)
@click.option(
    "--input_fpath", "-i",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to core-schema CSV file.",
)
@click.option(
    "--output_dir", "-o",
    type=click.Path(path_type=Path),
    default=Path("./exports"),
    show_default=True,
    help="Folder where the exported YAML file is saved.",
)
@click.option(
    "--scope", "-s",
    type=click.Choice(["base", "core", "full"]),
    default="core",
    show_default=True,
    help=(
        "base: raw CSV fields only; "
        "core: core metadata (includes generated id); "
        "full: complete metadata"
    ),
)
def export_yaml(input_fpath: Path, output_dir: Path, scope: str):
    """
    Convert a core-schema CSV back to a YAML journal collection.
    """
    if not Path(input_fpath).exists():
        click.secho(f"Input filepath does not exist: {input_fpath}", fg="red")
        return

    ensure_dir(output_dir)
    output_fpath = Path(output_dir) / Path(input_fpath.name).with_suffix(".yaml")
    to_yaml(input_fpath, output_fpath, scope)


@export.command("json", no_args_is_help=True)
@click.option(
    "--input_fpath", "-i",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to journal metadata CSV or YAML file.",
)
@click.option(
    "--output_dir", "-o",
    type=click.Path(path_type=Path),
    default=Path("./exports"),
    show_default=True,
    help="Folder where the exported JSON file is saved.",
)
@click.option(
    "--scope", "-s",
    type=click.Choice(["base", "core", "full"]),
    default="core",
    show_default=True,
    help=(
        "base: raw CSV/YAML fields only; "
        "core: core metadata; full: complete metadata"
    ),
)
def export_json(input_fpath: Path, output_dir: Path, scope: str):
    """
    Export journal metadata from CSV or YAML to a JSON file.
    """
    if not Path(input_fpath).exists():
        click.secho(f"Input filepath does not exist: {input_fpath}", fg="red")
        return

    ensure_dir(output_dir)
    output_fpath = Path(output_dir) / Path(input_fpath.name).with_suffix(".json")
    to_json(input_fpath, output_fpath, scope)


if __name__ == "__main__":
    cli()
