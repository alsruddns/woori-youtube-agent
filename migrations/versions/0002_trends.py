"""Record RSS snapshots without assuming a time window or active status."""
from alembic import op
import sqlalchemy as sa

revision = "0002_trends"
down_revision = "0001_job_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("trend_collections", sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("channel_id", sa.Text(), nullable=False), sa.Column("region", sa.Text(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False), sa.Column("error", sa.Text()))
    op.create_table("trend_observations", sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("collection_id", sa.BigInteger(), sa.ForeignKey("trend_collections.id"), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False), sa.Column("volume_raw", sa.Text()),
        sa.Column("volume_lower_bound", sa.BigInteger()), sa.Column("news_urls", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.Text()))


def downgrade():
    op.drop_table("trend_observations")
    op.drop_table("trend_collections")
