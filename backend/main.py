from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env', override=False)

from datetime import datetime, date
from typing import Optional

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from database import (
    Base,
    engine,
    SessionLocal,
    UserDB,
    CampaignDB,
    SpendingTransactionDB,
    ExperimentDB,
    DiscountCodeDB,
    DiscountRedemptionDB,
    SubscriptionDB,
    AIDecisionDB,
    PlatformConnectionDB,
    AdvertisementDB,
)

from auth import (
    get_db,
    hash_password,
    authenticate_user,
    create_access_token,
    get_current_user,
    require_admin,
)

from token_crypto import encrypt_token
from billing import router as billing_router
from plan_config import get_campaign_limit
from platform_oauth import router as platform_oauth_router
from account_discovery import router as account_discovery_router


# ============================================================
# DATABASE
# ============================================================

Base.metadata.create_all(bind=engine)


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="AdPilot API",
    description="AI advertising optimization platform",
    version="2.0.0",
)

app.include_router(billing_router)
app.include_router(platform_oauth_router)
app.include_router(account_discovery_router)


# ============================================================
# GENERAL
# ============================================================


from safety import (
    get_safety_summary,
    pause_campaign,
    resume_campaign,
    emergency_pause_campaign,
    record_spend as safety_record_spend,
)

from budget_controller import (
    validate_allocation_batch,
)

from ml_engine import (
    ml_engine,
    calculate_opportunity_score,
)


from platform_executor import (
    PlatformExecutor,
    sync_platform_data,
)

from admin_bootstrap import (
    bootstrap_admin,
)


from ai_pipeline import (
    run_ai_pipeline,
)

from campaign_rules import (
    evaluate_campaign_rules,
    filter_allocations,
)

@app.get("/")
def home():
    return {
        "name": "AdPilot",
        "version": "2.0.0",
        "status": "online",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
    }


# ============================================================
# USER SCHEMAS
# ============================================================

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    is_active: bool
    is_admin: bool

    class Config:
        from_attributes = True


# ============================================================
# AUTH
# ============================================================

@app.post("/auth/register")
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    email = user_data.email.lower()

    existing = (
        db.query(UserDB)
        .filter(UserDB.email == email)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="An account with that email already exists",
        )

    user = UserDB(
        email=email,
        password_hash=hash_password(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    subscription = SubscriptionDB(
        user_id=user.id,
        plan="none",
        status="pending",
    )

    db.add(subscription)
    db.commit()

    return {
        "message": "Account created",
        "user_id": user.id,
        "email": user.email,
    }


@app.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(
        db,
        form_data.username,
        form_data.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "is_admin": user.is_admin,
        },
    }


@app.get("/auth/me")
def me(
    current_user: UserDB = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "is_admin": current_user.is_admin,
        "is_active": current_user.is_active,
    }


# ============================================================
# CAMPAIGN SCHEMAS
# ============================================================

class CampaignCreate(BaseModel):
    name: str
    monthly_budget: float = Field(gt=0)
    discovery_budget: float = Field(default=0, ge=0)
    country: Optional[str] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    monthly_budget: Optional[float] = Field(
        default=None,
        gt=0,
    )
    discovery_budget: Optional[float] = Field(
        default=None,
        ge=0,
    )
    country: Optional[str] = None
    status: Optional[str] = None


# ============================================================
# CAMPAIGNS
# ============================================================

@app.post("/campaigns")
def create_campaign(
    campaign_data: CampaignCreate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subscription = (
        db.query(SubscriptionDB)
        .filter(SubscriptionDB.user_id == current_user.id)
        .first()
    )

    campaign_limit = (
        get_campaign_limit(subscription.plan)
        if subscription is not None
        and subscription.status == "active"
        else None
    )

    if campaign_limit is None:
        raise HTTPException(
            status_code=402,
            detail="An active paid AdPilot subscription is required to create campaigns.",
        )

    campaign_count = (
        db.query(CampaignDB)
        .filter(CampaignDB.user_id == current_user.id)
        .count()
    )

    if campaign_count >= campaign_limit:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Your {subscription.plan.title()} plan allows "
                f"up to {campaign_limit} campaigns. Upgrade your plan to create more."
            ),
        )

    campaign = CampaignDB(
        user_id=current_user.id,
        name=campaign_data.name,
        monthly_budget=campaign_data.monthly_budget,
        discovery_budget=campaign_data.discovery_budget,
        country=campaign_data.country,
        status="draft",
    )

    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return campaign


@app.get("/campaigns")
def get_campaigns(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(CampaignDB)
        .filter(
            CampaignDB.user_id == current_user.id
        )
        .all()
    )


@app.get("/campaigns/{campaign_id}")
def get_campaign(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    return campaign


@app.patch("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    updates = data.model_dump(exclude_unset=True)

    for key, value in updates.items():
        setattr(campaign, key, value)

    db.commit()
    db.refresh(campaign)

    return campaign


@app.delete("/campaigns/{campaign_id}")
def delete_campaign(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    db.delete(campaign)
    db.commit()

    return {
        "message": "Campaign deleted"
    }


# ============================================================
# SPENDING
# ============================================================

class SpendRequest(BaseModel):
    amount: float = Field(gt=0)
    platform: str = "unknown"
    country: Optional[str] = None
    spending_type: str = "normal"


def reset_daily_and_monthly_counters(
    campaign: CampaignDB,
):
    today = date.today()

    if campaign.spending_date != today:
        campaign.spent_today = 0
        campaign.spending_date = today

    current_month = today.month

    if campaign.spending_month != current_month:
        campaign.spent_this_month = 0
        campaign.spending_month = current_month


@app.post("/campaigns/{campaign_id}/spend")
def record_spend(
    campaign_id: int,
    data: SpendRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    reset_daily_and_monthly_counters(campaign)

    # Monthly pacing target.
    today = date.today()
    days_in_month = 30

    daily_limit = (
        campaign.monthly_budget
        / days_in_month
    )

    if data.spending_type == "normal":

        if (
            campaign.spent_today + data.amount
            > daily_limit
        ):
            raise HTTPException(
                status_code=400,
                detail="Daily budget limit exceeded",
            )

        if (
            campaign.spent_this_month + data.amount
            > campaign.monthly_budget
        ):
            raise HTTPException(
                status_code=400,
                detail="Monthly budget limit exceeded",
            )

        campaign.spent_today += data.amount
        campaign.spent_this_month += data.amount

    elif data.spending_type == "discovery":

        available = (
            campaign.discovery_budget
            - campaign.discovery_spent
        )

        if data.amount > available:
            raise HTTPException(
                status_code=400,
                detail="Discovery budget exceeded",
            )

        campaign.discovery_spent += data.amount

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid spending type",
        )

    transaction = SpendingTransactionDB(
        campaign_id=campaign.id,
        amount=data.amount,
        platform=data.platform,
        country=data.country,
        spending_type=data.spending_type,
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return {
        "message": "Spend recorded",
        "transaction_id": transaction.id,
        "amount": data.amount,
        "spending_type": data.spending_type,
    }


@app.get("/campaigns/{campaign_id}/budget")
def get_budget(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    reset_daily_and_monthly_counters(campaign)

    db.commit()

    return {
        "monthly_budget": campaign.monthly_budget,
        "spent_this_month": campaign.spent_this_month,
        "monthly_remaining": max(
            campaign.monthly_budget
            - campaign.spent_this_month,
            0,
        ),
        "discovery_budget": campaign.discovery_budget,
        "discovery_spent": campaign.discovery_spent,
        "discovery_remaining": max(
            campaign.discovery_budget
            - campaign.discovery_spent,
            0,
        ),
        "daily_spent": campaign.spent_today,
        "daily_target": campaign.monthly_budget / 30,
    }


# ============================================================
# EXPERIMENTS
# ============================================================

class ExperimentCreate(BaseModel):
    name: str
    experiment_type: str
    target: str
    platform: str = "unknown"
    budget: float = Field(gt=0)


class ExperimentResult(BaseModel):
    spent: float = Field(ge=0)
    clicks: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    revenue: float = Field(default=0, ge=0)


@app.post("/campaigns/{campaign_id}/experiments")
def create_experiment(
    campaign_id: int,
    data: ExperimentCreate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    reserved = (
        db.query(ExperimentDB)
        .filter(
            ExperimentDB.campaign_id == campaign.id,
            ExperimentDB.status == "planned",
        )
        .all()
    )

    reserved_budget = sum(
        experiment.budget
        for experiment in reserved
    )

    available = (
        campaign.discovery_budget
        - campaign.discovery_spent
        - reserved_budget
    )

    if data.budget > available:
        raise HTTPException(
            status_code=400,
            detail="Not enough discovery budget available",
        )

    experiment = ExperimentDB(
        campaign_id=campaign.id,
        name=data.name,
        experiment_type=data.experiment_type,
        target=data.target,
        platform=data.platform,
        budget=data.budget,
        status="planned",
    )

    db.add(experiment)
    db.commit()
    db.refresh(experiment)

    return experiment


@app.get("/campaigns/{campaign_id}/experiments")
def get_experiments(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    return (
        db.query(ExperimentDB)
        .filter(
            ExperimentDB.campaign_id == campaign.id
        )
        .all()
    )


@app.post("/experiments/{experiment_id}/result")
def complete_experiment(
    experiment_id: int,
    result: ExperimentResult,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    experiment = (
        db.query(ExperimentDB)
        .join(
            CampaignDB,
            ExperimentDB.campaign_id == CampaignDB.id,
        )
        .filter(
            ExperimentDB.id == experiment_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not experiment:
        raise HTTPException(
            status_code=404,
            detail="Experiment not found",
        )

    if result.spent > experiment.budget:
        raise HTTPException(
            status_code=400,
            detail="Experiment spent exceeds experiment budget",
        )

    experiment.spent = result.spent
    experiment.clicks = result.clicks
    experiment.conversions = result.conversions
    experiment.revenue = result.revenue
    experiment.status = "completed"
    experiment.completed_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Experiment completed",
        "experiment_id": experiment.id,
        "spent": experiment.spent,
        "revenue": experiment.revenue,
        "roas": (
            experiment.revenue / experiment.spent
            if experiment.spent > 0
            else 0
        ),
    }


# ============================================================
# ADVERTISEMENTS
# ============================================================

class AdvertisementCreate(BaseModel):
    name: str
    creative_url: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None


@app.post("/campaigns/{campaign_id}/advertisements")
def create_advertisement(
    campaign_id: int,
    data: AdvertisementCreate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    advertisement = AdvertisementDB(
        campaign_id=campaign.id,
        name=data.name,
        creative_url=data.creative_url,
        headline=data.headline,
        description=data.description,
    )

    db.add(advertisement)
    db.commit()
    db.refresh(advertisement)

    return advertisement


@app.get("/campaigns/{campaign_id}/advertisements")
def get_advertisements(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    return (
        db.query(AdvertisementDB)
        .filter(
            AdvertisementDB.campaign_id == campaign.id
        )
        .all()
    )


# ============================================================
# PLATFORM CONNECTIONS
# ============================================================

class PlatformConnectionCreate(BaseModel):
    platform: str
    account_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


@app.post("/platform-connections")
def create_platform_connection(
    data: PlatformConnectionCreate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Normalize supported platform names to a consistent value.
    platform_input = data.platform.strip().lower()
    platform_aliases = {
        "google": "google",
        "google_ads": "google",
        "meta": "meta",
        "facebook": "meta",
        "instagram": "meta",
    }

    platform = platform_aliases.get(platform_input)
    if platform is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported platform. Use Google Ads or Meta.",
        )

    # Never store credentials unless encryption succeeds.
    try:
        encrypted_access_token = encrypt_token(data.access_token)
        encrypted_refresh_token = encrypt_token(data.refresh_token)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token encryption is not configured correctly.",
        )

    connection = PlatformConnectionDB(
        user_id=current_user.id,
        platform=platform,
        account_id=data.account_id,
        access_token=encrypted_access_token,
        refresh_token=encrypted_refresh_token,
    )

    db.add(connection)
    db.commit()
    db.refresh(connection)

    return {
        "id": connection.id,
        "platform": connection.platform,
        "account_id": connection.account_id,
        "is_active": connection.is_active,
    }


@app.get("/platform-connections")
def get_platform_connections(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connections = (
        db.query(PlatformConnectionDB)
        .filter(
            PlatformConnectionDB.user_id
            == current_user.id
        )
        .all()
    )

    return [
        {
            "id": connection.id,
            "platform": connection.platform,
            "account_id": connection.account_id,
            "is_active": connection.is_active,
        }
        for connection in connections
    ]


# ============================================================
# AI DECISION LOGGING
# ============================================================

class AIDecisionCreate(BaseModel):
    campaign_id: Optional[int] = None
    decision_type: str
    platform: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    audience: Optional[str] = None
    day_of_week: Optional[str] = None
    hour: Optional[int] = None
    recommended_budget: float = 0
    expected_roas: float = 0
    confidence: float = 0
    reason: Optional[str] = None
    status: str = "shadow"


@app.post("/ai-decisions")
def create_ai_decision(
    data: AIDecisionCreate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.campaign_id is not None:

        campaign = (
            db.query(CampaignDB)
            .filter(
                CampaignDB.id == data.campaign_id,
                CampaignDB.user_id == current_user.id,
            )
            .first()
        )

        if not campaign:
            raise HTTPException(
                status_code=404,
                detail="Campaign not found",
            )

    decision = AIDecisionDB(
        campaign_id=data.campaign_id,
        decision_type=data.decision_type,
        platform=data.platform,
        country=data.country,
        region=data.region,
        audience=data.audience,
        day_of_week=data.day_of_week,
        hour=data.hour,
        recommended_budget=data.recommended_budget,
        expected_roas=data.expected_roas,
        confidence=data.confidence,
        reason=data.reason,
        status=data.status,
    )

    db.add(decision)
    db.commit()
    db.refresh(decision)

    return decision


@app.get("/ai-decisions")
def get_ai_decisions(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaigns = (
        db.query(CampaignDB.id)
        .filter(
            CampaignDB.user_id == current_user.id
        )
        .all()
    )

    campaign_ids = [
        campaign.id
        for campaign in campaigns
    ]

    return (
        db.query(AIDecisionDB)
        .filter(
            AIDecisionDB.campaign_id.in_(
                campaign_ids
            )
        )
        .order_by(
            AIDecisionDB.created_at.desc()
        )
        .all()
    )


# ============================================================
# ADMIN
# ============================================================

@app.get("/admin/overview")
def admin_overview(
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {
        "users": db.query(UserDB).count(),
        "campaigns": db.query(CampaignDB).count(),
        "experiments": db.query(ExperimentDB).count(),
        "advertisements": db.query(AdvertisementDB).count(),
        "subscriptions": db.query(SubscriptionDB).count(),
        "discount_codes": db.query(DiscountCodeDB).count(),
        "ai_decisions": db.query(AIDecisionDB).count(),
        "platform_connections": db.query(
            PlatformConnectionDB
        ).count(),
    }


@app.get("/admin/users")
def admin_users(
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(UserDB).all()

    return [
        {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "is_admin": user.is_admin,
            "created_at": user.created_at,
        }
        for user in users
    ]


# ============================================================
# DISCOUNT CODES
# ============================================================

class DiscountCreate(BaseModel):
    code: str
    discount_type: str
    discount_value: float = Field(gt=0)
    max_redemptions: int = Field(default=1, gt=0)
    expires_at: Optional[datetime] = None


@app.post("/admin/discounts")
def create_discount(
    data: DiscountCreate,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    code = data.code.upper().strip()

    if data.discount_type not in {
        "percentage",
        "fixed",
    }:
        raise HTTPException(
            status_code=400,
            detail="discount_type must be percentage or fixed",
        )

    if (
        data.discount_type == "percentage"
        and data.discount_value > 100
    ):
        raise HTTPException(
            status_code=400,
            detail="Percentage discount cannot exceed 100",
        )

    existing = (
        db.query(DiscountCodeDB)
        .filter(
            DiscountCodeDB.code == code
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Discount code already exists",
        )

    discount = DiscountCodeDB(
        code=code,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        max_redemptions=data.max_redemptions,
        expires_at=data.expires_at,
    )

    db.add(discount)
    db.commit()
    db.refresh(discount)

    return discount


@app.get("/admin/discounts")
def list_discounts(
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(DiscountCodeDB).all()


# ============================================================
# DISCOUNT REDEMPTION
# ============================================================

class DiscountRedeem(BaseModel):
    code: str
    purchase_amount: float = Field(gt=0)


@app.post("/discounts/redeem")
def redeem_discount(
    data: DiscountRedeem,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = data.code.upper().strip()

    discount = (
        db.query(DiscountCodeDB)
        .filter(
            DiscountCodeDB.code == code,
            DiscountCodeDB.is_active == True,
        )
        .first()
    )

    if not discount:
        raise HTTPException(
            status_code=404,
            detail="Invalid discount code",
        )

    if (
        discount.expires_at
        and datetime.utcnow() > discount.expires_at
    ):
        raise HTTPException(
            status_code=400,
            detail="Discount code has expired",
        )

    if (
        discount.redemption_count
        >= discount.max_redemptions
    ):
        raise HTTPException(
            status_code=400,
            detail="Discount code has already been used",
        )

    previous = (
        db.query(DiscountRedemptionDB)
        .filter(
            DiscountRedemptionDB.discount_code_id
            == discount.id,
            DiscountRedemptionDB.user_id
            == current_user.id,
        )
        .first()
    )

    if previous:
        raise HTTPException(
            status_code=400,
            detail="You have already redeemed this code",
        )

    if discount.discount_type == "percentage":
        savings = (
            data.purchase_amount
            * discount.discount_value
            / 100
        )

    else:
        savings = min(
            discount.discount_value,
            data.purchase_amount,
        )

    redemption = DiscountRedemptionDB(
        discount_code_id=discount.id,
        user_id=current_user.id,
        amount_saved=savings,
    )

    discount.redemption_count += 1

    if (
        discount.redemption_count
        >= discount.max_redemptions
    ):
        discount.is_active = False

    db.add(redemption)
    db.commit()

    return {
        "code": discount.code,
        "purchase_amount": data.purchase_amount,
        "amount_saved": savings,
        "final_amount": (
            data.purchase_amount - savings
        ),
    }


# ============================================================
# SUBSCRIPTION
# ============================================================

@app.get("/subscription")
def get_subscription(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subscription = (
        db.query(SubscriptionDB)
        .filter(
            SubscriptionDB.user_id
            == current_user.id
        )
        .first()
    )

    if not subscription:
        subscription = SubscriptionDB(
            user_id=current_user.id,
            plan="none",
            status="pending",
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

    # Legacy free accounts do not receive paid access.
    if subscription.plan and subscription.plan.strip().lower() == "free":
        subscription.plan = "none"
        subscription.status = "pending"
        db.commit()
        db.refresh(subscription)

    return subscription


# ============================================================
# OPTIMIZATION ENDPOINTS
# ============================================================

from optimizer import run_optimization_pipeline


@app.get("/campaigns/{campaign_id}/optimization")
def optimize_campaign(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    experiments = (
        db.query(ExperimentDB)
        .filter(
            ExperimentDB.campaign_id == campaign.id
        )
        .all()
    )

    available_budget = max(
        campaign.monthly_budget
        - campaign.spent_this_month,
        0,
    )

    result = run_optimization_pipeline(
        experiments,
        available_budget,
    )

    # Log the optimization decision.
    for allocation in result["final_allocations"]:

        decision = AIDecisionDB(
            campaign_id=campaign.id,
            decision_type="final_allocation",
            platform=allocation.get("platform"),
            country=campaign.country,
            region=allocation.get("target"),
            recommended_budget=allocation.get(
                "recommended_budget",
                0,
            ),
            expected_roas=allocation.get(
                "expected_roas",
                0,
            ),
            confidence=allocation.get(
                "confidence",
                0,
            ),
            reason=(
                "Prototype optimization engine "
                "allocation"
            ),
            status="shadow",
        )

        db.add(decision)

    db.commit()

    return result


# ============================================================
# SAFETY / BUDGET CONTROLLER
# ============================================================

@app.get("/campaigns/{campaign_id}/safety")
def campaign_safety(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    return get_safety_summary(campaign)


# ============================================================
# PAUSE CAMPAIGN
# ============================================================

@app.post("/campaigns/{campaign_id}/pause")
def pause_campaign_route(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    pause_campaign(campaign)
    db.commit()

    return {
        "message": "Campaign paused",
        "campaign_id": campaign.id,
        "status": campaign.status,
    }


# ============================================================
# RESUME CAMPAIGN
# ============================================================

@app.post("/campaigns/{campaign_id}/resume")
def resume_campaign_route(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    resume_campaign(campaign)
    db.commit()

    return {
        "message": "Campaign resumed",
        "campaign_id": campaign.id,
        "status": campaign.status,
    }


# ============================================================
# EMERGENCY PAUSE
# ============================================================

@app.post("/campaigns/{campaign_id}/emergency-pause")
def emergency_pause_route(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    emergency_pause_campaign(campaign)
    db.commit()

    return {
        "message": "EMERGENCY PAUSE ACTIVATED",
        "campaign_id": campaign.id,
        "status": campaign.status,
    }


# ============================================================
# SAFE SPEND TEST
# ============================================================

@app.post("/campaigns/{campaign_id}/safe-spend")
def safe_spend(
    campaign_id: int,
    amount: float,
    platform: str = "test",
    country: str | None = None,
    spending_type: str = "normal",
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    try:
        transaction = safety_record_spend(
            db=db,
            campaign=campaign,
            amount=amount,
            platform=platform,
            country=country,
            spending_type=spending_type,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    return {
        "message": "Spend approved and recorded",
        "transaction_id": transaction.id,
        "amount": transaction.amount,
        "spending_type": transaction.spending_type,
        "safety": get_safety_summary(campaign),
    }


# ============================================================
# VALIDATE OPTIMIZER ALLOCATIONS
# ============================================================

@app.post("/campaigns/{campaign_id}/validate-allocations")
def validate_allocations(
    campaign_id: int,
    allocations: list[dict],
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    return validate_allocation_batch(
        db=db,
        campaign=campaign,
        allocations=allocations,
    )


# ============================================================
# ML TRAINING
# ============================================================

@app.post("/ml/train")
def train_ml_model(
    rows: list[dict],
    current_user: UserDB = Depends(get_current_user),
):
    return ml_engine.train(rows)


# ============================================================
# ML PREDICTION
# ============================================================

@app.post("/ml/predict")
def predict_revenue(
    spend: float,
    impressions: float,
    clicks: float,
    conversions: float,
    current_user: UserDB = Depends(get_current_user),
):
    return ml_engine.predict_revenue(
        spend=spend,
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
    )


# ============================================================
# OPPORTUNITY SCORE
# ============================================================

@app.post("/ml/opportunity-score")
def opportunity_score(
    expected_roas: float,
    confidence: float,
    sample_size: int,
    current_user: UserDB = Depends(get_current_user),
):
    score = calculate_opportunity_score(
        expected_roas=expected_roas,
        confidence=confidence,
        sample_size=sample_size,
    )

    return {
        "score": score,
        "expected_roas": expected_roas,
        "confidence": confidence,
        "sample_size": sample_size,
    }


# ============================================================
# PLATFORM STATUS
# ============================================================

@app.get("/platforms/status")
def platform_status(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    connections = (
        db.query(PlatformConnectionDB)
        .filter(
            PlatformConnectionDB.user_id
            == current_user.id
        )
        .all()
    )

    result = {
        "google": False,
        "meta": False,
    }

    for connection in connections:

        platform = connection.platform.lower()

        if platform in {
            "google",
            "google_ads",
        }:
            result["google"] = connection.is_active

        if platform in {
            "meta",
            "facebook",
            "instagram",
        }:
            result["meta"] = connection.is_active

    return result


# ============================================================
# PLATFORM EXECUTION PREVIEW
# ============================================================

@app.post("/campaigns/{campaign_id}/platform-execution-preview")
def platform_execution_preview(
    campaign_id: int,
    allocation: dict,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    executor = PlatformExecutor(
        db=db,
        campaign=campaign,
    )

    return executor.prepare_execution(
        allocation
    )


# ============================================================
# PLATFORM EXECUTION
# ============================================================

@app.post("/campaigns/{campaign_id}/platform-execute")
def platform_execute(
    campaign_id: int,
    allocation: dict,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    if campaign.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Campaign must be active before platform execution.",
        )

    executor = PlatformExecutor(
        db=db,
        campaign=campaign,
    )

    return executor.execute(
        allocation
    )


# ============================================================
# PLATFORM DATA SYNC
# ============================================================

@app.post("/campaigns/{campaign_id}/sync-platform")
def sync_campaign_platform(
    campaign_id: int,
    platform: str,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    return sync_platform_data(
        db=db,
        campaign=campaign,
        platform=platform,
    )


# ============================================================
# ADMIN BOOTSTRAP
# ============================================================

@app.post("/admin/bootstrap")
def admin_bootstrap_route(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Administrator access required",
        )

    return bootstrap_admin(db)


# ============================================================
# ADMIN PLATFORM OVERVIEW
# ============================================================

@app.get("/admin/platform-connections")
def admin_platform_connections(
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):

    connections = (
        db.query(PlatformConnectionDB)
        .all()
    )

    return [
        {
            "id": connection.id,
            "user_id": connection.user_id,
            "platform": connection.platform,
            "account_id": connection.account_id,
            "is_active": connection.is_active,
            "connected_at": connection.connected_at,
        }
        for connection in connections
    ]


# ============================================================
# AI PIPELINE
# ============================================================

@app.post("/campaigns/{campaign_id}/run-ai")
def run_campaign_ai(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    experiments = (
        db.query(ExperimentDB)
        .filter(
            ExperimentDB.campaign_id
            == campaign.id
        )
        .all()
    )

    return run_ai_pipeline(
        db=db,
        campaign=campaign,
        experiments=experiments,
    )


# ============================================================
# CAMPAIGN RULE TEST
# ============================================================

@app.post("/campaigns/{campaign_id}/check-rule")
def check_campaign_rule(
    campaign_id: int,
    allocation: dict,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    # Prototype rules can be supplied through the request.
    campaign_data = {
        "id": campaign.id,
        "name": campaign.name,
        "rules": allocation.pop(
            "_rules",
            {},
        ),
    }

    allowed, reason = evaluate_campaign_rules(
        campaign_data,
        allocation,
    )

    return {
        "allowed": allowed,
        "reason": reason,
        "allocation": allocation,
    }


# ============================================================
# SHADOW MODE
# ============================================================

@app.get("/campaigns/{campaign_id}/shadow-decisions")
def shadow_decisions(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    campaign = (
        db.query(CampaignDB)
        .filter(
            CampaignDB.id == campaign_id,
            CampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found",
        )

    decisions = (
        db.query(AIDecisionDB)
        .filter(
            AIDecisionDB.campaign_id
            == campaign.id,

            AIDecisionDB.status
            == "shadow",
        )
        .order_by(
            AIDecisionDB.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": decision.id,
            "decision_type": decision.decision_type,
            "platform": decision.platform,
            "country": decision.country,
            "region": decision.region,
            "audience": decision.audience,
            "day_of_week": decision.day_of_week,
            "hour": decision.hour,
            "recommended_budget": decision.recommended_budget,
            "expected_roas": decision.expected_roas,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "status": decision.status,
            "created_at": decision.created_at,
        }
        for decision in decisions
    ]


# ============================================================
# AI DECISION APPROVAL
# ============================================================

@app.post("/admin/ai-decisions/{decision_id}/approve")
def approve_ai_decision(
    decision_id: int,
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):

    decision = (
        db.query(AIDecisionDB)
        .filter(
            AIDecisionDB.id == decision_id
        )
        .first()
    )

    if not decision:
        raise HTTPException(
            status_code=404,
            detail="AI decision not found",
        )

    if decision.status != "shadow":
        raise HTTPException(status_code=409, detail=f"Cannot approve a decision with status {decision.status!r}.")

    decision.status = "approved"

    db.commit()

    return {
        "message": "AI decision approved",
        "decision_id": decision.id,
        "status": decision.status,
    }


# ============================================================
# AI DECISION REJECTION
# ============================================================

@app.post("/admin/ai-decisions/{decision_id}/reject")
def reject_ai_decision(
    decision_id: int,
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):

    decision = (
        db.query(AIDecisionDB)
        .filter(
            AIDecisionDB.id == decision_id
        )
        .first()
    )

    if not decision:
        raise HTTPException(
            status_code=404,
            detail="AI decision not found",
        )

    if decision.status != "shadow":
        raise HTTPException(status_code=409, detail=f"Cannot reject a decision with status {decision.status!r}.")

    decision.status = "rejected"

    db.commit()

    return {
        "message": "AI decision rejected",
        "decision_id": decision.id,
        "status": decision.status,
    }

# ============================================================
# ADPILOT_GROWTH_API_V1
# New AI planning endpoints. Recommendations only; no live ad spend.
# ============================================================

from typing import Any
from market_discovery import discover_markets
from regional_discovery import discover_regions
from experiment_planner import create_experiment_plan
from experiment_learning import learn_from_experiments
from growth_planner import build_growth_plan


class MarketDiscoveryRequest(BaseModel):
    campaign: dict
    markets: list[dict]
    max_markets: int = Field(default=3, ge=1, le=25)


class RegionalDiscoveryRequest(BaseModel):
    country: str
    regions: list[dict]
    max_regions: int = Field(default=5, ge=1, le=50)


class ExperimentPlanRequest(BaseModel):
    discovery_budget: float = Field(ge=0)
    round_budget: Optional[float] = Field(default=None, ge=0)
    market_discovery: dict
    max_experiments: int = Field(default=3, ge=1, le=25)


class ExperimentLearningRequest(BaseModel):
    experiments: list[dict]


class GrowthPlanRequest(BaseModel):
    campaign: dict
    markets: list[dict]
    discovery_budget: float = Field(ge=0)
    round_budget: Optional[float] = Field(default=None, ge=0)
    regions_by_country: dict[str, list[dict]] = Field(default_factory=dict)
    experiment_results: list[dict] = Field(default_factory=list)
    max_markets: int = Field(default=3, ge=1, le=25)
    max_regions: int = Field(default=5, ge=1, le=50)


@app.post("/ai/market-discovery")
def api_market_discovery(
    payload: MarketDiscoveryRequest,
    current_user: UserDB = Depends(get_current_user),
):
    try:
        return discover_markets(
            payload.campaign,
            payload.markets,
            max_markets=payload.max_markets,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/ai/regional-discovery")
def api_regional_discovery(
    payload: RegionalDiscoveryRequest,
    current_user: UserDB = Depends(get_current_user),
):
    try:
        return discover_regions(
            payload.country,
            payload.regions,
            max_regions=payload.max_regions,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/ai/experiment-plan")
def api_experiment_plan(
    payload: ExperimentPlanRequest,
    current_user: UserDB = Depends(get_current_user),
):
    try:
        return create_experiment_plan(
            discovery_budget=payload.discovery_budget,
            round_budget=payload.round_budget,
            market_discovery=payload.market_discovery,
            max_experiments=payload.max_experiments,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/ai/learn")
def api_experiment_learning(
    payload: ExperimentLearningRequest,
    current_user: UserDB = Depends(get_current_user),
):
    try:
        return learn_from_experiments(payload.experiments)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/ai/growth-plan")
def api_growth_plan(
    payload: GrowthPlanRequest,
    current_user: UserDB = Depends(get_current_user),
):
    try:
        return build_growth_plan(
            campaign=payload.campaign,
            markets=payload.markets,
            discovery_budget=payload.discovery_budget,
            round_budget=payload.round_budget,
            regions_by_country=payload.regions_by_country,
            experiment_results=payload.experiment_results,
            max_markets=payload.max_markets,
            max_regions=payload.max_regions,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

# ============================================================
# ADPILOT_SAVED_GROWTH_PLAN_V1
# Uses saved campaign and experiment records.
# Recommendations only: never launches ads or spends money.
# ============================================================

from datetime import date as _growth_date
from database import CampaignDB as _GrowthCampaignDB
from database import ExperimentDB as _GrowthExperimentDB


class SavedGrowthPlanRequest(BaseModel):
    # Supply market candidates and optional campaign context.
    # Actual campaign budgets and country come from the database.
    markets: list[dict] = Field(default_factory=list)
    campaign_context: dict = Field(default_factory=dict)
    regions_by_country: dict[str, list[dict]] = Field(default_factory=dict)
    round_budget: Optional[float] = Field(default=None, ge=0)
    max_markets: int = Field(default=3, ge=1, le=25)
    max_regions: int = Field(default=5, ge=1, le=50)


@app.post("/campaigns/{campaign_id}/growth-plan")
def saved_campaign_growth_plan(
    campaign_id: int,
    payload: SavedGrowthPlanRequest,
    current_user: UserDB = Depends(get_current_user),
    db=Depends(get_db),
):
    # Only the owner of the campaign may use its records.
    campaign = (
        db.query(_GrowthCampaignDB)
        .filter(
            _GrowthCampaignDB.id == campaign_id,
            _GrowthCampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if campaign is None:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found.",
        )

    # Calculate remaining discovery budget from saved spending.
    total_discovery_budget = max(
        0.0, float(campaign.discovery_budget or 0)
    )
    discovery_spent = max(
        0.0, float(campaign.discovery_spent or 0)
    )
    remaining_discovery_budget = round(
        max(0.0, total_discovery_budget - discovery_spent), 2
    )

    requested_round_budget = payload.round_budget
    if requested_round_budget is None:
        effective_round_budget = remaining_discovery_budget
    else:
        effective_round_budget = min(
            float(requested_round_budget),
            remaining_discovery_budget,
        )

    # Load this campaign's actual saved experiment records.
    saved_experiments = (
        db.query(_GrowthExperimentDB)
        .filter(_GrowthExperimentDB.campaign_id == campaign.id)
        .all()
    )

    # Learn from experiments that have recorded results.
    experiment_results = []
    for experiment in saved_experiments:
        spend = float(experiment.spent or 0)
        revenue = float(experiment.revenue or 0)

        if (
            str(experiment.status or "").lower() == "completed"
            or spend > 0
        ):
            experiment_results.append({
                "experiment_id": experiment.id,
                "name": experiment.name,
                "experiment_type": experiment.experiment_type,
                "target": experiment.target,
                "platform": experiment.platform,
                "status": experiment.status,
                "country": (
                    experiment.target
                    if experiment.experiment_type == "country"
                    else campaign.country
                ),
                "spend": spend,
                "revenue": revenue,
                "clicks": int(experiment.clicks or 0),
                "conversions": int(experiment.conversions or 0),
            })

    # Saved budget/country fields override caller-provided values.
    campaign_data = dict(payload.campaign_context)
    campaign_data.update({
        "id": campaign.id,
        "name": campaign.name,
        "country": campaign.country,
        "monthly_budget": float(campaign.monthly_budget or 0),
        "discovery_budget": remaining_discovery_budget,
        "month": _growth_date.today().month,
    })

    try:
        report = build_growth_plan(
            campaign=campaign_data,
            markets=payload.markets,
            discovery_budget=remaining_discovery_budget,
            round_budget=effective_round_budget,
            regions_by_country=payload.regions_by_country,
            experiment_results=experiment_results,
            max_markets=payload.max_markets,
            max_regions=payload.max_regions,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    report["saved_campaign"] = {
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "country": campaign.country,
        "monthly_budget": float(campaign.monthly_budget or 0),
        "discovery_budget_total": total_discovery_budget,
        "discovery_spent_recorded": discovery_spent,
        "discovery_budget_remaining": remaining_discovery_budget,
    }
    report["data_sources"] = {
        "campaign_loaded_from_database": True,
        "experiments_loaded_from_database": True,
        "experiments_available": len(saved_experiments),
        "experiments_with_results_analyzed": len(experiment_results),
        "market_candidates_supplied": len(payload.markets),
    }
    report["spending_executed"] = False

    return report


# ============================================================
# ADPILOT_RECOMMENDATION_LEDGER_V1
# Persists review-only AI budget recommendations.
# No platform execution or actual spending.
# ============================================================

from database import AIDecisionDB as _GrowthAIDecisionDB


class BudgetRecommendationItem(BaseModel):
    decision_type: str = Field(min_length=1, max_length=80)
    platform: str = Field(default="unknown", max_length=80)
    country: Optional[str] = None
    region: Optional[str] = None
    audience: Optional[str] = None
    day_of_week: Optional[str] = None
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    recommended_budget: float = Field(ge=0)
    expected_roas: float = Field(default=0, ge=0)
    confidence: float = Field(default=0, ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)


class SaveBudgetRecommendationsRequest(BaseModel):
    recommendations: list[BudgetRecommendationItem] = Field(
        min_length=1, max_length=100
    )


@app.post("/campaigns/{campaign_id}/ai-recommendations")
def save_campaign_ai_recommendations(
    campaign_id: int,
    payload: SaveBudgetRecommendationsRequest,
    current_user: UserDB = Depends(get_current_user),
    db=Depends(get_db),
):
    campaign = (
        db.query(_GrowthCampaignDB)
        .filter(
            _GrowthCampaignDB.id == campaign_id,
            _GrowthCampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    monthly_budget = max(0.0, float(campaign.monthly_budget or 0))
    month_spend = max(0.0, float(campaign.spent_this_month or 0))
    monthly_remaining = round(max(0.0, monthly_budget - month_spend), 2)

    proposed_total = round(
        sum(item.recommended_budget for item in payload.recommendations), 2
    )

    if proposed_total > monthly_remaining + 0.000001:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Recommendations exceed the campaign's remaining monthly budget.",
                "monthly_budget": monthly_budget,
                "spent_this_month": month_spend,
                "monthly_remaining": monthly_remaining,
                "proposed_total": proposed_total,
            },
        )

    saved = []
    try:
        for item in payload.recommendations:
            decision = _GrowthAIDecisionDB(
                campaign_id=campaign.id,
                decision_type=item.decision_type,
                platform=item.platform,
                country=item.country or campaign.country,
                region=item.region,
                audience=item.audience,
                day_of_week=item.day_of_week,
                hour=item.hour,
                recommended_budget=item.recommended_budget,
                expected_roas=item.expected_roas,
                confidence=item.confidence,
                reason=item.reason,
                status="shadow",
            )
            db.add(decision)
            saved.append(decision)

        db.commit()

        for decision in saved:
            db.refresh(decision)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not save recommendations. No ads were launched.",
        )

    return {
        "campaign_id": campaign.id,
        "recommendations_saved": len(saved),
        "proposed_total": proposed_total,
        "monthly_remaining_at_save": monthly_remaining,
        "status": "shadow",
        "spending_executed": False,
        "recommendations": [
            {
                "id": decision.id,
                "decision_type": decision.decision_type,
                "platform": decision.platform,
                "country": decision.country,
                "region": decision.region,
                "audience": decision.audience,
                "day_of_week": decision.day_of_week,
                "hour": decision.hour,
                "recommended_budget": decision.recommended_budget,
                "expected_roas": decision.expected_roas,
                "confidence": decision.confidence,
                "reason": decision.reason,
                "status": decision.status,
            }
            for decision in saved
        ],
    }


# ============================================================
# ADPILOT_RECOMMENDATION_LIST_V1
# Lists saved AI recommendations for the campaign owner.
# Review-only: this endpoint never launches ads.
# ============================================================

@app.get("/campaigns/{campaign_id}/ai-recommendations")
def list_campaign_ai_recommendations(
    campaign_id: int,
    status: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db=Depends(get_db),
):
    campaign = (
        db.query(_GrowthCampaignDB)
        .filter(
            _GrowthCampaignDB.id == campaign_id,
            _GrowthCampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    query = db.query(_GrowthAIDecisionDB).filter(
        _GrowthAIDecisionDB.campaign_id == campaign.id
    )

    if status:
        query = query.filter(_GrowthAIDecisionDB.status == status)

    decisions = query.order_by(
        _GrowthAIDecisionDB.id.desc()
    ).all()

    return {
        "campaign_id": campaign.id,
        "count": len(decisions),
        "status_filter": status,
        "spending_executed": False,
        "recommendations": [
            {
                "id": item.id,
                "decision_type": item.decision_type,
                "platform": item.platform,
                "country": item.country,
                "region": item.region,
                "audience": item.audience,
                "day_of_week": item.day_of_week,
                "hour": item.hour,
                "recommended_budget": item.recommended_budget,
                "expected_roas": item.expected_roas,
                "confidence": item.confidence,
                "reason": item.reason,
                "status": item.status,
                "created_at": (
                    item.created_at.isoformat()
                    if item.created_at
                    else None
                ),
            }
            for item in decisions
        ],
    }


# ============================================================
# ADPILOT_RECOMMENDATION_REVIEW_V1
# Owner-controlled approval/rejection; no live ad execution.
# ============================================================

class ReviewAIRecommendationRequest(BaseModel):
    action: str = Field(min_length=1, max_length=20)
    review_note: Optional[str] = Field(default=None, max_length=2000)


@app.post(
    "/campaigns/{campaign_id}/ai-recommendations/{decision_id}/review"
)
def review_campaign_ai_recommendation(
    campaign_id: int,
    decision_id: int,
    payload: ReviewAIRecommendationRequest,
    current_user: UserDB = Depends(get_current_user),
    db=Depends(get_db),
):
    action = payload.action.strip().lower()

    if action not in {"approve", "reject"}:
        raise HTTPException(
            status_code=422,
            detail="Action must be 'approve' or 'reject'.",
        )

    campaign = (
        db.query(_GrowthCampaignDB)
        .filter(
            _GrowthCampaignDB.id == campaign_id,
            _GrowthCampaignDB.user_id == current_user.id,
        )
        .first()
    )

    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    decision = (
        db.query(_GrowthAIDecisionDB)
        .filter(
            _GrowthAIDecisionDB.id == decision_id,
            _GrowthAIDecisionDB.campaign_id == campaign.id,
        )
        .first()
    )

    if decision is None:
        raise HTTPException(
            status_code=404,
            detail="Recommendation not found for this campaign.",
        )

    if decision.status not in {"shadow", "pending", "approved", "rejected"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot review a recommendation with status '{decision.status}'.",
        )

    decision.status = "approved" if action == "approve" else "rejected"

    if payload.review_note:
        existing_reason = decision.reason or ""
        decision.reason = (
            existing_reason
            + "\nReview note: "
            + payload.review_note.strip()
        )[:2000]

    try:
        db.commit()
        db.refresh(decision)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not save the recommendation review.",
        )

    return {
        "campaign_id": campaign.id,
        "recommendation_id": decision.id,
        "status": decision.status,
        "review_action": action,
        "spending_executed": False,
        "message": (
            "Recommendation approved for review; no ads were launched."
            if action == "approve"
            else "Recommendation rejected; no ads were launched."
        ),
    }


# ============================================================
# ADPILOT_BACKEND_COMPLETION_PACK_V1
# Dashboard, analytics, budget visibility and saved growth plans.
# Review-only: this pack never launches ads or spends money.
# ============================================================

import json as _adpilot_completion_json
import inspect as _adpilot_completion_inspect
from database import SpendingTransactionDB as _AdpilotTransactionDB


def _adpilot_completion_iso(value):
    return value.isoformat() if value is not None else None


def _adpilot_owned_campaign(campaign_id, current_user, db):
    campaign = (
        db.query(_GrowthCampaignDB)
        .filter(
            _GrowthCampaignDB.id == campaign_id,
            _GrowthCampaignDB.user_id == current_user.id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


def _adpilot_campaign_experiments(campaign_id, db):
    return (
        db.query(_GrowthExperimentDB)
        .filter(_GrowthExperimentDB.campaign_id == campaign_id)
        .order_by(_GrowthExperimentDB.id.desc())
        .all()
    )


def _adpilot_campaign_decisions(campaign_id, db):
    return (
        db.query(_GrowthAIDecisionDB)
        .filter(_GrowthAIDecisionDB.campaign_id == campaign_id)
        .order_by(_GrowthAIDecisionDB.id.desc())
        .all()
    )


@app.post("/campaigns/{campaign_id}/generate-and-save-growth-plan")
async def adpilot_generate_and_save_growth_plan(
    campaign_id: int,
       payload: SavedGrowthPlanRequest,
    current_user: UserDB = Depends(get_current_user),
    db=Depends(get_db),
):
    campaign = _adpilot_owned_campaign(campaign_id, current_user, db)

    growth_route = next(
        (
            route for route in app.routes
            if getattr(route, "path", None)
            == "/campaigns/{campaign_id}/growth-plan"
            and "POST" in (getattr(route, "methods", None) or set())
        ),
        None,
    )

    if growth_route is None:
        raise HTTPException(
            status_code=500,
            detail="The existing growth-plan endpoint is unavailable.",
        )

    try:
        plan = growth_route.endpoint(
            payload=payload,
            campaign_id=campaign_id,
            current_user=current_user,
            db=db,
        )
        if _adpilot_completion_inspect.isawaitable(plan):
            plan = await plan

        if not isinstance(plan, dict):
            raise ValueError("Growth plan was not returned as an object.")

        # Preserve the complete generated plan in the saved snapshot.
        snapshot = _adpilot_completion_json.dumps(
            plan, default=str, separators=(",", ":")
        )

        decision = _GrowthAIDecisionDB(
            campaign_id=campaign.id,
            decision_type="growth_plan_snapshot",
            platform="unknown",
            country=campaign.country,
            recommended_budget=0,
            expected_roas=0,
            confidence=0,
            reason="Generated growth-plan snapshot for review: " + snapshot,
            status="shadow",
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)

        return {
            "campaign_id": campaign.id,
            "snapshot_id": decision.id,
            "status": "shadow",
            "growth_plan": plan,
            "snapshot_saved": True,
            "spending_executed": False,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not generate and save the plan. No ads were launched.",
        )


@app.get("/campaigns/{campaign_id}/dashboard")
def adpilot_campaign_dashboard(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db=Depends(get_db),
):
    campaign = _adpilot_owned_campaign(campaign_id, current_user, db)
    experiments = _adpilot_campaign_experiments(campaign.id, db)
    decisions = _adpilot_campaign_decisions(campaign.id, db)

    transactions = (
        db.query(_AdpilotTransactionDB)
        .filter(_AdpilotTransactionDB.campaign_id == campaign.id)
        .order_by(_AdpilotTransactionDB.id.desc())
        .limit(20)
        .all()
    )

    monthly_budget = max(0.0, float(campaign.monthly_budget or 0))
    month_spend = max(0.0, float(campaign.spent_this_month or 0))
    discovery_budget = max(0.0, float(campaign.discovery_budget or 0))
    discovery_spend = max(0.0, float(campaign.discovery_spent or 0))

    status_counts = {}
    for decision in decisions:
        status = decision.status or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "campaign": {
            "id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "country": campaign.country,
            "monthly_budget": monthly_budget,
            "spent_this_month": month_spend,
            "monthly_remaining": round(max(0, monthly_budget - month_spend), 2),
            "discovery_budget": discovery_budget,
            "discovery_spent": discovery_spend,
            "discovery_remaining": round(
                max(0, discovery_budget - discovery_spend), 2
            ),
            "spent_today": float(campaign.spent_today or 0),
            "spending_date": _adpilot_completion_iso(campaign.spending_date),
        },
        "experiment_count": len(experiments),
        "recent_experiments": [
            {
                "id": item.id,
                "name": item.name,
                "type": item.experiment_type,
                "target": item.target,
                "platform": item.platform,
                "budget": float(item.budget or 0),
                "spent": float(item.spent or 0),
                "clicks": int(item.clicks or 0),
                "conversions": int(item.conversions or 0),
                "revenue": float(item.revenue or 0),
                "status": item.status,
            }
            for item in experiments[:10]
        ],
        "recommendation_count": len(decisions),
        "recommendation_status_counts": status_counts,
        "recent_recommendations": [
            {
                "id": item.id,
                "decision_type": item.decision_type,
                "platform": item.platform,
                "country": item.country,
                "region": item.region,
                "recommended_budget": float(item.recommended_budget or 0),
                "expected_roas": float(item.expected_roas or 0),
                "confidence": float(item.confidence or 0),
                "reason": item.reason,
                "status": item.status,
                "created_at": _adpilot_completion_iso(item.created_at),
            }
            for item in decisions[:20]
        ],
        "recent_transactions": [
            {
                "id": item.id,
                "amount": float(item.amount or 0),
                "platform": item.platform,
                "country": item.country,
                "spending_type": item.spending_type,
                "created_at": _adpilot_completion_iso(item.created_at),
            }
            for item in transactions
        ],
        "spending_executed_by_this_endpoint": False,
    }


@app.get("/campaigns/{campaign_id}/analytics")
def adpilot_campaign_analytics(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db=Depends(get_db),
):
    campaign = _adpilot_owned_campaign(campaign_id, current_user, db)
    experiments = _adpilot_campaign_experiments(campaign.id, db)

    total_spend = sum(float(item.spent or 0) for item in experiments)
    total_revenue = sum(float(item.revenue or 0) for item in experiments)
    total_clicks = sum(int(item.clicks or 0) for item in experiments)
    total_conversions = sum(int(item.conversions or 0) for item in experiments)

    return {
        "campaign_id": campaign.id,
        "experiment_count": len(experiments),
        "experiment_spend": round(total_spend, 2),
        "experiment_revenue": round(total_revenue, 2),
        "experiment_roas": (
            round(total_revenue / total_spend, 4)
            if total_spend > 0 else None
        ),
        "clicks": total_clicks,
        "conversions": total_conversions,
        "conversion_rate": (
            round(total_conversions / total_clicks, 4)
            if total_clicks > 0 else None
        ),
        "data_note": (
            "Metrics are calculated from saved experiment records. "
            "They are not independently verified platform-wide totals."
        ),
    }


@app.get("/campaigns/{campaign_id}/budget-status")
def adpilot_campaign_budget_status(
    campaign_id: int,
    current_user: UserDB = Depends(get_current_user),
    db=Depends(get_db),
):
    campaign = _adpilot_owned_campaign(campaign_id, current_user, db)

    monthly_budget = max(0.0, float(campaign.monthly_budget or 0))
    month_spend = max(0.0, float(campaign.spent_this_month or 0))
    daily_spend = max(0.0, float(campaign.spent_today or 0))
    discovery_budget = max(0.0, float(campaign.discovery_budget or 0))
    discovery_spend = max(0.0, float(campaign.discovery_spent or 0))

    configured_daily_limit = getattr(campaign, "daily_target", None)
    if configured_daily_limit is None and monthly_budget > 0:
        configured_daily_limit = round(monthly_budget / 30.4375, 2)

    daily_limit = (
        max(0.0, float(configured_daily_limit))
        if configured_daily_limit is not None else None
    )
    monthly_remaining = round(max(0.0, monthly_budget - month_spend), 2)
    discovery_remaining = round(
        max(0.0, discovery_budget - discovery_spend), 2
    )
    daily_remaining = (
        round(max(0.0, daily_limit - daily_spend), 2)
        if daily_limit is not None else None
    )

    return {
        "campaign_id": campaign.id,
        "campaign_status": campaign.status,
        "monthly_budget": monthly_budget,
        "spent_this_month": month_spend,
        "monthly_remaining": monthly_remaining,
        "daily_limit": daily_limit,
        "spent_today": daily_spend,
        "daily_remaining": daily_remaining,
        "discovery_budget": discovery_budget,
        "discovery_spent": discovery_spend,
        "discovery_remaining": discovery_remaining,
        "appears_within_recorded_limits": (
            monthly_remaining > 0
            and (daily_remaining is None or daily_remaining > 0)
        ),
        "this_is_a_status_check_not_a_spending_lock": True,
        "spending_executed": False,
    }


@app.get("/system/backend-capabilities")
def adpilot_backend_capabilities():
    registered = {
        (route.path, method)
        for route in app.routes
        if hasattr(route, "path")
        for method in (getattr(route, "methods", None) or set())
    }

    expected = {
        "growth_plan": (
            "/campaigns/{campaign_id}/growth-plan", "POST"
        ),
        "generate_and_save_growth_plan": (
            "/campaigns/{campaign_id}/generate-and-save-growth-plan", "POST"
        ),
        "recommendation_list": (
            "/campaigns/{campaign_id}/ai-recommendations", "GET"
        ),
        "recommendation_save": (
            "/campaigns/{campaign_id}/ai-recommendations", "POST"
        ),
        "recommendation_review": (
            "/campaigns/{campaign_id}/ai-recommendations/{decision_id}/review",
            "POST",
        ),
        "campaign_dashboard": (
            "/campaigns/{campaign_id}/dashboard", "GET"
        ),
        "campaign_analytics": (
            "/campaigns/{campaign_id}/analytics", "GET"
        ),
        "budget_status": (
            "/campaigns/{campaign_id}/budget-status", "GET"
        ),
    }

    return {
        "capabilities": {
            name: {
                "method": method,
                "path": path,
                "registered": (path, method) in registered,
            }
            for name, (path, method) in expected.items()
        },
        "all_expected_routes_registered": all(
            (path, method) in registered
            for path, method in expected.values()
        ),
        "live_ad_execution_enabled_by_this_pack": False,
    }
