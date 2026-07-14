# Run configs

A run config is a YAML file consumed by :func:`leaders_db.config.load_config`.

| File | Target year | Notes |
|---|---|---|
| `prototype-2023.yaml` | 2023 | First prototype run, targets the client's existing 2023 matrix. |
| `research-models.yaml` | n/a | Versioned Codex/provider profiles for dossier researcher, dossier formatter, and chapter judge roles. Profiles describe capability/cost classes and credential/config file locations but never contain credentials. |
| `research-discovery.yaml` | n/a | Versioned eight-chapter search themes plus soft 5–20 retained-evidence goals and bounded discovery controls. Values are persisted into each dossier job. |
| `research-pricing.yaml` | n/a | Dated official rate-card snapshot used for API/Codex-credit equivalents and Parallel Search cost. |

Naming convention: ``<scope>-<year>.yaml``. The CLI's default config path
is ``configs/prototype-2023.yaml``; pass ``--config <path>`` to override.

Each run is reproducible from its config + the contents of `data/raw/<source>/`
+ the contents of `data/processed/<source>/`. See
`docs/architecture/local-data-store.md` for the data-lake layout.

Research model profiles are candidates, not scientific defaults. A
`low_cost_candidate` such as MiniMax M2.7, OpenAI Luna, or OpenAI Terra must pass
dossier-quality evaluation before broad use. Judge eligibility additionally
requires chapter-specific calibration testing. The local Codex catalog exposes
Luna as a fast/affordable candidate and Terra as a balanced candidate; these
descriptions are not project benchmark results or fixed price claims. The
readiness command checks that referenced Codex configuration and credential files
exist without reading or emitting credential contents.

`research-pricing.yaml` keeps estimated economics auditable. Codex exposes
aggregate execution-turn counters, not actual invoices or each underlying request.
The worker separates cached from uncached input, does not add reasoning output a
second time, and reports a range when an aggregate crosses a per-request
long-context threshold. Subscription/Coding Plan runs keep actual billed cash
unknown; API-equivalent dollars and Codex credits are comparison metrics.

`research-workflow.yaml` defines the ordered chapter pass, soft 5–20 source-claim
goal, source-family goal, and maximum three evidence-review rounds. One persistent
researcher session searches the internet directly and iteratively; neither a fixed
query allowance nor a preselected link packet limits the evidence it may inspect.
MiniMax profiles disable unrelated Codex apps, plugins, multi-agent, and goals to
reduce unsupported connector calls; this is a runtime compatibility control, not a
quality endorsement.
