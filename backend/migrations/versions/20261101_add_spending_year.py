"""Add spending year to campaign budget tracking."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261101_spending_year"
down_revision = "9ed1067fa64a"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())

    if "campaigns" not in inspector.get_table_names():
        raise RuntimeError("Cannot add spending_year: campaigns table is missing")

    columns = {
        column["name"]
        for column in inspector.get_columns("campaigns")
    }

    if "spending_year" not in columns:
        op.add_column(
            "campaigns",
            sa.Column(
                "spending_year",
                sa.Integer(),
                nullable=False,
                server_default="2026",
            ),
        )


def downgrade():
    inspector = inspect(op.get_bind())

    if "campaigns" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("campaigns")
    }

    if "spending_year" in columns:
        with op.batch_alter_table("campaigns") as batch_op:
            batch_op.drop_column("spending_year")
