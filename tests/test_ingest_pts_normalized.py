from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.ingest.pts_normalized import write_pts_normalized_observations


def test_write_pts_normalized_observations_bridges_processed_parquet(
    database_url: str,
    tmp_path,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    parquet_path = tmp_path / "pts_country_year.parquet"
    pd.DataFrame(
        [
            {
                "country": "United States",
                "cow_code": "USA",
                "year": 2023,
                "region": "na",
                "pts_amnesty_score": 2,
                "pts_human_rights_watch_score": pd.NA,
                "pts_state_dept_score": 3,
            },
            {
                "country": "Kosovo",
                "cow_code": "NA",
                "year": 2023,
                "region": "eca",
                "pts_amnesty_score": 1,
                "pts_human_rights_watch_score": 1,
                "pts_state_dept_score": 1,
            },
            {
                "country": "Austria",
                "cow_code": "AUS",
                "year": 2023,
                "region": "eca",
                "pts_amnesty_score": 1,
                "pts_human_rights_watch_score": pd.NA,
                "pts_state_dept_score": pd.NA,
            },
        ]
    ).to_parquet(parquet_path, index=False)

    result = write_pts_normalized_observations(
        engine=engine,
        parquet_path=parquet_path,
    )

    assert result.rows_written == 6
    assert result.rows_skipped_missing_value == 3
    assert result.rows_unresolved_country == 0
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT observation_id, country_code, indicator_code, value_json
                FROM normalized_observations
                WHERE source_slug = 'pts'
                ORDER BY observation_id
                """
            )
        ).mappings().all()
    assert len(rows) == 6
    assert {row["country_code"] for row in rows} == {"AUT", "USA", "XKX"}
    assert {
        row["indicator_code"] for row in rows if row["country_code"] == "USA"
    } == {"pts_amnesty_score", "pts_state_dept_score"}
