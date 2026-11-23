"""Record evidence-based, unreviewed trend grouping candidates."""
from alembic import op
import sqlalchemy as sa

revision = "0009_trend_groups"
down_revision = "0008_publication_dedup"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("trend_group_candidates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("collection_id", sa.BigInteger(), sa.ForeignKey("trend_collections.id"), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("shared_urls", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="unreviewed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("collection_id", "fingerprint", name="uq_trend_group_snapshot"))


def downgrade():
    op.drop_table("trend_group_candidates")
