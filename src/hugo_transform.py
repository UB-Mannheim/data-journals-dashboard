import yaml
from pathlib import Path


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
