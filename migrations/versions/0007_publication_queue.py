"""Persist independent private-upload jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0007_publication_queue"
down_revision = "0006_caption_tracks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("publication_jobs",
        sa.Column("publication_id", sa.Text(), primary_key=True),
        sa.Column("plan_id", sa.Text(), sa.ForeignKey("content_plans.plan_id"), nullable=False, unique=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("privacy", sa.Text(), nullable=False, server_default="private"),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("video_sha256", sa.Text(), nullable=False),
        sa.Column("claimed_by", sa.Text()), sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("youtube_video_id", sa.Text()), sa.Column("error", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("privacy='private'", name="ck_publication_private_only"))
    op.create_index("ix_publication_claim", "publication_jobs", ["channel_id", "status", "created_at"])


def downgrade():
    op.drop_index("ix_publication_claim", table_name="publication_jobs")
    op.drop_table("publication_jobs")
