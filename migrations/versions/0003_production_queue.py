"""Add channel-scoped production queue and selection audit."""
from alembic import op
import sqlalchemy as sa

revision = "0003_production_queue"
down_revision = "0002_trends"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("production_jobs",
        sa.Column("job_id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_by", sa.Text()), sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.UniqueConstraint("channel_id", "event_key", name="uq_production_channel_event"))
    op.create_index("ix_production_claim", "production_jobs", ["channel_id", "status", "created_at"])
    op.create_table("topic_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("collection_id", sa.BigInteger(), sa.ForeignKey("trend_collections.id"), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False), sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    op.drop_table("topic_decisions")
    op.drop_index("ix_production_claim", table_name="production_jobs")
    op.drop_table("production_jobs")
