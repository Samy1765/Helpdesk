"""knowledge documents: last reviewed date

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('knowledge_documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_reviewed', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('knowledge_documents', schema=None) as batch_op:
        batch_op.drop_column('last_reviewed')
