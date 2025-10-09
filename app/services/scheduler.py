"""
Scheduler for automatic bridge health checks
Uses APScheduler for scheduled tasks
"""

from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot

from app.core.database import async_session_maker
from app.core.redis import redis_client
from app.services.bridge_monitor import BridgeMonitor
from app.services.notification import NotificationService
from app.config import settings
from app.utils.logger import logger


class BridgeScheduler:
    """
    Scheduler for regular bridge health checks
    Supports optional notification sending and WebSocket broadcasting
    """

    def __init__(self, bot: Optional[Bot] = None, websocket_manager=None):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self.bot = bot  # optional Bot instance for sending alerts
        self.websocket_manager = websocket_manager  # for real-time updates

    async def check_bridges_job(self):
        """
        Scheduled task that runs periodically
        Checks all bridges and logs results
        """
        logger.info("Starting scheduled bridge check...")

        try:
            # create new DB session for this task
            async with async_session_maker() as session:

                # create notification service if bot is available
                notification_service = None
                if self.bot:
                    notification_service = NotificationService(
                        bot=self.bot,
                        db_session=session,
                        redis_client=redis_client
                    )

                # create monitor with session_maker (not session!)
                # this way each bridge check can create its own session
                monitor = BridgeMonitor(
                    session_maker=async_session_maker,
                    redis_client=redis_client,
                    notification_service=notification_service,
                    websocket_manager=self.websocket_manager
                )
                await monitor.initialize()

                try:
                    # check all bridges
                    results = await monitor.check_all_bridges()

                    logger.info(
                        f"Scheduled check completed at {datetime.now()}"
                    )

                    return results

                finally:
                    await monitor.close()

        except Exception as e:
            logger.error(f"Error in scheduled bridge check: {e}",
                         exc_info=True)

    def start(self):
        """Start scheduler with configured interval"""

        if self.is_running:
            logger.warning("Scheduler already running")
            return

        # add job with interval from config
        self.scheduler.add_job(
            self.check_bridges_job,
            trigger=IntervalTrigger(seconds=settings.check_interval_seconds),
            id='bridge_health_check',
            name='Check all bridges health',
            replace_existing=True,
            max_instances=1  # don't allow parallel execution
        )

        logger.info(
            f"Scheduler configured: checking every {settings.check_interval_seconds}s"
        )

        if self.bot:
            logger.info("Notifications enabled - will send alerts to users")
        else:
            logger.info("Notifications disabled - bot instance not provided")

        # start scheduler
        self.scheduler.start()
        self.is_running = True

        logger.info("Scheduler started successfully")

    def shutdown(self):
        """Stop scheduler on app shutdown"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Scheduler stopped")

    async def run_immediate_check(self):
        """
        Run check immediately (without waiting for schedule)
        Useful for manual checks or on startup
        """
        logger.info("Running immediate bridge check...")
        return await self.check_bridges_job()


# global scheduler instance - will be initialized with bot in main.py
bridge_scheduler: Optional[BridgeScheduler] = None


def initialize_scheduler(bot: Optional[Bot] = None, websocket_manager=None):
    """
    Initialize global scheduler instance
    Call this from main.py on startup
    """
    global bridge_scheduler
    bridge_scheduler = BridgeScheduler(bot=bot, websocket_manager=websocket_manager)
    return bridge_scheduler