import yaml
import re
from pathlib import Path
from datetime import datetime

from config import HUGO_CONFIG_PATH


def sanitize_filename(title: str) -> str:
    """
    Convert title to safe filename by removing/escaping special chars.
    """
    # Remove or replace problematic characters
    safe = re.sub(r"[^\w\s-]", "", title.lower())
    safe = re.sub(r"[\s_]+", "-", safe)
    return safe[:50]  # Limit length


def _update_version_in_config(config_fpath: Path | str = HUGO_CONFIG_PATH):
    """
    Inject current timestamp to hugo.toml.
    """
    data = config_fpath.read_text()
    timestamp = f"v{datetime.now().strftime("%Y-%m-%d")}"
    data = re.sub(r"v\d{4}-\d{2}-\d{2}", timestamp, data)

    with open(config_fpath, "w", encoding="utf-8") as file:
        file.write(data)


def create_journal_content_for_hugo(
    data_journals_fpath: Path,
    content_dir: Path
) -> int:
    """
    Generate Hugo-compatible markdown files from data_journals.yaml.

    Each journal becomes a markdown file with front matter containing
    all metadata fields suitable for Hugo templating and filtering.
    """
    with open(data_journals_fpath) as file:
        data = yaml.safe_load(file)

    if not data or "journals" not in data:
        print("No journals found in data file.")
        return 0

    content_dir.mkdir(parents=True, exist_ok=True)
    generated_count = 0

    for journal in data["journals"]:
        issn = journal.get("issn", "")
        if not issn:
            print("Skipping journal without ISSN...")
            continue

        issn_slug = issn.replace("-", "")
        title = journal.get("journal_title", "Untitled")
        title_slug = sanitize_filename(title)
        filepath = content_dir / f"{issn_slug}-{title_slug}.md"
        is_active = journal.get("is_active", "active")

        # Build front matter with essential Hugo fields
        front_matter = {
            "title": title,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "draft": False,
            "issn": issn,
            "is_active": "active" if is_active else "inactive"
        }

        # Add data_journal_type as taxonomy if present
        if journal.get("data_journal_type"):
            front_matter["data_journal_type"] = [journal["data_journal_type"]]

        # Add publisher as taxonomy
        if journal.get("publisher"):
            front_matter["publisher"] = [journal["publisher"]]

        # Add keywords as taxonomy (list)
        if journal.get("keywords"):
            front_matter["keywords"] = journal["keywords"]

        # Add research_fields as taxonomy (list)
        if journal.get("research_fields"):
            front_matter["research_fields"] = journal["research_fields"]

        # Add license_types as taxonomy (list)
        if journal.get("license_types"):
            front_matter["license_types"] = [t for t in journal["license_types"]]

        # Flatten APC info for easier template access
        if journal.get("apc_has") is not None:
            front_matter["apc_has"] = "yes" if journal["apc_has"] else "no"
        if journal.get("apc_max"):
            # Convert list of {price, currency} to simple display string
            apc_prices = []
            for apc in journal["apc_max"]:
                if isinstance(apc, dict) and apc.get("price"):
                    apc_prices.append(f"{apc["price"]} {apc.get("currency", "")}")
            if apc_prices:
                front_matter["apc_price_range"] = ", ".join(apc_prices)

        # Add preservation services if present
        if journal.get("preservation_services"):
            front_matter["preservation_services"] = journal["preservation_services"]

        # Add BOAI compliance
        if journal.get("boai") is not None:
            front_matter["boai"] = "yes" if journal["boai"] else "no"

        # Add all other fields as flat key-value pairs
        for key, value in journal.items():
            if key not in front_matter and value is not None:
                # Rename "url" to avoid collision with Hugo"s reserved page URL key
                out_key = "journal_url" if key == "url" else key
                front_matter[out_key] = value

        # Generate content body
        content_lines = [f"# {title}", ""]
        if journal.get("url"):
            content_lines.append(f"**Journal URL**: [{journal["url"]}]({journal["url"]})")
        if journal.get("publisher"):
            content_lines.append(f"**Publisher**: {journal["publisher"]}")
        if journal.get("data_journal_type"):
            content_lines.append(f"**Type**: {journal["data_journal_type"]}")
        content_lines.append("")

        # Write the markdown file
        front_matter_yaml = yaml.dump(
            front_matter,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False
        )
        content = f"---\n{front_matter_yaml}---\n\n" + "\n".join(content_lines) + "\n"
        filepath.write_text(content)
        generated_count += 1
        print(f"Generated: {filepath.name}")

    # Update version
    _update_version_in_config()
    return generated_count


def generate_hugo_site_config(output_dir: Path, base_url: str, version: str) -> None:
    """
    Generate Hugo config.toml with taxonomies for filtering.
    """
    config_content = f"""baseURL = "{base_url}"
locale = "en-us"
title = "Data Journals Dashboard"
theme = "djd"
DataDir = "hugo-data"

[params]
  description = "Search and filter data journals by type, publisher, APC, and more"
  author = {{ name = "Thomas Schmidt", email = "thomas.schmidt@uni-mannheim.de" }}
  version = "{version}"

[taxonomies]
  data_journal_type = "data_journal_type"
  publisher = "publisher"
  keywords = "keywords"
  research_fields = "research_fields"
  license_types = "license_types"

[outputs]
  home = ["HTML", "RSS"]
  section = ["HTML", "RSS"]

[markup]
  [markup.highlight]
    style = "github"
"""

    config_dir = output_dir
    config_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "hugo.toml").write_text(config_content)
    print(f"Generated Hugo config at {config_dir / "hugo.toml"}")


def generate_field_descriptions_data(schema_fpath: Path, output_dir: Path) -> None:
    """
    Generate data/field_descriptions.yaml from the metadata schema.
    Maps each field key to its description for use in Hugo templates.
    """
    with open(schema_fpath) as f:
        schema = yaml.safe_load(f)

    selected_keys = [
        "data_journal_type", "oa_start", "boai", "publication_time_weeks",
        "subject_codes", "review_process", "apc_has", "waiver_has",
        "preservation_has", "plagiarism_detection", "copyright_author_retains",
        "deposit_policy_has", "is_active", "enrichment_source"
    ]
    descriptions = {
        field["key"]: field["description"]
        for field in schema.get("fields", [])
        if field["key"] in selected_keys
        and "key" in field and "description" in field
    }

    data_dir = output_dir / "hugo-data"
    data_dir.mkdir(parents=True, exist_ok=True)

    with open(data_dir / "field_descriptions.yaml", "w") as f:
        yaml.dump(descriptions, f, allow_unicode=True, sort_keys=True)


def generate_hugo_archetype(output_dir: Path) -> None:
    """
    Generate default archetype template for journal pages.
    """
    archetype_content = """---
title: "{{ replace .Name \"-\" \" \" | title }}"
date: {{ .Date }}
draft: true
---

{{/*
This is the default archetype for data journal entries.
Hugo will use front matter from the YAML source.
*/}}
"""

    archetype_dir = output_dir / "themes" / "djd" / "archetypes"
    archetype_dir.mkdir(parents=True, exist_ok=True)

    (archetype_dir / "default.md").write_text(archetype_content)
    print(f"Generated Hugo archetype at {archetype_dir / "default.md"}")
