"""Regression tests for durable hosted quota reservations."""

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import QuotaReservation, User


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def hosted_settings(_force_selfhost_settings):  # ensure conftest runs first
    import app.config as config_mod
    from app.config import Settings

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(deploy_mode="hosted", _env_file=None)
    try:
        yield
    finally:
        config_mod._settings_instance = prev


@pytest.fixture
def hosted_user(db, hosted_settings):
    user = User(
        username="hosted_user",
        hashed_password="x",
        role="admin",
        is_active=True,
        generation_quota=2,
        feedback_submitted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_quota_scope_charge_is_persisted_before_finalize(db, hosted_user):
    from app.core.auth import QuotaScope

    scope = QuotaScope(db, hosted_user.id, count=2)
    scope.reserve()
    scope.charge(1)

    reservation = db.query(QuotaReservation).filter(QuotaReservation.id == scope.reservation_id).one()
    assert reservation.reserved_count == 2
    assert reservation.charged_count == 1
    assert reservation.released_at is None

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == 0

    scope.finalize()

    db.refresh(hosted_user)
    db.refresh(reservation)
    assert hosted_user.generation_quota == 1
    assert reservation.released_at is not None


def test_reconcile_abandoned_quota_reservations_refunds_only_unused_units(db, hosted_user):
    from app.core import auth as auth_mod

    hosted_user.generation_quota = 0
    db.commit()

    reservation = QuotaReservation(
        user_id=hosted_user.id,
        reserved_count=2,
        charged_count=1,
        lease_token="stale-owner-token",
    )
    db.add(reservation)
    db.commit()

    refunded = auth_mod.reconcile_abandoned_quota_reservations(db, user_id=hosted_user.id)

    db.refresh(hosted_user)
    db.refresh(reservation)
    assert refunded == 1
    assert hosted_user.generation_quota == 1
    assert reservation.released_at is not None
