"""rename users.last_login -> last_login_at

Во второй миграции колонка получила имя last_login, а в модели поле last_login_at.
Autogenerate переименование не распознаёт (увидел бы drop + add и потерял данные),
поэтому эта миграция написана руками через alter_column.

Revision ID: a1c3e5f70911
Revises: 734fe96e6233
Create Date: 2026-09-25 19:40:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1c3e5f70911"
down_revision: str | Sequence[str] | None = "734fe96e6233"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "last_login", new_column_name="last_login_at")


def downgrade() -> None:
    op.alter_column("users", "last_login_at", new_column_name="last_login")
