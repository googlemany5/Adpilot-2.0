from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import get_current_user, get_db
from database import (
    Base,
    UserDB,
    CampaignDB,
    ExperimentDB,
    PlatformConnectionDB,
)
from main import app


@pytest.fixture
def api_setup():
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
        email="missing-endpoints@example.com",
        password_hash="not-used",
        is_active=True,
    )
    other_user = UserDB(
        email="other-missing-endpoints@example.com",
        password_hash="not-used",
        is_active=True,
    )
    db.add_all([user, other_user])
    db.commit()
    db.refresh(user)
    db.refresh(other_user)

    def override_db():
        yield db

    def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    client = TestClient(app)

    def make_campaign(owner_id=None, status="active"):
        campaign = CampaignDB(
            user_id=owner_id or user.id,
            name="Endpoint Coverage Campaign",
            monthly_budget=3000,
            discovery_budget=100,
            status=status,
            spent_today=0,
            spending_date=date.today(),
            spent_this_month=0,
            spending_month=date.today().month,
            spending_year=date.today().year,
            discovery_spent=0,
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


def test_experiment_creation_and_listing(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    response = client.post(
        f"/campaigns/{campaign.id}/experiments",
        json={
            "name": "Montana Test",
            "experiment_type": "region",
            "target": "Montana",
            "platform": "meta",
            "budget": 60,
        },
    )
    assert response.status_code == 200, response.text
    experiment_id = response.json()["id"]

    listing = client.get(
        f"/campaigns/{campaign.id}/experiments"
    )
    assert listing.status_code == 200, listing.text
    assert any(item["id"] == experiment_id for item in listing.json())


def test_experiments_cannot_reserve_more_than_discovery_budget(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    for name in ("First", "Second"):
        response = client.post(
            f"/campaigns/{campaign.id}/experiments",
            json={
                "name": name,
                "experiment_type": "country",
                "target": "United States",
                "platform": "meta",
                "budget": 60,
            },
        )

        if name == "First":
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 400, response.text

    assert (
        db.query(ExperimentDB)
        .filter_by(campaign_id=campaign.id)
        .count()
        == 1
    )


def test_experiment_result_records_roas(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    created = client.post(
        f"/campaigns/{campaign.id}/experiments",
        json={
            "name": "ROAS Test",
            "experiment_type": "country",
            "target": "United States",
            "platform": "meta",
            "budget": 100,
        },
    )
    assert created.status_code == 200, created.text

    experiment_id = created.json()["id"]

    result = client.post(
        f"/experiments/{experiment_id}/result",
        json={
            "spent": 75,
            "clicks": 50,
            "conversions": 5,
            "revenue": 300,
        },
    )

    assert result.status_code == 200, result.text
    assert result.json()["roas"] == 4
    assert result.json()["spent"] == 75

    db_exp = db.query(ExperimentDB).filter_by(id=experiment_id).first()
    assert db_exp.status == "completed"
    assert db_exp.conversions == 5


def test_experiment_result_cannot_exceed_planned_budget(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    created = client.post(
        f"/campaigns/{campaign.id}/experiments",
        json={
            "name": "Budget Limit Test",
            "experiment_type": "country",
            "target": "Canada",
            "platform": "google",
            "budget": 50,
        },
    )
    assert created.status_code == 200, created.text

    experiment_id = created.json()["id"]

    result = client.post(
        f"/experiments/{experiment_id}/result",
        json={
            "spent": 75,
            "clicks": 10,
            "conversions": 1,
            "revenue": 100,
        },
    )

    assert result.status_code == 400, result.text

    db_exp = db.query(ExperimentDB).filter_by(id=experiment_id).first()
    assert db_exp.status == "planned"
    assert db_exp.spent == 0


def test_optimization_endpoint_returns_allocations(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    created = client.post(
        f"/campaigns/{campaign.id}/experiments",
        json={
            "name": "Optimization Test",
            "experiment_type": "country",
            "target": "United States",
            "platform": "meta",
            "budget": 100,
        },
    )
    assert created.status_code == 200, created.text

    result = client.post(
        f"/experiments/{created.json()['id']}/result",
        json={
            "spent": 50,
            "clicks": 100,
            "conversions": 10,
            "revenue": 200,
        },
    )
    assert result.status_code == 200, result.text

    optimized = client.get(
        f"/campaigns/{campaign.id}/optimization"
    )
    assert optimized.status_code == 200, optimized.text

    data = optimized.json()
    assert "ranked_experiments" in data
    assert "final_allocations" in data


def test_pause_resume_and_emergency_pause(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    paused = client.post(f"/campaigns/{campaign.id}/pause")
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"

    resumed = client.post(f"/campaigns/{campaign.id}/resume")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "active"

    emergency = client.post(
        f"/campaigns/{campaign.id}/emergency-pause"
    )
    assert emergency.status_code == 200, emergency.text
    assert emergency.json()["status"] == "emergency_paused"

    db.refresh(campaign)
    assert campaign.status == "emergency_paused"


def test_campaign_controls_reject_another_users_campaign(api_setup):
    client, db, user, other_user, make_campaign = api_setup
    campaign = make_campaign(owner_id=other_user.id)

    for action in ("pause", "resume", "emergency-pause"):
        response = client.post(
            f"/campaigns/{campaign.id}/{action}"
        )
        assert response.status_code == 404, (
            f"{action}: {response.status_code} {response.text}"
        )

    db.refresh(campaign)
    assert campaign.status == "active"


def test_platform_status_defaults_to_disconnected(api_setup):
    client, db, user, _, make_campaign = api_setup

    response = client.get("/platforms/status")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "google": False,
        "meta": False,
    }


def test_platform_status_reports_active_connections(api_setup):
    client, db, user, _, make_campaign = api_setup

    db.add_all([
        PlatformConnectionDB(
            user_id=user.id,
            platform="google",
            is_active=True,
        ),
        PlatformConnectionDB(
            user_id=user.id,
            platform="meta",
            is_active=False,
        ),
    ])
    db.commit()

    response = client.get("/platforms/status")
    assert response.status_code == 200, response.text
    assert response.json()["google"] is True
    assert response.json()["meta"] is False


def test_ml_training_endpoint(api_setup):
    client, db, user, _, make_campaign = api_setup

    response = client.post(
        "/ml/train",
        json=[
            {
                "spend": 100,
                "impressions": 5000,
                "clicks": 100,
                "conversions": 5,
                "revenue": 300,
            },
            {
                "spend": 150,
                "impressions": 7000,
                "clicks": 140,
                "conversions": 8,
                "revenue": 500,
            },
            {
                "spend": 200,
                "impressions": 9000,
                "clicks": 180,
                "conversions": 11,
                "revenue": 700,
            },
        ],
    )

    assert response.status_code == 200, response.text
    assert response.json() is not None


def test_experiment_cannot_be_completed_twice(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    created = client.post(
        f"/campaigns/{campaign.id}/experiments",
        json={
            "name": "Single Completion Test",
            "experiment_type": "country",
            "target": "United States",
            "platform": "meta",
            "budget": 50,
        },
    )
    assert created.status_code == 200, created.text

    experiment_id = created.json()["id"]
    result_data = {
        "spent": 25,
        "clicks": 10,
        "conversions": 2,
        "revenue": 100,
    }

    first = client.post(
        f"/experiments/{experiment_id}/result",
        json=result_data,
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/experiments/{experiment_id}/result",
        json=result_data,
    )
    assert second.status_code == 409, second.text


def test_experiment_completion_does_not_double_count_discovery_spend(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    created = client.post(
        f"/campaigns/{campaign.id}/experiments",
        json={
            "name": "Discovery Accounting Test",
            "experiment_type": "country",
            "target": "Canada",
            "platform": "google",
            "budget": 50,
        },
    )
    assert created.status_code == 200, created.text

    experiment_id = created.json()["id"]

    result = client.post(
        f"/experiments/{experiment_id}/result",
        json={
            "spent": 25,
            "clicks": 10,
            "conversions": 2,
            "revenue": 100,
        },
    )
    assert result.status_code == 200, result.text

    db.refresh(campaign)
    assert campaign.discovery_spent == 0


def test_experiment_completion_rejects_invalid_spend_without_changes(api_setup):
    client, db, user, _, make_campaign = api_setup
    campaign = make_campaign()

    created = client.post(
        f"/campaigns/{campaign.id}/experiments",
        json={
            "name": "Invalid Completion Test",
            "experiment_type": "country",
            "target": "United States",
            "platform": "meta",
            "budget": 50,
        },
    )
    assert created.status_code == 200, created.text

    experiment_id = created.json()["id"]

    result = client.post(
        f"/experiments/{experiment_id}/result",
        json={
            "spent": 75,
            "clicks": 10,
            "conversions": 1,
            "revenue": 100,
        },
    )
    assert result.status_code == 400

    db.refresh(campaign)
    experiment = db.query(ExperimentDB).filter_by(id=experiment_id).first()

    assert experiment.status == "planned"
    assert experiment.spent == 0
    assert campaign.discovery_spent == 0
