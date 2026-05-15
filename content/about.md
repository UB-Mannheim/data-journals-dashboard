---
title: About
date: '2026-05-11'
type: page
---

Last update: 2026-05-11

---

## Introduction

The Data Journals Dashboard provides easy access to a collection of data journals first compiled by **Kindling, M. and Strecker, D.** and published in 2022 [[Zenodo](https://doi.org/10.5281/zenodo.7082126)]. With additional metadata from the [Directory of Open Access Journals](https://doaj.org/) the dashboard enables researchers, research data management professionals, librarians and all other interested parties to search and filter the collection and select a data journal that meets their publication needs.

To find out more about the concept of data journals refer to this page by the [University Libraries of Western Michigan University](https://libguides.wmich.edu/datasci/datajournals).

## Primary Dataset

The primary data source for the dashboard is a collection of data journal metadata published under `CC0 1.0 Universal` on [Zenodo](https://doi.org/10.5281/zenodo.7082126) and [Github](https://github.com/MaxiKi/data-journals):

```bash
Zenodo:
    - Kindling, M., & Strecker, D. (2022). List of data journals (1.0) [Data set]. Zenodo.
      https://doi.org/10.5281/zenodo.7082126

GitHub:
    - https://github.com/MaxiKi/data-journals
```

## Augmented Dataset

The primary dataset is enhanced by adding additional metadata via the [Directory of Open Access Journals (doaj.org)](https://doaj.org/) API. Each `ISSN` in the primary dataset is queried via the API. If the `ISSN` is present in the DOAJ, additional metadata is retrieved and added to the journal's existing metadata. The full metadata schema used to integrate both data sources is available on [GitHub](https://github.com/tsmdt/data-journals-dashboard/blob/main/journal_metadata_schema/schema.yaml).

**The augmented dataset is available as XXX here:
All metadata is licensed under CC 0**

### Limitations

The metadata for a majority of data journals is augmented via the DOAJ API. In cases where an `ISSN` is not present in the directory the corresponding data journal in the dashboard will only provide limited metdata, consisting of these core elements:

```bash
- ISSN
- Journal Title
- Publisher
- URL
- Data Journal Type
```

## Contributions

pass

## Acknowledgment

pass

## citation.cff

```yaml
cff-version: 1.2.0
type: software
title: "Data Journals Dashboard"
version: v2026-05-12
date-released: "2026-05-12"
url: "https://tsmdt.github.io/data-journals-dashboard/"
repository-code: "https://github.com/tsmdt/data-journals-dashboard"
authors:
  - family-names: Schmidt
    given-names: Thomas
    orcid: "https://orcid.org/0000-0003-3620-3355"
license: CC0-1.0
```

{{< figure src="/logos/FDZ_Logo_DE_rgb_blau.png" link="https://fdz.bib.uni-mannheim.de/" target="_blank" alt="FDZ-Logo" width="20%" >}}
