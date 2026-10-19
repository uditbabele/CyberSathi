"""Initial TRACEWEAVE database schema."""
from alembic import op
import sqlalchemy as sa

revision = "20261020_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(40), nullable=False, server_default="investigator"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.String(100), nullable=False, unique=True),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(80), nullable=False, server_default=""),
        sa.Column("source_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_transactions_transaction_id", "transactions", ["transaction_id"], unique=True)
    op.create_index("ix_transactions_source", "transactions", ["source"])
    op.create_index("ix_transactions_target", "transactions", ["target"])
    op.create_index("ix_transactions_timestamp", "transactions", ["timestamp"])
    op.create_index("ix_transaction_source_time", "transactions", ["source", "timestamp"])
    op.create_index("ix_transaction_target_time", "transactions", ["target", "timestamp"])
    op.create_table(
        "complaints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("complaint_id", sa.String(100), nullable=False, unique=True),
        sa.Column("account_id", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("source_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index("ix_complaints_complaint_id", "complaints", ["complaint_id"], unique=True)
    op.create_index("ix_complaints_account_id", "complaints", ["account_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("action", sa.String(150), nullable=False),
        sa.Column("resource", sa.String(250), nullable=False, server_default=""),
        sa.Column("details", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audit_logs_username", "audit_logs", ["username"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

def downgrade():
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_username", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_complaints_account_id", table_name="complaints")
    op.drop_index("ix_complaints_complaint_id", table_name="complaints")
    op.drop_table("complaints")
    op.drop_index("ix_transaction_target_time", table_name="transactions")
    op.drop_index("ix_transaction_source_time", table_name="transactions")
    op.drop_index("ix_transactions_timestamp", table_name="transactions")
    op.drop_index("ix_transactions_target", table_name="transactions")
    op.drop_index("ix_transactions_source", table_name="transactions")
    op.drop_index("ix_transactions_transaction_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
