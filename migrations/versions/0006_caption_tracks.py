"""Record verified caption tracks without modifying existing publication rows."""
from alembic import op
import sqlalchemy as sa

revision = "0006_caption_tracks"
down_revision = "0005_content_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("caption_tracks",
        sa.Column("caption_id", sa.Text(), primary_key=True),
        sa.Column("plan_id", sa.Text(), sa.ForeignKey("content_plans.plan_id"), nullable=False),
        sa.Column("video_id", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("track_name", sa.Text(), nullable=False),
        sa.Column("srt_path", sa.Text(), nullable=False),
        sa.Column("srt_sha256", sa.Text(), nullable=False),
        sa.Column("timing_method", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_caption_video", "caption_tracks", ["video_id"])


def downgrade():
    op.drop_index("ix_caption_video", table_name="caption_tracks")
    op.drop_table("caption_tracks")
