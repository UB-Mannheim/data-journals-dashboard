import click
import json
import tempfile
import yaml
from datetime import datetime
from pathlib import Path

from data_processing import (
    get_journal_data_from_github,
    write_csv_to_disk,
    process_all_journals,
    process_single_journal,
    METADATA_SCHEMA_PATH,
    RAW_JOURNAL_METADATA_PATH,
    JOURNAL_COLLECTION_PATH,
)
from utils import ensure_dir, to_csv, to_yaml, to_json, get_journal_by_issn
from validate import run_validation


class OrderedGroup(click.Group):
    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(["collect", "process", "hugo", "export", "validate"])


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
@click.option(
    "--output_fpath", "-o",
    type=click.Path(path_type=Path),
    default=JOURNAL_COLLECTION_PATH,
    show_default=True,
    help="Path to save the processed journal collection YAML file.",
)
def process_all(
    input_fpath: Path,
    schema_path: Path,
    output_fpath: Path,
):
    """
    Process all journals in one go.
    """
    if not input_fpath.exists():
        click.secho("No input provided. Aborting.", fg="red")
        return

    ensure_dir(output_fpath.parent)
    process_all_journals(input_fpath, schema_path, output_fpath)


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
@click.option(
    "--output_fpath", "-o",
    type=click.Path(path_type=Path),
    default=JOURNAL_COLLECTION_PATH,
    show_default=True,
    help="Path to save the processed journal collection YAML file.",
)
def process_single(
    input_fpath: Path | None,
    schema_path: Path,
    output_fpath: Path,
):
    """
    Process a single journal.
    """
    if not input_fpath or not input_fpath.exists():
        click.secho("No input provided. Aborting.", fg="red")
        raise click.Abort()

    ensure_dir(output_fpath.parent)
    success = process_single_journal(input_fpath, schema_path, output_fpath)
    if not success:
        raise click.Abort()


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
    default=JOURNAL_COLLECTION_PATH,
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
    help="Path to journal metadata YAML or JSON file.",
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
@click.option(
    "--issn",
    default=None,
    help="ISSN of a single journal to export from the collection.",
)
def export_csv(input_fpath: Path, output_dir: Path, scope: str, issn: str | None):
    """
    Export YAML or JSON metadata to a core-schema CSV.
    """
    if issn:
        journal = get_journal_by_issn(JOURNAL_COLLECTION_PATH, issn)
        if journal is None:
            click.secho(f"ISSN '{issn}' not found in collection.", fg="red")
            return
        ensure_dir(output_dir)
        with tempfile.NamedTemporaryFile(
            suffix=".yaml", delete=False, mode="w", encoding="utf-8"
        ) as tmp:
            yaml.dump({"journals": [journal]}, tmp, allow_unicode=True)
            tmp_path = Path(tmp.name)
        try:
            output_fpath = Path(output_dir) / f"{issn}.csv"
            to_csv(tmp_path, output_fpath, scope)
        finally:
            tmp_path.unlink(missing_ok=True)
        return

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
    help="Path to schema CSV or JSON file.",
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
@click.option(
    "--issn",
    default=None,
    help="ISSN of a single journal to export from the collection.",
)
def export_yaml(input_fpath: Path, output_dir: Path, scope: str, issn: str | None):
    """
    Convert a core-schema CSV or JSON back to a YAML journal collection.
    """
    if issn:
        journal = get_journal_by_issn(JOURNAL_COLLECTION_PATH, issn)
        if journal is None:
            click.secho(f"ISSN '{issn}' not found in collection.", fg="red")
            return
        ensure_dir(output_dir)
        journal_without_issn = {k: v for k, v in journal.items() if k != "issn"}
        payload = json.dumps({"journals": {issn: journal_without_issn}})
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        ) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        try:
            output_fpath = Path(output_dir) / f"{issn}.yaml"
            to_yaml(tmp_path, output_fpath, scope)
        finally:
            tmp_path.unlink(missing_ok=True)
        return

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
@click.option(
    "--issn",
    default=None,
    help="ISSN of a single journal to export from the collection.",
)
def export_json(input_fpath: Path, output_dir: Path, scope: str, issn: str | None):
    """
    Export journal metadata from CSV or YAML to a JSON file.
    """
    if issn:
        journal = get_journal_by_issn(JOURNAL_COLLECTION_PATH, issn)
        if journal is None:
            click.secho(f"ISSN '{issn}' not found in collection.", fg="red")
            return
        ensure_dir(output_dir)
        with tempfile.NamedTemporaryFile(
            suffix=".yaml", delete=False, mode="w", encoding="utf-8"
        ) as tmp:
            yaml.dump({"journals": [journal]}, tmp, allow_unicode=True)
            tmp_path = Path(tmp.name)
        try:
            output_fpath = Path(output_dir) / f"{issn}.json"
            to_json(tmp_path, output_fpath, scope)
        finally:
            tmp_path.unlink(missing_ok=True)
        return

    if not Path(input_fpath).exists():
        click.secho(f"Input filepath does not exist: {input_fpath}", fg="red")
        return

    ensure_dir(output_dir)
    output_fpath = Path(output_dir) / Path(input_fpath.name).with_suffix(".json")
    to_json(input_fpath, output_fpath, scope)


@cli.command("validate", no_args_is_help=True)
@click.option(
    "--input_fpath", "-i",
    type=click.Path(path_type=Path, exists=True),
    required=True,
    help="Path to input journal metadata YAML file (must be .yaml)."
)
@click.option(
    "--output_fpath", "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to write validation log (defaults to stdout)."
)
@click.option(
    "--issn",
    default=None,
    help="ISSN of a single journal to validate from the collection.",
)
def validate(
    input_fpath: Path,
    output_fpath: Path | None,
    issn: str | None,
):
    """
    Validate journals against metadata schema.
    """
    if input_fpath.suffix != ".yaml":
        raise click.UsageError(
            f"Input file must be a .yaml file, got {input_fpath.suffix}"
        )
    try:
        run_validation(input_fpath, output_fpath, issn)
    except ValueError as e:
        click.secho(str(e), fg="red")
        return
    click.secho("Validation complete.", fg="green")


if __name__ == "__main__":
    cli()
