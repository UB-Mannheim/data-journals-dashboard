# README

## Package Structure

```bash
src/
├── cli.py               # Entry point: defines all CLI commands and subcommands
├── config.py            # Central path and URL constants shared across modules
├── data_processing.py   # Fetches raw journal metadata from GitHub and enriches it with DOAJ API data
├── hugo_transform.py    # Converts processed journal YAML into Hugo-compatible markdown and config files
├── utils.py             # I/O helpers for reading and writing CSV, YAML, and JSON; schema loading utilities
├── validate.py          # Validates a journal collection against the metadata schema for type and compliance errors
└── __init__.py
```

## Scripts

| File | Description |
| --- | --- |
| [cli.py](cli.py) | Defines the `dj` CLI with five command groups (`collect`, `process`, `hugo`, `export`, `validate`) using Click. |
| [config.py](config.py) | Stores shared file paths and the upstream GitHub CSV URL as module-level constants. |
| [data_processing.py](data_processing.py) | Orchestrates the core data pipeline: fetching the raw journal CSV from GitHub, deduplicating against the existing collection, and enriching each journal record with metadata from the DOAJ API. |
| [hugo_transform.py](hugo_transform.py) | Transforms the processed data journal metadata (YAML) into per-journal Hugo markdown files with front matter, and generates the site config (`hugo.toml`), field descriptions, and archetype template. |
| [utils.py](utils.py) | Provides reusable helpers for loading the metadata schema, parsing CSV rows against schema field definitions, and converting the journal collection between CSV, YAML, and JSON formats. |
| [validate.py](validate.py) | Checks a journal YAML collection for missing required fields, invalid field names, wrong value types, and duplicate IDs/ISSNs, then writes a timestamped validation log. |

## CLI Usage

```bash
dj [COMMAND]

Commands:
  collect   Fetch raw journal metadata CSV from GitHub
  process   Validate and enrich raw metadata (all journals or a single one)
  hugo      Generate Hugo markdown content or initialise the Hugo site structure
  export    Export the journal collection to CSV, YAML, or JSON
  validate  Check a journal YAML file against the metadata schema
```

Run `dj [COMMAND] --help` for options on any subcommand.
