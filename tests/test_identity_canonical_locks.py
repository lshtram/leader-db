from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from leaders_db.db.models import (
    Base,
    Country,
    CountryYear,
    RulerIdentityAdjudication,
    RulerYear,
)
from leaders_db.identity.adjudications import build_ruler_identity_adjudications
from leaders_db.identity.canonical_locks import (
    LOCKED_STATUS,
    CanonicalIdentityCase,
    CanonicalIdentityManifest,
    apply_canonical_identity_locks,
    challenge_canonical_identity_lock,
)


def test_canonical_identity_lock_is_idempotent_and_survives_rebuild(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'identity.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        country = Country(
            iso3="AAA", country_name="Example", country_name_normalized="example"
        )
        session.add(country)
        session.flush()
        session.add(
            CountryYear(
                country_id=country.id,
                year=2023,
                included_in_project=True,
            )
        )
        session.commit()

    manifest = CanonicalIdentityManifest(
        year=2023,
        run_id="test-lock-v1",
        cases=(
            CanonicalIdentityCase(
                iso3="AAA",
                ruler_name="Jane Example",
                office_title="Prime Minister",
                start_date=date(2020, 1, 1),
                rationale="Formal governing officeholder.",
                source_urls=("https://example.test/jane",),
            ),
        ),
    )
    first = apply_canonical_identity_locks(engine, manifest)
    second = apply_canonical_identity_locks(engine, manifest)
    build_ruler_identity_adjudications(engine, start_year=2023, end_year=2023)

    assert first.ruler_years_created == 1
    assert second.ruler_years_created == 0
    with Session(engine) as session:
        adjudication = session.scalar(select(RulerIdentityAdjudication))
        assert adjudication is not None
        assert adjudication.review_status == LOCKED_STATUS
        assert adjudication.selected_leader_name == "Jane Example"
        assert session.scalar(select(RulerYear).where(RulerYear.review_status == LOCKED_STATUS))


def test_canonical_identity_change_requires_explicit_challenge(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'identity.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        country = Country(
            iso3="AAA", country_name="Example", country_name_normalized="example"
        )
        session.add(country)
        session.flush()
        session.add(CountryYear(country_id=country.id, year=2023, included_in_project=True))
        session.commit()

    def manifest(name: str) -> CanonicalIdentityManifest:
        return CanonicalIdentityManifest(
            year=2023,
            run_id=f"lock-{name}",
            cases=(
                CanonicalIdentityCase(
                    iso3="AAA",
                    ruler_name=name,
                    office_title="President",
                    start_date=date(2020, 1, 1),
                    rationale="Formal governing officeholder.",
                    source_urls=("https://example.test/source",),
                ),
            ),
        )

    apply_canonical_identity_locks(engine, manifest("First Ruler"))
    with pytest.raises(ValueError, match="challenge it explicitly first"):
        apply_canonical_identity_locks(engine, manifest("Second Ruler"))

    challenge_canonical_identity_lock(
        engine, iso3="AAA", year=2023, reason="Documented correction"
    )
    apply_canonical_identity_locks(engine, manifest("Second Ruler"))
    with Session(engine) as session:
        adjudication = session.scalar(select(RulerIdentityAdjudication))
        assert adjudication is not None
        assert adjudication.selected_leader_name == "Second Ruler"
        assert adjudication.review_status == LOCKED_STATUS
