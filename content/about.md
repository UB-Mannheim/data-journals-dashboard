---
title: About the Data Journals Dashboard
date: '2026-06-02'
type: page
logo:
  src: "logos/FDZ_Logo_DE_rgb_blau.png"
  link: "https://fdz.bib.uni-mannheim.de/"
  alt: "FDZ-Logo"
---

## Contents

- [Introduction](#introduction)
  - [What are Data Journals?](#what-are-data-journals)
- [Journal Metadata](#journal-metadata)
  - [Primary Dataset](#primary-dataset)
  - [Augmented Dataset](#augmented-dataset)
  - [Dataset Dump](#dataset-dump)
  - [Licenses](#licenses)
- [Contributions](#contributions)
- [Use of AI](#use-of-ai)
- [Citing the Dashboard](#citing-the-dashboard)

## Introduction

The Data Journals Dashboard provides access to a collection of data journals first published by **Maxi Kindling & Dorothea Strecker** in 2022 [[Zenodo](https://doi.org/10.5281/zenodo.7082126)]. With additional metadata from the [Directory of Open Access Journals](https://doaj.org/) the dashboard enables researchers, research data management (RDM) professionals, librarians and all other interested parties to search and filter the collection and select a data journal that meets their publication needs.

The Data Journals Dashboard is maintained by the [Research Data Center](https://fdz.bib.uni-mannheim.de/) of the [University Library Mannheim](https://www.bib.uni-mannheim.de/en/).

### What are Data Journals?

Data journals are scientific journals that primarily or to a large extend publish data papers, data reports, and similar article types. These articles describe datasets produced through research activities, but do not interpret the results. Instead, data journals focus on providing detailed documentation of how, when and with which methodology datasets were created, where they are accessible, and how they can be reused by others. As most data journals are peer-reviewed, data papers promote good research and RDM practices; they also benefit researchers who create and share high-quality datasets, as they follow established scientific communication practices and receive citations.

## Journal Metadata

### Primary Dataset

The dashboard's primary data source are data journal metadata published under `CC0 1.0 Universal` on [Zenodo](https://doi.org/10.5281/zenodo.7082126) and [Github](https://github.com/MaxiKi/data-journals):

- **Zenodo**: Kindling, M., & Strecker, D. (2022). List of data journals (1.0) [Data set]. Zenodo. [https://doi.org/10.5281/zenodo.7082126](https://doi.org/10.5281/zenodo.7082126)
- **GitHub**: [https://github.com/MaxiKi/data-journals](https://github.com/MaxiKi/data-journals)

### Augmented Dataset

The primary dataset is enhanced by adding additional metadata via the Directory of Open Access Journals API. Each `ISSN` in the primary dataset is queried via the API. If the `ISSN` is present in the DOAJ, additional metadata is retrieved and added to the journal's existing metadata. The full metadata schema used to integrate both data sources is available on [GitHub](https://github.com/UB-Mannheim/data-journals-dashboard/blob/main/metadata_schema/schema.yaml).

For `ISSNs` not present in the DOAJ manual metadata augmentations are made using the journal's website, [ISSN Portal](https://portal.issn.org/), Wikidata and other sources. Each data journal page provides a list of the specific sources used for metadata augmentation.

### Dataset Dump

The augmented dataset containing all metadata can be dowloaded as `CSV`, `YAML` and `JSON` on [Github](https://github.com/UB-Mannheim/data-journals-dashboard/tree/main/data/dumps).

### Licenses

- The primary dataset by Kindling & Strecker (2022) is licensed under `CC0 1.0 Universal` [[Source](https://github.com/MaxiKi/data-journals)]
- Metadata retrieved via the Directory of Open Access Journals API is licensed under `CC0 1.0 Universal` [[Source](https://doaj.org/terms/#metadata)]
- The augmented dataset ([DJD metadata collection](https://github.com/UB-Mannheim/data-journals-dashboard/blob/main/data/data_journals.yaml)) is licensed under `CC0 1.0 Universal` [[CC0 1.0 deed](https://creativecommons.org/publicdomain/zero/1.0/deed.de)]
- The [DJD metadata schema](https://github.com/UB-Mannheim/data-journals-dashboard/blob/main/metadata_schema/schema.yaml) of the Data Journals Dashboard is licensed under `CC0 1.0 Universal` [[CC0 1.0 deed](https://creativecommons.org/publicdomain/zero/1.0/deed.de)]

## Contributions

Contribute to the Data Journals Dashboard by suggesting a new data journal via a [GitHub issue](https://github.com/UB-Mannheim/data-journals-dashboard/issues/new/choose) using the **"Add Data Journal"** template. The template will ask for the journal's `ISSN`, `title`, `publisher`, `URL`, `data_journal_type`, and `status`. After submitting the issue, a maintainer will review your contribution. Once approved, the new journal will be processed and added to the collection.

## Use of AI

Claude Code (`Sonnet 4.6`) was used for coding, bug fixing and testing the Python data processing pipeline as well as the [Hugo](https://gohugo.io/) app.

Additional journal metadata not provided by the Directory of Open Access Journals' API was for a large part collected with Claude Code and its web search tool, and then manually verified and cleaned.

## Citing the Dashboard

If you use the Data Journals Dashboard in your research or work, please cite it as follows:

- Schmidt, T. (2026). *Data Journals Dashboard* [Software]. Universitätsbibliothek Mannheim. https://github.com/UB-Mannheim/data-journals-dashboard
