"""extend user schema + rbac + orgs + sessions + logs

Revision ID: c1d2e3f4a5b6
Revises: ab8c310529f6
Create Date: 2026-07-07 00:00:00.000000+00:00

Adds:
  - users: username/phone/avatar/real_name/password/password_updated_at/
           last_login_at/status/metadata/is_deleted/deleted_at/audit columns.
  - roles, permissions, role_permissions (RBAC display layer over casbin).
  - organizations, user_organizations (org tree + membership).
  - user_sessions, user_login_methods, verification_codes (security).
  - system_logs (audit trail).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

# Match the ORM models exactly: JSONB on Postgres, plain JSON on SQLite (used
# by the test suite). Using a bare ``sa.JSON()`` here would create a JSON column
# on Postgres and leave ``alembic autogenerate`` reporting a permanent diff.
_MetadataJSON = JSONB().with_variant(JSON, "sqlite")


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'ab8c310529f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ users
    op.add_column('users', sa.Column('username', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('real_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('phone', sa.String(length=20), nullable=True))
    op.add_column(
        'users',
        sa.Column('avatar', sa.String(length=255), nullable=False, server_default='/avatars/default.jpg'),
    )
    op.add_column('users', sa.Column('password', sa.String(length=255), nullable=True))
    op.add_column(
        'users',
        sa.Column('password_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'users',
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('metadata', _MetadataJSON, server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('created_by', sa.String(length=128), nullable=True))
    op.add_column('users', sa.Column('updated_by', sa.String(length=128), nullable=True))
    op.add_column(
        'users',
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_phone', 'users', ['phone'])
    op.create_index('ix_users_real_name', 'users', ['real_name'])
    op.create_index('ix_users_is_deleted', 'users', ['is_deleted'])
    op.create_foreign_key(
        'fk_users_created_by', 'users', 'users', ['created_by'], ['id']
    )
    op.create_foreign_key(
        'fk_users_updated_by', 'users', 'users', ['updated_by'], ['id']
    )

    # ------------------------------------------------------------------ roles
    op.create_table(
        'roles',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('code', sa.String(length=100), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_system', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('created_by', sa.String(length=128), nullable=True),
        sa.Column('updated_by', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_roles_tenant_code'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_roles_tenant_name'),
    )
    op.create_index('idx_roles_tenant_id', 'roles', ['tenant_id'])

    # ------------------------------------------------------------ permissions
    op.create_table(
        'permissions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('code', sa.String(length=100), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('type', sa.String(length=20), server_default='api', nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_system', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_permissions_tenant_code'),
    )

    # ----------------------------------------------------- role_permissions
    op.create_table(
        'role_permissions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('role_id', sa.String(length=32), nullable=False),
        sa.Column('permission_id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'role_id', 'permission_id', name='uq_role_permission_tenant'),
    )

    # ------------------------------------------------------------ organizations
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('code', sa.String(length=100), nullable=True),
        sa.Column('path', sa.String(length=255), nullable=True),
        sa.Column('parent_id', sa.String(length=32), nullable=True),
        sa.Column('leader_id', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['leader_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_organizations_tenant_id', 'organizations', ['tenant_id'])
    op.create_index('idx_organizations_parent_id', 'organizations', ['parent_id'])

    # ------------------------------------------------------ user_organizations
    op.create_table(
        'user_organizations',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('organization_id', sa.String(length=32), nullable=False),
        sa.Column('position', sa.String(length=100), nullable=True),
        sa.Column('is_main', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'organization_id', name='uq_user_organization'),
    )
    op.create_index('idx_user_organizations_user_id', 'user_organizations', ['user_id'])
    op.create_index('idx_user_organizations_org_id', 'user_organizations', ['organization_id'])

    # ------------------------------------------------------------- user_sessions
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=True),
        sa.Column('device_type', sa.String(length=20), nullable=True),
        sa.Column('device_name', sa.String(length=200), nullable=True),
        sa.Column('platform', sa.String(length=100), nullable=True),
        sa.Column('token_hash', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('impersonator_id', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['impersonator_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', name='uq_user_sessions_session_id'),
    )
    op.create_index('idx_user_sessions_user_id', 'user_sessions', ['user_id'])
    op.create_index('idx_user_sessions_expires_at', 'user_sessions', ['expires_at'])
    op.create_index('idx_user_sessions_is_active', 'user_sessions', ['is_active'])

    # ------------------------------------------------------- user_login_methods
    op.create_table(
        'user_login_methods',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('login_type', sa.String(length=20), server_default='email', nullable=False),
        sa.Column('identifier', sa.String(length=255), nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'login_type', 'identifier', name='uq_user_login_method'),
    )
    op.create_index('idx_user_login_methods_user_id', 'user_login_methods', ['user_id'])
    op.create_index('idx_user_login_methods_identifier', 'user_login_methods', ['identifier'])

    # --------------------------------------------------------- verification_codes
    op.create_table(
        'verification_codes',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tenant_id', sa.String(length=32), nullable=True),
        sa.Column('ip', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_verification_codes_expires_at', 'verification_codes', ['expires_at'])

    # -------------------------------------------------------------- system_logs
    op.create_table(
        'system_logs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('level', sa.String(length=20), server_default='info', nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('module', sa.String(length=50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', _MetadataJSON, nullable=True),
        sa.Column('resource_type', sa.String(length=100), nullable=True),
        sa.Column('resource_id', sa.String(length=255), nullable=True),
        sa.Column('old_values', _MetadataJSON, nullable=True),
        sa.Column('new_values', _MetadataJSON, nullable=True),
        sa.Column('user_id', sa.String(length=128), nullable=True),
        sa.Column('session_id', sa.String(length=255), nullable=True),
        sa.Column('tenant_id', sa.String(length=32), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('request_id', sa.String(length=100), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_system_logs_resource', 'system_logs', ['resource_type', 'resource_id'])
    op.create_index('idx_system_logs_tenant_id', 'system_logs', ['tenant_id'])
    op.create_index('idx_system_logs_user_id', 'system_logs', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_system_logs_user_id', table_name='system_logs')
    op.drop_index('idx_system_logs_tenant_id', table_name='system_logs')
    op.drop_index('idx_system_logs_resource', table_name='system_logs')
    op.drop_table('system_logs')

    op.drop_index('idx_verification_codes_expires_at', table_name='verification_codes')
    op.drop_table('verification_codes')

    op.drop_index('idx_user_login_methods_identifier', table_name='user_login_methods')
    op.drop_index('idx_user_login_methods_user_id', table_name='user_login_methods')
    op.drop_table('user_login_methods')

    op.drop_index('idx_user_sessions_is_active', table_name='user_sessions')
    op.drop_index('idx_user_sessions_expires_at', table_name='user_sessions')
    op.drop_index('idx_user_sessions_user_id', table_name='user_sessions')
    op.drop_table('user_sessions')

    op.drop_index('idx_user_organizations_org_id', table_name='user_organizations')
    op.drop_index('idx_user_organizations_user_id', table_name='user_organizations')
    op.drop_table('user_organizations')

    op.drop_index('idx_organizations_parent_id', table_name='organizations')
    op.drop_index('idx_organizations_tenant_id', table_name='organizations')
    op.drop_table('organizations')

    op.drop_table('role_permissions')
    op.drop_table('permissions')

    op.drop_index('idx_roles_tenant_id', table_name='roles')
    op.drop_table('roles')

    op.drop_constraint('fk_users_updated_by', 'users', type_='foreignkey')
    op.drop_constraint('fk_users_created_by', 'users', type_='foreignkey')
    op.drop_index('ix_users_is_deleted', table_name='users')
    op.drop_index('ix_users_real_name', table_name='users')
    op.drop_index('ix_users_phone', table_name='users')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_username', table_name='users')
    for col in (
        'updated_at', 'updated_by', 'created_by', 'deleted_at', 'is_deleted',
        'metadata', 'status', 'last_login_at', 'password_updated_at', 'password',
        'avatar', 'phone', 'real_name', 'username',
    ):
        op.drop_column('users', col)
