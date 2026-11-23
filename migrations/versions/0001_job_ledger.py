"""Create durable job, upload, and audit ledgers."""
from alembic import op
import sqlalchemy as sa

revision = "0001_job_ledger"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("jobs",
        sa.Column("job_id", sa.Text(), primary_key=True), sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("job_date", sa.Date(), nullable=False), sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("error", sa.Text()),
        sa.Column("result_json", sa.JSON()), sa.UniqueConstraint("channel_id", "job_date", name="uq_jobs_channel_date"))
    op.create_table("uploads",
        sa.Column("upload_id", sa.Text(), primary_key=True), sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("job_date", sa.Date(), nullable=False), sa.Column("youtube_video_id", sa.Text(), nullable=False),
        sa.Column("privacy_status", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel_id", "job_date", name="uq_uploads_channel_date"))
    op.create_table("audit_events",
        sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=True), sa.Column("job_id", sa.Text()),
        sa.Column("event_type", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False))


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("uploads")
    op.drop_table("jobs")
