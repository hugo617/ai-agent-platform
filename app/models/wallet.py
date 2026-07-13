"""ORM models for the token wallet and its transaction stream.

The wallet is the prepaid balance for one tenant (store). The tenant pays the
platform for a quota of tokens up front (recharge); each successful assistant
turn debits the consumed tokens (charge). A zero balance blocks new chats.

Design (user decision 2026-07-12: prepaid-wallet + model-real-token pricing +
quota transfer, no payment gateway):

- **Balance is an integer token count, not money.** A recharge grants N tokens;
  a charge subtracts the consumed total_tokens. Pricing changes never change
  the balance — the monetary ``cost`` is computed at charge time (a snapshot)
  and stored on ``UsageEvent.cost`` + ``WalletTransaction``, decoupled from the
  balance.
- **One wallet per tenant** (partial unique index on live rows). Soft-deleted
  wallets keep their row but are exempt from uniqueness, mirroring the
  User/Role/Customer convention.
- ``total_recharged`` / ``total_consumed`` are monotonic lifetime counters
  (handy for dashboards); ``balance`` is the live remainder.
- ``WalletTransaction`` is an append-only ledger: every recharge / consume /
  adjust appends one row with the resulting ``balance_after``, so the full
  history of a wallet is reconstructable.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Wallet(Base):
    """The prepaid token balance for one tenant.

    One live wallet per tenant. ``balance`` is debited by ``BillingService.charge``
    (token count) and credited by ``recharge``. ``low_balance_threshold`` is the
    optional alert line (consumed by the notification task, not enforced here).
    """

    __tablename__ = "wallets"
    __table_args__ = (
        # At most one *live* wallet per tenant. Soft-deleted rows are exempt so
        # a wallet can be recreated after deletion. Mirrored PG/SQLite.
        Index(
            "uq_wallets_tenant_active",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Live token balance. Recharge adds; charge subtracts. Integer tokens —
    # money (cost) is a charge-time snapshot stored on transactions/events,
    # never on the balance.
    balance: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_recharged: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_consumed: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    # Optional alert line (notification task consumes it). 0 = disabled.
    low_balance_threshold: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Wallet {self.id} tenant={self.tenant_id} balance={self.balance}>"


class WalletTransaction(Base):
    """An append-only ledger row for one wallet mutation.

    ``type`` values:
      - ``recharge`` — credit (positive amount), balance goes up.
      - ``consume``  — debit (negative amount), balance goes down (one per
        charged assistant turn).
      - ``refund``   — credit reversing a prior consume (reserved; the current
        charge path never refunds, but the slot is here for manual adjustment).
      - ``adjust``   — manual correction by an admin (either sign).

    ``amount`` is signed: positive for credits (recharge/refund), negative for
    debits (consume). ``balance_after`` is the wallet balance immediately
    after this mutation, so the wallet history is fully reconstructable.
    """

    __tablename__ = "wallet_transactions"
    __table_args__ = (
        Index("idx_wallet_transactions_tenant_created", "tenant_id", "created_at"),
        Index("idx_wallet_transactions_wallet_created", "wallet_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    wallet_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # recharge / consume / refund / adjust.
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Signed: +credit / -debit (in tokens).
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    # Optional link to the usage event that triggered a consume (NULL for
    # recharge/adjust). Lets a dashboard join consume → conversation → model.
    usage_event_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("usage_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The model that served a consume (denormalized from UsageEvent for fast
    # ledger filtering without a join). NULL for recharge/adjust.
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The platform user who performed a recharge/adjust (NULL for consume —
    # the chat path has no human operator).
    operator_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<WalletTransaction {self.id} type={self.type} "
            f"amount={self.amount} after={self.balance_after}>"
        )
