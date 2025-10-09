# app/telegram/handlers.py
"""
Telegram bot command handlers
Full implementation of all bot commands
"""

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.user import User, UserSubscription
from app.models.bridge import Bridge, BridgeStatus
from app.telegram.keyboards import (
    build_subscription_keyboard,
    build_settings_keyboard
)
from app.telegram.messages import (
    get_welcome_message,
    format_status_message,
    format_subscription_success,
    format_help_message
)
from app.utils.logger import logger


class BotHandlers:
    """
    All bot command handlers
    Each method handles one command
    """

    def __init__(self):
        # will be set by bot.py on init
        self.engine = None
        self.session_maker = None

    def get_session(self):
        """Create new DB session for this handler"""
        if not self.session_maker:
            raise RuntimeError("Session maker not initialized")
        return self.session_maker()

    async def _register_or_update_user(
            self,
            telegram_id: int,
            username: Optional[str]
    ) -> User:
        """Register new user or update existing one when they interact with bot"""
        async with self.get_session() as db:
            result = await db.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user:
                # update activity timestamp and username if changed
                user.last_active = datetime.now(timezone.utc)
                user.username = username
            else:
                # new user - create with notifications enabled by default
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    notifications_enabled=True
                )
                db.add(user)

            await db.commit()
            await db.refresh(user)
            return user

    async def start_command(self, update: Update,
                            context: ContextTypes.DEFAULT_TYPE):
        """Handle /start - welcome message and register user"""
        user = update.effective_user

        await self._register_or_update_user(user.id, user.username)

        logger.info(f"User {user.id} ({user.username}) started the bot")

        message = get_welcome_message()
        await update.message.reply_text(message, parse_mode='HTML')

    async def status_command(self, update: Update,
                             context: ContextTypes.DEFAULT_TYPE):
        """Handle /status - show current status of all bridges"""
        async with self.get_session() as db:
            # get all active bridges
            result = await db.execute(
                select(Bridge)
                    .where(Bridge.is_active == True)
                    .order_by(Bridge.name)
            )
            bridges = result.scalars().all()

            # get latest status for each bridge
            bridge_statuses = []
            for bridge in bridges:
                status_result = await db.execute(
                    select(BridgeStatus)
                        .where(BridgeStatus.bridge_id == bridge.id)
                        .order_by(BridgeStatus.checked_at.desc())
                        .limit(1)
                )
                latest = status_result.scalar_one_or_none()
                bridge_statuses.append((bridge, latest))

        message = format_status_message(bridge_statuses)
        await update.message.reply_text(message, parse_mode='HTML')

        logger.info(f"User {update.effective_user.id} checked status")

    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list - show all monitored bridges"""
        async with self.get_session() as db:
            result = await db.execute(
                select(Bridge)
                    .where(Bridge.is_active == True)
                    .order_by(Bridge.name)
            )
            bridges = result.scalars().all()

        lines = ["<b>Monitored Bridges:</b>\n"]
        for bridge in bridges:
            lines.append(f"• {bridge.name}")

        lines.append(f"\nTotal: {len(bridges)} bridges")
        lines.append("\nUse /subscribe [bridge name] to get alerts")

        message = "\n".join(lines)
        await update.message.reply_text(message, parse_mode='HTML')

    async def subscribe_command(self, update: Update,
                                context: ContextTypes.DEFAULT_TYPE):
        """Handle /subscribe - subscribe to bridge alerts"""
        user_id = update.effective_user.id

        # no args provided - show interactive menu
        if not context.args:
            async with self.get_session() as db:
                keyboard = await build_subscription_keyboard(db, user_id)

            await update.message.reply_text(
                "Choose a bridge to subscribe:",
                reply_markup=keyboard
            )
            return

        # subscribe to specific bridge by name
        bridge_name = " ".join(context.args)
        success = await self._subscribe_user(user_id, bridge_name)

        if success:
            message = format_subscription_success(bridge_name, subscribed=True)
        else:
            message = f"Bridge '{bridge_name}' not found.\nUse /list to see available bridges."

        await update.message.reply_text(message, parse_mode='HTML')

    async def unsubscribe_command(self, update: Update,
                                  context: ContextTypes.DEFAULT_TYPE):
        """Handle /unsubscribe - unsubscribe from bridge alerts"""
        user_id = update.effective_user.id

        if not context.args:
            # show current subscriptions if no args
            async with self.get_session() as db:
                result = await db.execute(
                    select(UserSubscription, Bridge)
                        .join(Bridge)
                        .where(UserSubscription.user_id == user_id)
                )
                subs = result.all()

            if not subs:
                await update.message.reply_text(
                    "You don't have any subscriptions.\nUse /subscribe to start!"
                )
                return

            lines = ["<b>Your subscriptions:</b>\n"]
            for sub, bridge in subs:
                lines.append(f"• {bridge.name}")

            lines.append("\nUse /unsubscribe <bridge_name> to unsubscribe")
            message = "\n".join(lines)
            await update.message.reply_text(message, parse_mode='HTML')
            return

        # unsubscribe from specific bridge
        bridge_name = " ".join(context.args)
        success = await self._unsubscribe_user(user_id, bridge_name)

        if success:
            message = format_subscription_success(bridge_name,
                                                  subscribed=False)
        else:
            message = f"You are not subscribed to '{bridge_name}'"

        await update.message.reply_text(message, parse_mode='HTML')

    async def history_command(self, update: Update,
                              context: ContextTypes.DEFAULT_TYPE):
        """Handle /history - show 24h history for a bridge"""
        if not context.args:
            await update.message.reply_text(
                "Usage: /history <bridge_name>\nExample: /history Stargate"
            )
            return

        bridge_name = " ".join(context.args)

        async with self.get_session() as db:
            # find bridge by name (case insensitive)
            result = await db.execute(
                select(Bridge).where(Bridge.name.ilike(f"%{bridge_name}%"))
            )
            bridge = result.scalar_one_or_none()

            if not bridge:
                await update.message.reply_text(
                    f"Bridge '{bridge_name}' not found.\nUse /list to see available bridges."
                )
                return

            # get 24h history
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

            result = await db.execute(
                select(BridgeStatus)
                    .where(
                    BridgeStatus.bridge_id == bridge.id,
                    BridgeStatus.checked_at >= cutoff
                )
                    .order_by(BridgeStatus.checked_at.desc())
                    .limit(50)
            )
            statuses = result.scalars().all()

        if not statuses:
            await update.message.reply_text(f"No history for {bridge.name}")
            return

        # calculate stats from history
        total = len(statuses)
        up_count = sum(1 for s in statuses if s.status == "UP")
        down_count = sum(1 for s in statuses if s.status == "DOWN")
        slow_count = sum(1 for s in statuses if s.status == "SLOW")

        uptime_pct = (up_count / total * 100) if total > 0 else 0

        response_times = [s.response_time for s in statuses if s.response_time]
        avg_response = sum(response_times) / len(
            response_times) if response_times else 0

        lines = [
            f"<b>{bridge.name} - 24h History</b>\n",
            f"Uptime: {uptime_pct:.1f}%",
            f"Avg Response: {avg_response:.0f}ms",
            f"\nStatus breakdown:",
            f"🟢 UP: {up_count}",
            f"🟡 SLOW: {slow_count}",
            f"🔴 DOWN: {down_count}",
            f"\nTotal checks: {total}"
        ]

        message = "\n".join(lines)
        await update.message.reply_text(message, parse_mode='HTML')

    async def incidents_command(self, update: Update,
                                context: ContextTypes.DEFAULT_TYPE):
        """Handle /incidents - show active incidents across all bridges"""
        from app.models.bridge import Incident

        async with self.get_session() as db:
            result = await db.execute(
                select(Incident, Bridge)
                    .join(Bridge)
                    .where(Incident.status == "ACTIVE")
                    .order_by(Incident.severity.desc(),
                              Incident.started_at.desc())
            )
            incidents = result.all()

        if not incidents:
            await update.message.reply_text(
                "🟢 No active incidents!\nAll bridges are healthy."
            )
            return

        lines = [f"<b>Active Incidents ({len(incidents)}):</b>\n"]

        for incident, bridge in incidents:
            severity_emoji = {
                'LOW': '🟡',
                'MEDIUM': '🟠',
                'HIGH': '🔴',
                'CRITICAL': '🔥'
            }.get(incident.severity, '⚪')

            duration = datetime.now(timezone.utc) - incident.started_at
            hours = int(duration.total_seconds() / 3600)

            lines.append(
                f"{severity_emoji} <b>{bridge.name}</b> - {incident.severity}\n"
                f"   {incident.title}\n"
                f"   Duration: {hours}h ago"
            )

        message = "\n".join(lines)
        await update.message.reply_text(message, parse_mode='HTML')

    async def settings_command(self, update: Update,
                               context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings - show and update user settings"""
        user_id = update.effective_user.id

        async with self.get_session() as db:
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                await update.message.reply_text("Use /start first")
                return

        keyboard = build_settings_keyboard(user)

        message = (
            "<b>Settings</b>\n\n"
            f"Notifications: {'✅ Enabled' if user.notifications_enabled else '❌ Disabled'}\n\n"
            "Use buttons below to change settings"
        )

        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=keyboard
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help - show available commands and usage"""
        message = format_help_message()
        await update.message.reply_text(message, parse_mode='HTML')

    # Callback query handlers for inline buttons

    async def handle_subscription_callback(self, update: Update,
                                           context: ContextTypes.DEFAULT_TYPE):
        """Handle subscription button clicks from inline keyboard"""
        query = update.callback_query
        await query.answer()

        action, bridge_id = query.data.split(":")
        bridge_id = int(bridge_id)
        user_id = query.from_user.id

        async with self.get_session() as db:
            result = await db.execute(
                select(Bridge).where(Bridge.id == bridge_id)
            )
            bridge = result.scalar_one_or_none()

            if not bridge:
                await query.edit_message_text("Bridge not found")
                return

            if action == "sub":
                await self._subscribe_user_by_id(user_id, bridge_id)
                message = format_subscription_success(bridge.name,
                                                      subscribed=True)
            else:
                await self._unsubscribe_user_by_id(user_id, bridge_id)
                message = format_subscription_success(bridge.name,
                                                      subscribed=False)

        await query.edit_message_text(message, parse_mode='HTML')

    async def handle_settings_callback(self, update: Update,
                                       context: ContextTypes.DEFAULT_TYPE):
        """Handle settings button clicks from inline keyboard"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id

        if query.data == "toggle_notifications":
            async with self.get_session() as db:
                result = await db.execute(
                    select(User).where(User.telegram_id == user_id)
                )
                user = result.scalar_one()

                # toggle notification setting
                user.notifications_enabled = not user.notifications_enabled
                await db.commit()
                await db.refresh(user)

                keyboard = build_settings_keyboard(user)

                message = (
                    "<b>Settings</b>\n\n"
                    f"Notifications: {'✅ Enabled' if user.notifications_enabled else '❌ Disabled'}\n\n"
                    "Use buttons below to change settings"
                )

                await query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard
                )

    # Helper methods for subscriptions

    async def _subscribe_user(self, user_id: int, bridge_name: str) -> bool:
        """Subscribe user by bridge name (case insensitive search)"""
        async with self.get_session() as db:
            result = await db.execute(
                select(Bridge).where(Bridge.name.ilike(f"%{bridge_name}%"))
            )
            bridge = result.scalar_one_or_none()

            if not bridge:
                return False

            return await self._subscribe_user_by_id(user_id, bridge.id)

    async def _subscribe_user_by_id(self, user_id: int, bridge_id: int) -> bool:
        """Subscribe user by bridge ID"""
        async with self.get_session() as db:
            # check if already subscribed
            result = await db.execute(
                select(UserSubscription).where(
                    UserSubscription.user_id == user_id,
                    UserSubscription.bridge_id == bridge_id
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                return True  # already subscribed, that's ok

            # create new subscription with default settings
            sub = UserSubscription(
                user_id=user_id,
                bridge_id=bridge_id,
                alert_on_down=True,  # always alert on DOWN
                alert_on_slow=False,  # don't spam for slow
                alert_on_warning=True  # alert on warnings
            )
            db.add(sub)
            await db.commit()

            logger.info(f"User {user_id} subscribed to bridge {bridge_id}")
            return True

    async def _unsubscribe_user(self, user_id: int, bridge_name: str) -> bool:
        """Unsubscribe user by bridge name"""
        async with self.get_session() as db:
            result = await db.execute(
                select(Bridge).where(Bridge.name.ilike(f"%{bridge_name}%"))
            )
            bridge = result.scalar_one_or_none()

            if not bridge:
                return False

            return await self._unsubscribe_user_by_id(user_id, bridge.id)

    async def _unsubscribe_user_by_id(self, user_id: int, bridge_id: int) -> bool:
        """Unsubscribe user by bridge ID"""
        async with self.get_session() as db:
            result = await db.execute(
                select(UserSubscription).where(
                    UserSubscription.user_id == user_id,
                    UserSubscription.bridge_id == bridge_id
                )
            )
            sub = result.scalar_one_or_none()

            if not sub:
                return False  # wasn't subscribed

            await db.delete(sub)
            await db.commit()

            logger.info(f"User {user_id} unsubscribed from bridge {bridge_id}")
            return True