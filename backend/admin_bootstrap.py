import os

from sqlalchemy.orm import Session

from database import UserDB
from auth import hash_password


# ============================================================
# ADMIN BOOTSTRAP
# ============================================================

def bootstrap_admin(db: Session):
    """
    Creates the first administrator from environment variables.

    Required:

        ADPILOT_ADMIN_EMAIL
        ADPILOT_ADMIN_PASSWORD

    This is intentionally NOT exposed as a public API endpoint.
    """

    admin_email = os.getenv(
        "ADPILOT_ADMIN_EMAIL"
    )

    admin_password = os.getenv(
        "ADPILOT_ADMIN_PASSWORD"
    )

    if not admin_email or not admin_password:
        return {
            "created": False,
            "reason": (
                "Admin environment variables are not configured."
            ),
        }

    admin_email = admin_email.lower().strip()

    user = (
        db.query(UserDB)
        .filter(UserDB.email == admin_email)
        .first()
    )

    if user:

        if not user.is_admin:
            user.is_admin = True
            db.commit()

        return {
            "created": False,
            "admin": True,
            "email": admin_email,
            "reason": "Existing account promoted to administrator.",
        }

    user = UserDB(
        email=admin_email,
        password_hash=hash_password(
            admin_password
        ),
        first_name="Admin",
        last_name="",
        is_active=True,
        is_admin=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "created": True,
        "admin": True,
        "user_id": user.id,
        "email": user.email,
    }
