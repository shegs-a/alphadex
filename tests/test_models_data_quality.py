"""Data-quality tests for the core schema (ADR-003 / ADR-004).

These assert the central data-integrity guarantee: missing data is explicit and is
never stored as a real value (and, in particular, never coerced to ``0``).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alphadex.models import Asset, MetricObservation, ValueStatus


def _asset(session: Session) -> Asset:
    asset = Asset(symbol="AAA", name="Asset A", category="DeFi")
    session.add(asset)
    session.flush()
    return asset


def test_ok_observation_requires_a_value(session: Session) -> None:
    asset = _asset(session)
    session.add(
        MetricObservation(
            asset_id=asset.id,
            metric="revenue",
            value=1000,
            value_status=ValueStatus.OK,
            unit="USD",
            period="30d",
            observed_at=datetime.now(UTC),
            source_provider="test",
        )
    )
    session.commit()  # should succeed


def test_ok_observation_without_value_is_rejected(session: Session) -> None:
    asset = _asset(session)
    session.add(
        MetricObservation(
            asset_id=asset.id,
            metric="revenue",
            value=None,
            value_status=ValueStatus.OK,
            period="30d",
            observed_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "status",
    [ValueStatus.UNKNOWN, ValueStatus.NOT_AVAILABLE, ValueStatus.NOT_APPLICABLE],
)
def test_missing_status_must_have_null_value(
    session: Session, status: ValueStatus
) -> None:
    """Missing data must be recorded as NULL + status, never as a number (e.g. 0)."""
    asset = _asset(session)
    session.add(
        MetricObservation(
            asset_id=asset.id,
            metric="fees",
            value=0,  # deliberately wrong: pretending missing data is zero
            value_status=status,
            period="30d",
            observed_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "status",
    [ValueStatus.UNKNOWN, ValueStatus.NOT_AVAILABLE, ValueStatus.NOT_APPLICABLE],
)
def test_missing_status_with_null_value_is_accepted(
    session: Session, status: ValueStatus
) -> None:
    asset = _asset(session)
    obs = MetricObservation(
        asset_id=asset.id,
        metric="fees",
        value=None,
        value_status=status,
        period="30d",
        observed_at=datetime.now(UTC),
    )
    session.add(obs)
    session.commit()
    assert obs.value is None
    assert obs.value_status is status


def test_observations_are_append_only_history(session: Session) -> None:
    """Multiple observations of the same metric/period coexist as history (ADR-004)."""
    asset = _asset(session)
    for value, observed in ((100, "2026-08-01"), (150, "2026-08-15")):
        session.add(
            MetricObservation(
                asset_id=asset.id,
                metric="revenue",
                value=value,
                value_status=ValueStatus.OK,
                period="30d",
                observed_at=datetime.fromisoformat(observed).replace(tzinfo=UTC),
            )
        )
    session.commit()

    rows = (
        session.query(MetricObservation)
        .filter_by(asset_id=asset.id, metric="revenue", period="30d")
        .all()
    )
    assert len(rows) == 2
