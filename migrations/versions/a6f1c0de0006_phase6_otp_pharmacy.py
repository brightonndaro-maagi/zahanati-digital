"""phase 6: otp codes, pharmacies, phone as primary identifier

Revision ID: a6f1c0de0006
Revises: 46086f005c8e
"""
from alembic import op
import sqlalchemy as sa

revision = "a6f1c0de0006"
down_revision = "46086f005c8e"
branch_labels = None
depends_on = None


def upgrade():
    # Alembic does not detect CHECK constraint changes, so this part is written by hand.
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", "role IN ('patient','doctor','pharmacy','admin')")
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=True)
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_otp_lookup", "otp_codes", ["phone", "purpose", "created_at"], unique=False)

    op.create_table(
        "pharmacy_profiles",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("license_number", sa.String(length=60), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("approval_status", sa.String(length=10), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.CheckConstraint("approval_status IN ('pending','approved','rejected')", name="ck_pharmacy_approval_status"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("license_number"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_pharmacy_profiles_approval_status", "pharmacy_profiles", ["approval_status"], unique=False)


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM users WHERE role = 'pharmacy'")).scalar():
        raise RuntimeError("Remove pharmacy accounts before downgrading this migration.")
    op.drop_index("ix_pharmacy_profiles_approval_status", table_name="pharmacy_profiles")
    op.drop_table("pharmacy_profiles")
    op.drop_index("ix_otp_lookup", table_name="otp_codes")
    op.drop_table("otp_codes")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", "role IN ('patient','doctor','admin')")
    # users.email / users.password_hash stay nullable: restoring NOT NULL could fail on existing rows.
