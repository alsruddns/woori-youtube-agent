"""Store actual YouTube Data API video statistics snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0010_video_statistics"
down_revision = "0009_trend_groups"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("video_statistics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.Text(), sa.ForeignKey("content_plans.plan_id"), nullable=False),
        sa.Column("video_id", sa.Text(), nullable=False),
        sa.Column("view_count", sa.BigInteger()), sa.Column("like_count", sa.BigInteger()),
        sa.Column("comment_count", sa.BigInteger()),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_video_statistics_plan_time", "video_statistics", ["plan_id", "collected_at"])


def downgrade():
    op.drop_index("ix_video_statistics_plan_time", table_name="video_statistics")
    op.drop_table("video_statistics")
