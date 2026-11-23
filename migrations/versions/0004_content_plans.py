"""Add independent content plans without changing existing jobs or data."""
from alembic import op
import sqlalchemy as sa

revision = "0004_content_plans"
down_revision = "0003_production_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("content_plans",
        sa.Column("plan_id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("collection_id", sa.BigInteger(), sa.ForeignKey("trend_collections.id"), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("topics", sa.JSON(), nullable=False),
        sa.Column("ranking_snapshot", sa.JSON()),
        sa.Column("status", sa.Text(), nullable=False, server_default="planned"),
        sa.Column("script", sa.JSON()), sa.Column("duration_seconds", sa.Float()),
        sa.Column("video_path", sa.Text()), sa.Column("youtube_video_id", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("channel_id", "content_type", "fingerprint", name="uq_content_plan_fingerprint"),
        sa.CheckConstraint("content_type IN ('MAIN_NEWS','SINGLE_SHORT','TOP5_SHORT')", name="ck_content_plan_type"))
    op.create_table("content_type_settings",
        sa.Column("channel_id", sa.Text(), primary_key=True),
        sa.Column("content_type", sa.Text(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("daily_goal", sa.Integer(), nullable=False),
        sa.CheckConstraint("daily_goal >= 0", name="ck_content_daily_goal"))


def downgrade():
    op.drop_table("content_type_settings")
    op.drop_table("content_plans")
