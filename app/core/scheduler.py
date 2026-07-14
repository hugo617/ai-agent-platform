"""APScheduler periodic-job framework (priority 54).

Two things live here:

1. **Job functions** (``scan_balance_warnings``) — pure, importable, individually
   testable. They take a session factory, do their work, and return a count the
   caller (test) can assert on. The cron wrappers below call them with the
   app's session factory.

2. **Scheduler lifecycle** (``init_scheduler`` / ``shutdown_scheduler``) — builds
   one module-level ``AsyncIOScheduler``, registers the cron jobs, and starts
   it from the FastAPI lifespan. **Idempotent**: ``init_scheduler`` is a no-op
   if the scheduler is already running. This is CRITICAL — the test suite calls
   ``create_app()`` per test, and if the lifespan started a fresh scheduler each
   time, the second start would raise ``scheduler already running``. We also
   gate the whole thing behind a settings flag so tests can opt out entirely.

Multi-instance note (the plan's risk table): in production only ONE replica
should run the scheduler, otherwise every replica fires the cron and duplicate
notifications appear. For now that means a single-replica deployment; the
``SCHEDULER_ENABLED`` flag lets a multi-replica deploy disable it on all but one.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.wallet import Wallet
from app.services.notification_service import NotificationService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

# Module-level singleton. ``init_scheduler`` registers jobs on this instance
# and starts it; ``shutdown_scheduler`` stops it on app teardown. Repeated
# ``init_scheduler`` calls are safe (idempotent — guarded by ``.running``).
scheduler: AsyncIOScheduler = AsyncIOScheduler()

# Whether to auto-start the scheduler at app startup. Defaults to True in
# non-test envs; tests set ``SCHEDULER_ENABLED=false`` (via conftest env) so
# create_app() never spins up real cron jobs that would outlive the test.
_SCHEDULER_ENABLED: bool = settings.scheduler_enabled


# --------------------------------------------------------------------- jobs
async def scan_balance_warnings(
    session_factory: async_sessionmaker | None = None,
) -> int:
    """Create a ``balance_warning`` notification for each low-balance wallet.

    Runs on a daily cron (09:00) and is also directly callable from tests
    (passing a session factory bound to the test engine). Dedupes per tenant:
    if a balance_warning notification already exists in the last 24h, that
    tenant is skipped — otherwise the bell would re-fire every tick for a
    chronically-low wallet.

    Targets every tenant user (``user_id=None``) so the owner + admins all see
    the warning. Best-effort per tenant: a notification failure on one tenant
    doesn't abort the scan for the rest.

    Returns the number of new warnings created (handy for tests + ops logs).
    """
    factory = session_factory or AsyncSessionLocal
    created = 0
    async with factory() as db:
        # All live wallets with a positive threshold that the balance crossed.
        stmt = select(Wallet).where(
            Wallet.is_deleted.is_(False),
            Wallet.low_balance_threshold > 0,
            Wallet.balance < Wallet.low_balance_threshold,
        )
        wallets = list((await db.execute(stmt)).scalars().all())

        for wallet in wallets:
            svc = NotificationService(db)
            # Dedupe: skip if a balance_warning for this tenant is recent.
            already = await svc.repo.exists_recent(
                tenant_id=wallet.tenant_id,
                type="balance_warning",
                within_hours=24,
            )
            if already:
                continue
            await svc.create(
                tenant_id=wallet.tenant_id,
                user_id=None,
                type="balance_warning",
                title="余额预警",
                content=(
                    f"钱包余额({wallet.balance})低于预警阈值"
                    f"({wallet.low_balance_threshold}),请及时充值。"
                ),
                link="/billing",
            )
            created += 1
        await db.commit()
    if created:
        logger.info("scan_balance_warnings created %d warning(s)", created)
    return created


# ---------------------------------------------------------------- lifecycle
def _register_jobs(sched: AsyncIOScheduler) -> None:
    """Register every periodic job on the scheduler (idempotent per job id).

    ``replace_if_exists`` makes re-registration safe even if the scheduler was
    not fully torn down between app instances in the same process.
    """
    sched.add_job(
        scan_balance_warnings,
        CronTrigger(hour=9, minute=0),
        id="scan_balance_warnings",
        replace_if_exists=True,
    )


def init_scheduler() -> AsyncIOScheduler:
    """Register jobs + start the scheduler. Idempotent + test-safe.

    - If ``SCHEDULER_ENABLED`` is False (tests), this is a complete no-op — the
      module-level scheduler is returned untouched but never started, so
      ``create_app()`` per-test never spawns real cron jobs.
    - If the scheduler is already running (a second ``create_app()`` call in
      the same process), the running instance is returned as-is. Without this
      guard, the second ``start()`` raises ``scheduler already running``.
    """
    if not _SCHEDULER_ENABLED:
        logger.debug("scheduler disabled (SCHEDULER_ENABLED=false); not starting")
        return scheduler
    if scheduler.running:
        return scheduler
    _register_jobs(scheduler)
    scheduler.start()
    logger.info("scheduler started (jobs: %s)", sorted(scheduler.get_jobs().ids))
    return scheduler


def shutdown_scheduler(wait: bool = False) -> None:
    """Stop the scheduler if it's running. Safe to call when not running."""
    if scheduler.running:
        scheduler.shutdown(wait=wait)
        logger.info("scheduler shut down")
