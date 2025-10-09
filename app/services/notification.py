"""
Notification service for sending alerts to subscribed users
Handles rate limiting, user filtering, and retry logic
"""

import asyncio
from typing import List, Optional
from datetime import datetime, timezone

from telegram import Bot
from telegram.error import TelegramError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bridge import Bridge
from app.models.user import User, UserSubscription
from app.core.redis import RedisClient
from app.config import settings
from app.utils.logger import logger


class NotificationService:
    """
    Service for sending Telegram notifications to subscribed users

    Features:
    - Rate limiting to prevent spam (configurable cooldown)
    - User preference filtering (alert_on_down, alert_on_slow, etc)
    - Telegram API rate limiting (0.05s between messages)
    - Retry mechanism for failed sends
    """

    def __init__(self, bot: Bot, db_session: AsyncSession,
                 redis_client: RedisClient):
        self.bot = bot
        self.db = db_session
        self.redis = redis_client
        self.cooldown_minutes = settings.alert_cooldown_minutes

    async def send_bridge_alert(
            self,
            bridge: Bridge,
            new_status: str,
            old_status: Optional[str] = None,
            severity: str = "MEDIUM",
            response_time: Optional[int] = None
    ):
        """
        Send alert to all subscribed users about bridge status change

        Args:
            bridge: Bridge that changed status
            new_status: New status (UP, DOWN, SLOW, WARNING)
            old_status: Previous status (for context)
            severity: Incident severity (LOW, MEDIUM, HIGH, CRITICAL)
            response_time: Response time in milliseconds
        """

        # check rate limit - don't spam same alerts
        rate_key = f"alert:{bridge.id}:{new_status}"
        if await self._is_rate_limited(rate_key):
            logger.info(f"Alert rate limited for {bridge.name}: {new_status}")
            return

        # get users who should receive this alert
        subscribers = await self._get_subscribers(bridge.id, new_status)

        if not subscribers:
            logger.info(
                f"No subscribers for {bridge.name} {new_status} alerts")
            return

        # format the alert message
        message = self._format_alert_message(
            bridge=bridge,
            new_status=new_status,
            old_status=old_status,
            severity=severity,
            response_time=response_time
        )

        # send to all subscribers with rate limiting
        sent_count = 0
        failed_count = 0

        for user in subscribers:
            try:
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=message,
                    parse_mode='HTML'
                )
                sent_count += 1

                # respect Telegram API rate limits
                await asyncio.sleep(0.05)

            except TelegramError as e:
                logger.error(
                    f"Failed to send alert to user {user.telegram_id}: {e}")
                failed_count += 1

                # if user blocked bot or chat not found - could disable notifications
                if "bot was blocked" in str(
                        e).lower() or "chat not found" in str(e).lower():
                    await self._disable_user_notifications(user.telegram_id)

        # set rate limit for this alert type
        await self.redis.setex(
            rate_key,
            self.cooldown_minutes * 60,  # convert to seconds
            "1"
        )

        logger.info(
            f"Alert sent for {bridge.name} ({new_status}): "
            f"{sent_count} delivered, {failed_count} failed"
        )

    async def _is_rate_limited(self, rate_key: str) -> bool:
        """Check if alert is rate limited"""
        return await self.redis.exists(rate_key)

    async def _get_subscribers(
            self,
            bridge_id: int,
            status: str
    ) -> List[User]:
        """
        Get users who should receive alerts for this bridge and status

        Filters by:
        - User has notifications enabled
        - User is subscribed to this bridge
        - User wants alerts for this status type
        """

        # determine which alert preference to check
        alert_field = {
            "DOWN": UserSubscription.alert_on_down,
            "WARNING": UserSubscription.alert_on_warning,
            "SLOW": UserSubscription.alert_on_slow,
        }.get(status, UserSubscription.alert_on_down)

        # query users with proper filtering
        result = await self.db.execute(
            select(User)
                .join(UserSubscription)
                .where(
                User.notifications_enabled == True,
                UserSubscription.bridge_id == bridge_id,
                alert_field == True
            )
        )

        return list(result.scalars().all())

    def _format_alert_message(
            self,
            bridge: Bridge,
            new_status: str,
            old_status: Optional[str],
            severity: str,
            response_time: Optional[int]
    ) -> str:
        """
        Format alert message with emoji and details

        Makes messages visual and easy to scan
        """

        # status emoji
        status_emoji = {
            "UP": "🟢",
            "SLOW": "🟡",
            "WARNING": "⚠️",
            "DOWN": "🔴"
        }.get(new_status, "⚪")

        # severity emoji
        severity_emoji = {
            "LOW": "🟡",
            "MEDIUM": "🟠",
            "HIGH": "🔴",
            "CRITICAL": "🔥"
        }.get(severity, "⚪")

        # build message lines
        lines = [
            f"{status_emoji} <b>ALERT: {bridge.name}</b>",
            f"Status: {new_status}"
        ]

        # add status change if we know previous status
        if old_status and old_status != new_status:
            lines.append(f"Changed from: {old_status}")

        lines.append(f"Severity: {severity_emoji} {severity}")

        # add response time if available
        if response_time is not None:
            lines.append(f"Response time: {response_time}ms")
        elif new_status == "DOWN":
            lines.append("Response: timeout")

        # timestamp
        now = datetime.now(timezone.utc)
        lines.append(f"\nTime: {now.strftime('%H:%M:%S UTC')}")

        # help text
        lines.append("\nUse /status to see all bridges")

        return "\n".join(lines)

    async def _disable_user_notifications(self, telegram_id: int):
        """
        Disable notifications for user who blocked bot
        So we don't keep trying to send them messages
        """
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.notifications_enabled = False
            await self.db.commit()
            logger.info(
                f"Disabled notifications for user {telegram_id} (bot blocked)")

    async def send_recovery_alert(
            self,
            bridge: Bridge,
            downtime_minutes: int
    ):
        """
        Send recovery notification when bridge comes back UP
        This is good news so we want to tell users
        """

        # no rate limiting on recovery alerts - users want to know ASAP
        subscribers = await self._get_subscribers(bridge.id, "UP")

        message = (
            f"🟢 <b>RECOVERED: {bridge.name}</b>\n"
            f"Status: UP\n"
            f"Downtime: {downtime_minutes} minutes\n\n"
            f"Bridge is back to normal operation!"
        )

        sent_count = 0
        for user in subscribers:
            try:
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=message,
                    parse_mode='HTML'
                )
                sent_count += 1
                await asyncio.sleep(0.05)
            except TelegramError as e:
                logger.error(f"Failed to send recovery alert: {e}")

        logger.info(
            f"Recovery alert sent for {bridge.name}: {sent_count} users")