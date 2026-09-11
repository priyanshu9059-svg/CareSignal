"""Add revoked_tokens for JWT logout revocation."""
from alembic import op
import sqlalchemy as sa

revision = '0002_revoked_tokens'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'revoked_tokens',
        sa.Column('id', sa.String(length=80), primary_key=True),
        sa.Column('user_id', sa.String(length=80), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

def downgrade():
    op.drop_table('revoked_tokens')
