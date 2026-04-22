"""add email and hashed_password to users

Revision ID: 1e070ab96619
Revises: 
Create Date: 2026-04-22 02:14:50.904754

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e070ab96619'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('hashed_password', sa.String(length=255), nullable=True))
    
    # In case there are existing users, we need to populate dummy data or leave it nullable initially. 
    # For now, we update existing rows to dummy values so we can make them NOT NULL.
    op.execute("UPDATE users SET email = CONCAT(user_id, '@legacy.local') WHERE email IS NULL")
    op.execute("UPDATE users SET hashed_password = 'unusable_password' WHERE hashed_password IS NULL")
    
    op.alter_column('users', 'email', existing_type=sa.String(length=255), nullable=False)
    op.alter_column('users', 'hashed_password', existing_type=sa.String(length=255), nullable=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_column('users', 'hashed_password')
    op.drop_column('users', 'email')
