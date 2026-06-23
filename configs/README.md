# Run configs

A run config is a YAML file consumed by :func:`leaders_db.config.load_config`.

| File | Target year | Notes |
|---|---|---|
| `prototype-2023.yaml` | 2023 | First prototype run, targets the client's existing 2023 matrix. |

Naming convention: ``<scope>-<year>.yaml``. The CLI's default config path
is ``configs/prototype-2023.yaml``; pass ``--config <path>`` to override.

Each run is reproducible from its config + the contents of `data/raw/<source>/`
+ the contents of `data/processed/<source>/`. See
`docs/architecture/local-data-store.md` for the data-lake layout.
