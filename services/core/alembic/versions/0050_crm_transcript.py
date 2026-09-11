"""Add transcript_text to CRM activities (SKY-91).

Adds the raw call/meeting transcript column to ``erp_crm_activities``. The
transcript is user-submitted CRM data about an activity (what was said on a
call); it stays in core alongside the rest of the CRM data plane. Analysis of
that transcript (summary, objection score, next-best-action) is AI product data
the ai-agent owns in its own table (``ai_transcript_analyses``) - core only
ever stores the input, never AI outputs on CRM rows.

Chains after 0049 (SKY-90 wave-2 permissions).

Revision ID: 0050
Revises: 0049
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "erp_crm_activities",
        sa.Column("transcript_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("erp_crm_activities", "transcript_text")
