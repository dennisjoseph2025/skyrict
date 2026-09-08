"""ai_finance_line_embeddings - per-tenant invoice line-item snapshot (SKY-67 C1).

One row per ``(tenant_id, description)``: a 768-dimension pgvector embedding of
the line's description text plus the account it was most often posted to and
how many times that line has been used across the tenant's invoice history.
Enables "sensible line suggestions" - the invoice dialog embeds the text the
user typed and retrieves the closest past lines, never auto-inserting anything.

The table is a SNAPSHOT MIRROR of core-owned invoice lines maintained only by
the ``finance reindex`` CLI (machine-to-machine, AI_INGEST_TOKEN); no request
path writes it. RLS bounds every row to the session tenant via
``current_tenant_id()``. ``embedding_model``/``embedding_dims`` record which
model produced the vector so model/dimension upgrades know what to re-embed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiFinanceLineEmbeddingModel(Base):
    __tablename__ = "ai_finance_line_embeddings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The account the description was most often posted to (code/name denorm for
    # response payloads; account_id itself carries no FK - accounts may be
    # deactivated after the snapshot was built).
    account_code: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str] = mapped_column(Text, nullable=False)
    times_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    embedding = mapped_column(Vector(768), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_dims: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("768"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
