"""anonymize studies: drop device_model, hide original file names

Revision ID: c2d4f6a8b013
Revises: b7aa56d08f6d
Create Date: 2026-09-25 23:10:00

Исходные имена файлов и модель аппарата могли содержать серийные номера
и прочие идентификаторы. Колонку убираем, имена заменяем на image_N.dcm,
из сохранённого результата ML удаляем всё, кроме modality.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d4f6a8b013"
down_revision: str | Sequence[str] | None = "b7aa56d08f6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("studies", "device_model")
    op.execute(
        """
        UPDATE studies
        SET file_names = (
            SELECT COALESCE(jsonb_agg('image_' || g || '.dcm' ORDER BY g), '[]'::jsonb)
            FROM generate_series(1, jsonb_array_length(file_names)) AS g
        )
        """
    )
    op.execute(
        """
        UPDATE studies
        SET result = jsonb_set(
            result, '{metadata}',
            jsonb_build_object('modality', result->'metadata'->'modality')
        )
        WHERE result ? 'metadata'
        """
    )


def downgrade() -> None:
    # Исходные данные не восстанавливаются — анонимизация необратима намеренно.
    op.add_column("studies", sa.Column("device_model", sa.String(length=255), nullable=True))
