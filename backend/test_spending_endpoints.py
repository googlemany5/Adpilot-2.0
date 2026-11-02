import pytest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import get_current_user, get_db
from database import (
    Base,
    UserDB,
    CampaignDB,
    SpendingTransactionDB,
)
from main import app


@pytest.fixture
def spending_setup():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    db = TestingSession()

    user = UserDB(
        email="spending-test@example.com",
        password_hash="not-used",
        is_active=True,
    )
    other_user = UserDB(
        email="other-spending-test@example.com",
        password_hash="not-used",
        is_active=True,
    )

    db.add_all([user, other_user])
    db.commit()
    db.refresh(user)
    db.refresh(other_user)

    def override_get_db():
        yield db

    def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )

    client = TestClient(app)

    def make_campaign(
        owner_id=None,
        spent_today=0,
        discovery_budget=100,
        discovery_spent=0,
    ):
        campaign = CampaignDB(
            user_id=owner_id or user.id,
            name="Spending API Test",
            monthly_budget=3000,
            discovery_budget=discovery_budget,
            status="active",
            spent_today=spent_today,
            spending_date=date.today(),
            spent_this_month=spent_today,
            spending_month=date.today().month,
            spending_year=date.today().year,
            discovery_spent=discovery_spent,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign

    yield client, db, user, other_user, make_campaign

    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_regular_spend_endpoint_records_approved_spending(spending_setup):
    client, db, user, _, make_campaign = spending_setup
    campaign = make_campaign()

    response = client.post(
        f"/campaigns/{campaign.id}/spend",
        json={
            "amount": 20,
            "platform": "test",
            "country": "United States",
            "spending_type": "normal",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["amount"] == 20
    assert db.query(SpendingTransactionDB).filter_by(
        campaign_id=campaign.id
    ).count() == 1

    db.refresh(campaign)
    assert campaign.spent_today == 20


def test_safe_spend_endpoint_records_approved_spending(spending_setup):
    client, db, user, _, make_campaign = spending_setup
    campaign = make_campaign()

    response = client.post(
        f"/campaigns/{campaign.id}/safe-spend",
        params={"amount": 20, "spending_type": "normal"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["amount"] == 20

    db.refresh(campaign)
    assert campaign.spent_today == 20


def test_regular_spend_rejects_exceeded_daily_budget(spending_setup):
    client, db, user, _, make_campaign = spending_setup
    campaign = make_campaign(spent_today=90)

    response = client.post(
        f"/campaigns/{campaign.id}/spend",
        json={"amount": 20},
    )

    assert response.status_code == 400, response.text

    db.refresh(campaign)
    assert campaign.spent_today == 90
    assert db.query(SpendingTransactionDB).filter_by(
        campaign_id=campaign.id
    ).count() == 0


def test_safe_spend_rejects_exceeded_discovery_budget(spending_setup):
    client, db, user, _, make_campaign = spending_setup
    campaign = make_campaign(
        discovery_budget=10,
        discovery_spent=10,
    )

    response = client.post(
        f"/campaigns/{campaign.id}/safe-spend",
        params={"amount": 20, "spending_type": "discovery"},
    )

    assert response.status_code == 400, response.text

    db.refresh(campaign)
    assert campaign.discovery_spent == 10
    assert campaign.spent_today == 0
    assert db.query(SpendingTransactionDB).filter_by(
        campaign_id=campaign.id
    ).count() == 0


def test_spend_rejects_campaign_owned_by_another_user(spending_setup):
    client, db, user, other_user, make_campaign = spending_setup
    campaign = make_campaign(owner_id=other_user.id)

    response = client.post(
        f"/campaigns/{campaign.id}/spend",
        json={"amount": 20},
    )

    assert response.status_code == 404

    assert db.query(SpendingTransactionDB).filter_by(
        campaign_id=campaign.id
    ).count() == 0

@pytest.mark.parametrize("amount", [True, False, "nan", "inf", "-inf"])
def test_regular_spend_rejects_invalid_amounts(spending_setup, amount):
    client, db, user, _, make_campaign = spending_setup
    campaign = make_campaign()

    response = client.post(
        f"/campaigns/{campaign.id}/spend",
        json={"amount": amount},
    )

    assert response.status_code == 422, response.text
    db.refresh(campaign)
    assert campaign.spent_today == 0
    assert db.query(SpendingTransactionDB).filter_by(
        campaign_id=campaign.id
    ).count() == 0
