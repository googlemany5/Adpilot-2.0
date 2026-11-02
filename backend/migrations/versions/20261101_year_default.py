"""Remove the hardcoded spending_year database default."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261101_year_default"
down_revision = "20261101_spending_year"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())

    if "campaigns" not in inspector.get_table_names():
        return

    columns = {
        column["name"]: column
        for column in inspector.get_columns("campaigns")
    }

    if "spending_year" not in columns:
        return

    if columns["spending_year"]["default"] is None:
        return

    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.alter_column(
            "spending_year",
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=None,
        )


def downgrade():
    inspector = inspect(op.get_bind())

    if "campaigns" not in inspector.get_table_names():
        return

    columns = {
        column["name"]: column
        for column in inspector.get_columns("campaigns")
    }

    if "spending_year" not in columns:
        return

    if columns["spending_year"]["default"] is not None:
        return

    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.alter_column(
            "spending_year",
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=sa.text("'2026'"),
        )
