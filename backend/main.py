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


# ============================================================
# GENERAL
# ============================================================


from safety import (
    get_safety_summary,
    pause_campaign,
    resume_campaign,
    emergency_pause_campaign,
    record_spend,
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
        plan="free",
        status="active",
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
    connection = PlatformConnectionDB(
        user_id=current_user.id,
        platform=data.platform,
        account_id=data.account_id,
        access_token=data.access_token,
        refresh_token=data.refresh_token,
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
            plan="free",
            status="active",
        )

        db.add(subscription)
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
        transaction = record_spend(
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

    decision.status = "rejected"

    db.commit()

    return {
        "message": "AI decision rejected",
        "decision_id": decision.id,
        "status": decision.status,
    }
