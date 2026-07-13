"""Pydantic schemas for customer DTOs.

The customer domain has two read shapes, mirroring the two access patterns:

- ``CustomerProfileRead`` — the *store* view: a single tenant's profile with
  the global identity embedded. This is what a store user sees.
- ``CustomerRead`` — the *HQ* (super_admin) view: the global identity with ALL
  store profiles expanded (cross-store aggregation).
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.group import TenantBrief


class CustomerBrief(BaseModel):
    """Minimal global-identity info, embedded in a profile read."""

    id: str
    identity_key: str
    name: str
    gender: str | None = None
    birthday: date | None = None
    avatar: str | None = None


class CustomerProfileBrief(BaseModel):
    """A per-store profile summary, embedded in a cross-store CustomerRead."""

    id: str
    tenant: TenantBrief
    remark: str | None = None
    tags: dict = Field(default_factory=dict)
    status: str
    last_visit_at: datetime | None = None


# ----------------------------------------------------------- store view


class CustomerProfileRead(BaseModel):
    """What a store user sees: their profile + the global identity.

    Tenant isolation is enforced at the repository layer (``tenant_id`` filter),
    so a store never sees another store's profile for the same customer.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    tenant_id: str
    remark: str | None = None
    tags: dict = Field(default_factory=dict)
    status: str
    last_visit_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerBrief


class CustomerProfileCreate(BaseModel):
    """Create a customer in *this* store.

    If ``identity_key`` already exists globally, the existing Customer is reused
    and only a new Profile is created. The global-identity fields (name/gender/
    birthday) are applied to the Customer on create, and kept in sync on update.
    """

    identity_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    gender: str | None = Field(None, max_length=20)
    birthday: date | None = None
    remark: str | None = None
    tags: dict = Field(default_factory=dict)
    status: str = "active"


class CustomerProfileUpdate(BaseModel):
    """Update a store profile.

    Global-identity fields (name/gender/birthday) sync to the Customer; store-
    private fields (remark/tags/status) update only this profile.
    """

    name: str | None = Field(None, min_length=1, max_length=100)
    gender: str | None = Field(None, max_length=20)
    birthday: date | None = None
    remark: str | None = None
    tags: dict | None = None
    status: str | None = Field(None, max_length=20)


# --------------------------------------------------------------- HQ view


class CustomerRead(BaseModel):
    """What super_admin sees: global identity + every store's profile.

    ``profiles`` lists every live CustomerProfile across tenants (cross-store
    aggregation); ``profile_count`` is ``len(profiles)`` for convenience.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    identity_key: str
    name: str
    gender: str | None = None
    birthday: date | None = None
    avatar: str | None = None
    created_at: datetime
    updated_at: datetime
    profiles: list[CustomerProfileBrief] = Field(default_factory=list)
    profile_count: int = 0


# ----------------------------------------------- AI usage attribution
# Token 费用管理系列 3/4 (customer-conversation-link): a customer's aggregate
# AI service consumption — chats attributed to them + the tokens those chats
# consumed. Powers the "AI 服务" dimension on the customer 360 view.


class CustomerUsageRead(BaseModel):
    """Aggregate AI usage attributed to a customer.

    Returned by ``GET /customers/{id}/usage``. Store-scoped for tenant users
    (only this store's service of the customer); global for cross-tenant
    viewers (super_admin / hq_staff). ``conversation_count`` is the number of
    distinct chats tied to the customer; zeros / None mean no attributed usage.
    """

    customer_id: str
    conversation_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float | None = None
    last_active_at: datetime | None = None
