"""Prevent queuing the same reviewed file twice for a channel."""
from alembic import op

revision = "0008_publication_dedup"
down_revision = "0007_publication_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_publication_channel_sha", "publication_jobs", ["channel_id", "video_sha256"])


def downgrade():
    op.drop_constraint("uq_publication_channel_sha", "publication_jobs", type_="unique")
