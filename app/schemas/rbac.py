"""Pydantic schemas for roles and permissions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Row-level data scope levels a role can carry (权限重构系列 3/4). See
# app/models/rbac.py Role.data_scope and app/services/data_scope.py.
DATA_SCOPE_PATTERN = r"^(all|tenant|group|self)$"


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    code: str
    description: str | None = None
    is_system: bool = False
    sort_order: int = 0
    data_scope: str = "tenant"
    created_at: datetime | None = None


class RoleLabel(BaseModel):
    """Lightweight role option for dropdowns."""

    id: str
    name: str
    code: str


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    code: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    data_scope: str = Field(default="tenant", pattern=DATA_SCOPE_PATTERN)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int | None = None
    data_scope: str | None = Field(default=None, pattern=DATA_SCOPE_PATTERN)


# ----- role ↔ permission grants (SCD2, scenario ii) -----


class RolePermissionGrant(BaseModel):
    """Grant a single ``(obj, act)`` permission to a role.

    The permission catalogue row is upserted under ``code == "<obj>:<act>"``;
    the grant then points the role at it via a current-state ``role_permissions``
    row and resyncs casbin.
    """

    obj: str = Field(..., min_length=1, max_length=64)
    act: str = Field(..., min_length=1, max_length=32)


class RolePermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str  # role_permissions row id
    role_id: str
    permission_id: str
    obj: str
    act: str
    valid_from: datetime
    valid_to: datetime | None = None


# ----- permission catalogue + aggregated matrix (read-only views) -----


class PermissionItem(BaseModel):
    """A single permission catalogue entry (one ``<obj>:<act>`` unit).

    ``obj``/``act`` are parsed from ``code``; ``obj_label``/``act_label`` carry
    Chinese display names (sourced from ``OBJ_CN``/``ACT_CN``/``MENU_CN`` in
    ``permission_service``) so the frontend renders the matrix without keeping
    its own label map. ``type`` is ``"api"`` (real backend authorization units
    like ``customers:read``) or ``"menu"`` (UX-layer menu visibility like
    ``menu:agents``); the matrix UI groups by it.
    """

    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str  # "<obj>:<act>"
    name: str
    obj: str  # resource part parsed from code
    act: str  # action part parsed from code
    obj_label: str  # Chinese display name for the resource (e.g. "智能体")
    act_label: str  # Chinese display name for the action (e.g. "查看")
    type: str = "api"  # "api" (backend auth) or "menu" (UX visibility)


class PermissionMatrix(BaseModel):
    """Aggregated role × permission matrix for a tenant.

    ``matrix[role_code][permission_code]`` is True when the role currently holds
    that permission (SCD2 current state), False otherwise. Drives the
    permission-matrix UI; never written through this endpoint.
    """

    roles: list[RoleRead]  # all tenant roles
    permissions: list[PermissionItem]  # all tenant permission items
    matrix: dict[str, dict[str, bool]]  # {role_code: {permission_code: granted}}
