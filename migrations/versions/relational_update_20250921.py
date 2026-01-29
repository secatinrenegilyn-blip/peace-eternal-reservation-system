"""Add foreign key relationships for Reservation and Deceased

Revision ID: relational_update_20250921
Revises: e2056927a1c8
Create Date: 2025-09-21
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'relational_update_20250921'
down_revision = 'e2056927a1c8'
branch_labels = None
depends_on = None

def upgrade():
    # Add plot_id to Deceased and set as foreign key
    op.add_column('deceased', sa.Column('plot_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_deceased_plot', 'deceased', 'plot', ['plot_id'], ['id'])
    # Remove plot_number from Deceased if exists
    with op.batch_alter_table('deceased') as batch_op:
        batch_op.drop_column('plot_number')
    # Set Reservation.plot_id as foreign key
    op.create_foreign_key('fk_reservation_plot', 'reservation', 'plot', ['plot_id'], ['id'])
    # Remove plot_number from Reservation if exists
    with op.batch_alter_table('reservation') as batch_op:
        batch_op.drop_column('plot_number')

def downgrade():
    # Remove foreign keys and columns
    op.drop_constraint('fk_deceased_plot', 'deceased', type_='foreignkey')
    op.drop_column('deceased', 'plot_id')
    op.drop_constraint('fk_reservation_plot', 'reservation', type_='foreignkey')
    # Re-add plot_number columns
    op.add_column('deceased', sa.Column('plot_number', sa.String(length=50), nullable=True))
    op.add_column('reservation', sa.Column('plot_number', sa.String(length=50), nullable=True))
