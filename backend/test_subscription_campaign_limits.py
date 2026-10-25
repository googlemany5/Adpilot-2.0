import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import get_current_user, get_db
from database import Base, UserDB, SubscriptionDB, CampaignDB
from main import app


@pytest.fixture
def subscription_test_setup():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
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
        email="subscription-test@example.com",
        password_hash="not-used-in-this-test",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    def override_get_db():
        yield db

    def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )

    client = TestClient(app)

    yield client, db, user

    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def campaign_payload(name="Subscription Test Campaign"):
    return {
        "name": name,
        "monthly_budget": 1000,
        "discovery_budget": 100,
        "country": "United States",
    }


def add_subscription(db, user, plan="starter", status="active"):
    subscription = SubscriptionDB(
        user_id=user.id,
        plan=plan,
        status=status,
    )
    db.add(subscription)
    db.commit()
    return subscription


def test_campaign_creation_rejected_without_subscription(
    subscription_test_setup,
):
    client, db, user = subscription_test_setup

    response = client.post(
        "/campaigns",
        json=campaign_payload(),
    )

    assert response.status_code == 402
    assert "active paid AdPilot subscription" in response.json()["detail"]
    assert db.query(CampaignDB).filter_by(user_id=user.id).count() == 0


def test_active_starter_subscription_allows_campaign_creation(
    subscription_test_setup,
):
    client, db, user = subscription_test_setup
    add_subscription(db, user, plan="starter", status="active")

    response = client.post(
        "/campaigns",
        json=campaign_payload(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Subscription Test Campaign"
    assert response.json()["status"] == "draft"
    assert db.query(CampaignDB).filter_by(user_id=user.id).count() == 1


def test_starter_campaign_limit_blocks_fourth_campaign(
    subscription_test_setup,
):
    client, db, user = subscription_test_setup
    add_subscription(db, user, plan="starter", status="active")

    for number in range(1, 4):
        response = client.post(
            "/campaigns",
            json=campaign_payload(f"Starter Campaign {number}"),
        )
        assert response.status_code == 200, response.text

    response = client.post(
        "/campaigns",
        json=campaign_payload("Fourth Campaign"),
    )

    assert response.status_code == 403
    assert "up to 3 campaigns" in response.json()["detail"]
    assert db.query(CampaignDB).filter_by(user_id=user.id).count() == 3


def test_pending_subscription_cannot_create_campaign(
    subscription_test_setup,
):
    client, db, user = subscription_test_setup
    add_subscription(db, user, plan="starter", status="pending")

    response = client.post(
        "/campaigns",
        json=campaign_payload(),
    )

    assert response.status_code == 402
    assert db.query(CampaignDB).filter_by(user_id=user.id).count() == 0
