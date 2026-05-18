# README

Last update: 2026-05-18

## data_journals_augmented.csv

`data_journals_augmented.csv` is an augmented version of [https://github.com/MaxiKi/data-journals](https://github.com/MaxiKi/data-journals) with an added column "is_active". The column provides a manually made check if a data journal is currently active and publishing new papers or has ceased/paused.

The augmented dataset is released as under [CC0 1.0 International](https://creativecommons.org/publicdomain/zero/1.0/deed.de).

For more information about the original dataset refer to this publication:

> Kindling, M., & Strecker, D. (2022). List of data journals (1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.7082126

## data_journals.yaml

The augmented dataset is enhanced by adding additional metadata via the [Directory of Open Access Journals (doaj.org)](https://doaj.org/) API. Each `ISSN` in the primary dataset is queried via the API. If the `ISSN` is present in the DOAJ, additional metadata is retrieved and added to the journal's existing metadata. The full metadata schema used to integrate both data sources is available on [GitHub](../../metadata_schema/schema.yaml).

The YAML dataset is released as under [CC0 1.0 International](https://creativecommons.org/publicdomain/zero/1.0/deed.de).
