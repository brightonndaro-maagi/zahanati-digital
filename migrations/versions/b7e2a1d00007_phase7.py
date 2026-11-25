"""phase 7: medicines catalogue

Revision ID: b7e2a1d00007
Revises: a6f1c0de0006
"""
from alembic import op
import sqlalchemy as sa

revision = "b7e2a1d00007"
down_revision = "a6f1c0de0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "medicines",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pharmacy_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("generic_name", sa.String(length=150), nullable=True),
        sa.Column("price_tzs", sa.Integer(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("requires_prescription", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("price_tzs > 0", name="ck_medicine_price_positive"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_medicine_stock_not_negative"),
        sa.ForeignKeyConstraint(["pharmacy_id"], ["pharmacy_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medicines_pharmacy_id", "medicines", ["pharmacy_id"], unique=False)
    # one medicine name per pharmacy, ignoring case (functional index, written by hand)
    op.create_index("uq_medicine_pharmacy_name", "medicines", ["pharmacy_id", sa.text("lower(name)")], unique=True)


def downgrade():
    op.drop_index("uq_medicine_pharmacy_name", table_name="medicines")
    op.drop_index("ix_medicines_pharmacy_id", table_name="medicines")
    op.drop_table("medicines")
