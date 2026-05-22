from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.workers import heartbeat, monthly, nightly, on_demand, weekly_snapshot

settings = get_settings()


class WorkerSettings:
    functions: ClassVar[tuple[object, ...]] = (
        nightly.run_nightly,
        monthly.run_monthly,
        weekly_snapshot.run_weekly_snapshot,
        on_demand.run_on_demand,
        heartbeat.run_heartbeat,
    )
    cron_jobs: ClassVar[tuple[object, ...]] = (
        cron(nightly.run_nightly, hour=2, minute=0),
        cron(monthly.run_monthly, day=1, hour=3, minute=0),
        cron(weekly_snapshot.run_weekly_snapshot, weekday=6, hour=4, minute=0),
        # Hourly heartbeat — exercises the /lookup wire end-to-end against
        # HEARTBEAT_TEST_EMAIL. Skipped at runtime if the env var isn't set,
        # so registering the cron unconditionally is safe.
        cron(heartbeat.run_heartbeat, minute=7),
    )
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
