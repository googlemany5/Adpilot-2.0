"""Add persistent authentication rate-limit buckets."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261101_auth_rate_limits"
down_revision = "20261101_year_default"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = inspect(connection)
    tables = inspector.get_table_names()

    if "rate_limit_buckets" not in tables:
        op.create_table(
            "rate_limit_buckets",
            sa.Column("bucket_key", sa.String(length=64), primary_key=True),
            sa.Column(
                "request_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "window_start",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    else:
        columns = {
            column["name"]
            for column in inspector.get_columns("rate_limit_buckets")
        }

        if "window_start" not in columns:
            op.add_column(
                "rate_limit_buckets",
                sa.Column(
                    "window_start",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )

    inspector = inspect(connection)
    indexes = {
        index["name"]
        for index in inspector.get_indexes("rate_limit_buckets")
    }

    if "ix_rate_limit_buckets_window_start" not in indexes:
        op.create_index(
            "ix_rate_limit_buckets_window_start",
            "rate_limit_buckets",
            ["window_start"],
        )


def downgrade():
    connection = op.get_bind()
    inspector = inspect(connection)

    if "rate_limit_buckets" not in inspector.get_table_names():
        return

    indexes = {
        index["name"]
        for index in inspector.get_indexes("rate_limit_buckets")
    }

    if "ix_rate_limit_buckets_window_start" in indexes:
        op.drop_index(
            "ix_rate_limit_buckets_window_start",
            table_name="rate_limit_buckets",
        )

    columns = {
        column["name"]
        for column in inspector.get_columns("rate_limit_buckets")
    }

    if "window_start" in columns:
        with op.batch_alter_table("rate_limit_buckets") as batch:
            batch.drop_column("window_start")
