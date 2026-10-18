from datetime import datetime, date

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Text,
)

from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# DATABASE CONNECTION
# ============================================================

DATABASE_URL = "sqlite:///./adpilot.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


# ============================================================
# USERS
# ============================================================

class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash = Column(
        String,
        nullable=False,
    )

    first_name = Column(String)
    last_name = Column(String)

    is_active = Column(
        Boolean,
        default=True,
    )

    is_admin = Column(
        Boolean,
        default=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# CAMPAIGNS
# ============================================================

class CampaignDB(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    name = Column(
        String,
        nullable=False,
    )

    monthly_budget = Column(
        Float,
        nullable=False,
    )

    discovery_budget = Column(
        Float,
        default=0,
    )

    country = Column(String)

    status = Column(
        String,
        default="draft",
    )

    spent_today = Column(
        Float,
        default=0,
    )

    spending_date = Column(
        Date,
        default=date.today,
    )

    spent_this_month = Column(
        Float,
        default=0,
    )

    spending_month = Column(
        Integer,
        default=date.today().month,
    )

    discovery_spent = Column(
        Float,
        default=0,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# SPENDING TRANSACTIONS
# ============================================================

class SpendingTransactionDB(Base):
    __tablename__ = "spending_transactions"

    id = Column(Integer, primary_key=True, index=True)

    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.id"),
        nullable=False,
        index=True,
    )

    amount = Column(
        Float,
        nullable=False,
    )

    platform = Column(
        String,
        default="unknown",
    )

    country = Column(String)

    spending_type = Column(
        String,
        default="normal",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# EXPERIMENTS
# ============================================================

class ExperimentDB(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)

    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.id"),
        nullable=False,
        index=True,
    )

    name = Column(String)

    experiment_type = Column(String)

    target = Column(String)

    platform = Column(String)

    budget = Column(
        Float,
        default=0,
    )

    spent = Column(
        Float,
        default=0,
    )

    clicks = Column(
        Integer,
        default=0,
    )

    conversions = Column(
        Integer,
        default=0,
    )

    revenue = Column(
        Float,
        default=0,
    )

    status = Column(
        String,
        default="planned",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    completed_at = Column(
        DateTime,
        nullable=True,
    )


# ============================================================
# DISCOUNT CODES
# ============================================================

class DiscountCodeDB(Base):
    __tablename__ = "discount_codes"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )

    discount_type = Column(
        String,
        nullable=False,
    )
    # "percentage" or "fixed"

    discount_value = Column(
        Float,
        nullable=False,
    )

    max_redemptions = Column(
        Integer,
        default=1,
    )

    redemption_count = Column(
        Integer,
        default=0,
    )

    expires_at = Column(
        DateTime,
        nullable=True,
    )

    is_active = Column(
        Boolean,
        default=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# DISCOUNT REDEMPTIONS
# ============================================================

class DiscountRedemptionDB(Base):
    __tablename__ = "discount_redemptions"

    id = Column(Integer, primary_key=True, index=True)

    discount_code_id = Column(
        Integer,
        ForeignKey("discount_codes.id"),
        nullable=False,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    amount_saved = Column(
        Float,
        default=0,
    )

    redeemed_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# SUBSCRIPTIONS
# ============================================================

class SubscriptionDB(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    plan = Column(
        String,
        default="free",
    )

    status = Column(
        String,
        default="active",
    )

    stripe_customer_id = Column(
        String,
        nullable=True,
    )

    stripe_subscription_id = Column(
        String,
        nullable=True,
    )

    current_period_start = Column(
        DateTime,
        nullable=True,
    )

    current_period_end = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# AI DECISION LOG
# ============================================================

class AIDecisionDB(Base):
    __tablename__ = "ai_decisions"

    id = Column(Integer, primary_key=True, index=True)

    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.id"),
        nullable=True,
        index=True,
    )

    decision_type = Column(String)

    platform = Column(String)

    country = Column(String)

    region = Column(String)

    audience = Column(String)

    day_of_week = Column(String)

    hour = Column(Integer)

    recommended_budget = Column(Float)

    expected_roas = Column(Float)

    confidence = Column(Float)

    reason = Column(Text)

    status = Column(
        String,
        default="shadow",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# AD PLATFORM CONNECTIONS
# ============================================================

class PlatformConnectionDB(Base):
    __tablename__ = "platform_connections"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    platform = Column(
        String,
        nullable=False,
    )

    account_id = Column(String)

    access_token = Column(Text)

    refresh_token = Column(Text)

    is_active = Column(
        Boolean,
        default=True,
    )

    connected_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# ADVERTISEMENTS
# ============================================================

class AdvertisementDB(Base):
    __tablename__ = "advertisements"

    id = Column(Integer, primary_key=True, index=True)

    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.id"),
        nullable=False,
        index=True,
    )

    name = Column(String)

    creative_url = Column(String)

    headline = Column(String)

    description = Column(Text)

    status = Column(
        String,
        default="active",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# CREATE DATABASE TABLES
# ============================================================

Base.metadata.create_all(bind=engine)
