from datetime import datetime, date, timezone

from sqlalchemy import (
    Index,
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
    inspect,
)

from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# DATABASE CONNECTION
# ============================================================

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./adpilot.db").strip()

# Explicitly use Psycopg 3 for PostgreSQL connections.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql+psycopg://", 1
    )
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must not be empty.")

_connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if DATABASE_URL.startswith("sqlite:")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


# ============================================================
# AUTHENTICATION RATE LIMITS
# ============================================================

class RateLimitBucketDB(Base):
    __tablename__ = "rate_limit_buckets"

    bucket_key = Column(String(64), primary_key=True)
    request_count = Column(Integer, nullable=False, default=0)
    window_start = Column(Integer, nullable=False, index=True)


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

    spending_year = Column(
        Integer,
        default=lambda: date.today().year,
        nullable=False,
    )

    discovery_spent = Column(
        Float,
        default=0,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


# ============================================================
# SUBSCRIPTIONS
# ============================================================

class ProcessedStripeEventDB(Base):
    """Stripe webhook event IDs already handled by AdPilot."""

    __tablename__ = "processed_stripe_events"

    event_id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    event_created = Column(Integer, nullable=False)
    processed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)


class SubscriptionDB(Base):
    __tablename__ = "subscriptions"

    __table_args__ = (
        Index("uq_subscriptions_user_id", "user_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    plan = Column(
        String,
        default="none",
    )

    status = Column(
        String,
        default="pending",
    )

    stripe_customer_id = Column(
        String,
        nullable=True,
    )

    stripe_subscription_id = Column(
        String,
        nullable=True,
    )

    last_stripe_event_created = Column(Integer, nullable=True)

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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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
        default=False,
    )

    connected_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


# ============================================================
class PlatformOAuthStateDB(Base):
    __tablename__ = "platform_oauth_states"

    id = Column(Integer, primary_key=True, index=True)
    state_hash = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


# Production must use Alembic migrations instead of automatic schema creation.
if (
    os.getenv("ADPILOT_ENVIRONMENT", "development").strip().lower()
    == "production"
    and os.getenv("ADPILOT_SKIP_DB_INIT") != "1"
):
    raise RuntimeError(
        "Production database initialization is disabled. "
        "Run 'alembic upgrade head' before starting the API, "
        "and set ADPILOT_SKIP_DB_INIT=1."
    )


if os.getenv("ADPILOT_SKIP_DB_INIT") != "1":
    # ============================================================
    # CREATE DATABASE TABLES
    # ============================================================

    Base.metadata.create_all(bind=engine)

    # Enforce one subscription record per user on SQLite databases.
    # Refuse to proceed if existing data violates this invariant.
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            duplicate_users = connection.exec_driver_sql(
                "SELECT user_id, COUNT(*) FROM subscriptions "
                "GROUP BY user_id HAVING COUNT(*) > 1 LIMIT 10"
            ).fetchall()

            if duplicate_users:
                details = ", ".join(
                    f"user_id={row[0]} (records={row[1]})"
                    for row in duplicate_users
                )
                raise RuntimeError(
                    "Cannot enforce unique subscriptions: duplicate records exist: "
                    + details
                )

            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_subscriptions_user_id "
                "ON subscriptions (user_id)"
            )

    # Safely add the timestamp column to existing SQLite databases.
    if engine.dialect.name == "sqlite":
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("subscriptions")
        }
        if "last_stripe_event_created" not in columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE subscriptions "
                    "ADD COLUMN last_stripe_event_created INTEGER"
                )
