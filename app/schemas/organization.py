"""Pydantic schemas for organizations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    name: str
    code: str | None = None
    path: str | None = None
    parent_id: str | None = None
    leader_id: str | None = None
    status: str = "active"
    sort_order: int = 0
    created_at: datetime | None = None


class OrganizationTreeNode(OrganizationRead):
    """An org node with its children expanded for tree rendering."""

    children: list["OrganizationTreeNode"] = []


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=100)
    parent_id: str | None = None
    leader_id: str | None = None
    sort_order: int = 0


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=100)
    parent_id: str | None = None
    leader_id: str | None = None
    status: str | None = None
    sort_order: int | None = None


OrganizationTreeNode.model_rebuild()
