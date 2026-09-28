"""users: snils and esia_oid for Gosuslugi login

Revision ID: d3e5a7c9f124
Revises: c2d4f6a8b013
Create Date: 2026-09-28 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3e5a7c9f124"
down_revision: str | Sequence[str] | None = "c2d4f6a8b013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("snils", sa.String(length=11), nullable=True))
    op.add_column("users", sa.Column("esia_oid", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_users_snils", "users", ["snils"])
    op.create_unique_constraint("uq_users_esia_oid", "users", ["esia_oid"])


def downgrade() -> None:
    op.drop_constraint("uq_users_esia_oid", "users", type_="unique")
    op.drop_constraint("uq_users_snils", "users", type_="unique")
    op.drop_column("users", "esia_oid")
    op.drop_column("users", "snils")
