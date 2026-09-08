"""finance_line_embeddings - per-tenant invoice-line suggestion snapshot (SKY-67 C1).

One row per ``(tenant_id, description)`` with a 768-dimension pgvector
embedding of the line's description plus the account it was most often posted
to and a usage count. The table is a snapshot mirror of core-owned invoice
lines maintained exclusively by the ``finance reindex`` CLI (AI_INGEST_TOKEN,
machine-to-machine); no request path writes it. RLS bounds rows to the session
tenant via ``current_tenant_id()`` - same cross-service snapshot idiom as
0012 (SKY-70 inventory embeddings).

``embedding_model``/``embedding_dims`` record which model produced the vector
so future model/dimension upgrades know what must be re-embedded.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _enable_rls(table: str) -> None:
    """Enable RLS and the tenant-isolation policy (0001/0012 convention)."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation_{table} ON {table} "
        "USING (tenant_id = public.current_tenant_id()) "
        "WITH CHECK (tenant_id = public.current_tenant_id())"
    )


def upgrade() -> None:
    op.create_table(
        "ai_finance_line_embeddings",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("description", sa.Text(), primary_key=True, nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False),
        sa.Column("account_code", sa.String(32), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column(
            "times_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column(
            "embedding_dims",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("768"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_ai_finance_line_embeddings_embedding",
        "ai_finance_line_embeddings",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": "100"},
    )
    _enable_rls("ai_finance_line_embeddings")


def downgrade() -> None:
    op.execute("ALTER TABLE ai_finance_line_embeddings DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_ai_finance_line_embeddings "
        "ON ai_finance_line_embeddings"
    )
    op.drop_table("ai_finance_line_embeddings")
