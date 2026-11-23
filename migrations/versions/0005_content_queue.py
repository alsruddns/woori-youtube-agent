"""Add lease and progress metadata to content plans."""
from alembic import op
import sqlalchemy as sa

revision = "0005_content_queue"
down_revision = "0004_content_plans"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("content_plans", sa.Column("claimed_by", sa.Text()))
    op.add_column("content_plans", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("content_plans", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("content_plans", sa.Column("stage", sa.Text(), nullable=False, server_default="planned"))
    op.add_column("content_plans", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_content_plan_claim", "content_plans", ["channel_id", "content_type", "status", "created_at"])


def downgrade():
    op.drop_index("ix_content_plan_claim", table_name="content_plans")
    for column in ("updated_at", "stage", "attempts", "lease_expires_at", "claimed_by"):
        op.drop_column("content_plans", column)
