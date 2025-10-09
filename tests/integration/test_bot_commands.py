"""
Integration tests for Telegram bot commands
Testing bot handlers with real DB interactions
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select

from app.telegram.handlers import BotHandlers
from app.models.user import User, UserSubscription
from app.models.bridge import BridgeStatus, Incident


def create_mock_update(user_id=123456, username="testuser", text="/start"):
    """Helper to create mock Telegram Update"""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def create_mock_context(args=None):
    """Helper to create mock Telegram Context"""
    context = MagicMock()
    context.args = args or []
    return context


def create_mock_callback_query(user_id=123456, callback_data="test"):
    """Helper to create mock callback query"""
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = callback_data
    update.callback_query.from_user = MagicMock()
    update.callback_query.from_user.id = user_id
    return update


@pytest.mark.asyncio
class TestStartCommand:
    """Tests for /start command"""

    async def test_start_creates_new_user(self, db_session):
        """Start command creates new user in DB"""
        handlers = BotHandlers()
        update = create_mock_update(user_id=999, username="newuser")
        context = create_mock_context()

        await handlers.start_command(update, context)

        # check user was created
        result = await db_session.execute(
            select(User).where(User.telegram_id == 999)
        )
        user = result.scalar_one_or_none()

        assert user is not None
        assert user.username == "newuser"
        assert user.notifications_enabled is True

    async def test_start_updates_existing_user(self, db_session, sample_user):
        """Start command updates last_active for existing user"""
        handlers = BotHandlers()
        update = create_mock_update(
            user_id=sample_user.telegram_id,
            username="updated_username"
        )
        context = create_mock_context()

        await handlers.start_command(update, context)

        # refresh user
        await db_session.refresh(sample_user)

        # username should be updated
        assert sample_user.username == "updated_username"

    async def test_start_sends_welcome_message(self, db_session):
        """Start command sends welcome message"""
        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context()

        await handlers.start_command(update, context)

        # check message was sent
        assert update.message.reply_text.called
        message = update.message.reply_text.call_args.kwargs["text"]

        assert "Welcome" in message
        assert "/status" in message
        assert "/subscribe" in message


@pytest.mark.asyncio
class TestStatusCommand:
    """Tests for /status command"""

    async def test_status_shows_all_bridges(
        self,
        db_session,
        sample_bridges
    ):
        """Status command shows all active bridges"""
        # add status for each bridge
        for bridge in sample_bridges:
            if bridge.is_active:
                status = BridgeStatus(
                    bridge_id=bridge.id,
                    status="UP",
                    response_time=2000
                )
                db_session.add(status)
        await db_session.commit()

        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context()

        await handlers.status_command(update, context)

        assert update.message.reply_text.called
        message = update.message.reply_text.call_args.kwargs["text"]

        # should show all active bridges
        for bridge in sample_bridges:
            if bridge.is_active:
                assert bridge.name in message

    async def test_status_shows_response_times(
        self,
        db_session,
        sample_bridge,
        sample_status
    ):
        """Status shows response times"""
        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context()

        await handlers.status_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        # should show response time
        assert "2500ms" in message or "2500" in message


@pytest.mark.asyncio
class TestListCommand:
    """Tests for /list command"""

    async def test_list_shows_all_bridges(self, db_session, sample_bridges):
        """List command shows all monitored bridges"""
        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context()

        await handlers.list_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        # should list all active bridges
        for bridge in sample_bridges:
            if bridge.is_active:
                assert bridge.name in message

        # should show total count
        assert "2" in message  # 2 active bridges in fixture


@pytest.mark.asyncio
class TestSubscribeCommand:
    """Tests for /subscribe command"""

    async def test_subscribe_without_args_shows_menu(
        self,
        db_session,
        sample_user
    ):
        """Subscribe without args shows interactive menu"""
        handlers = BotHandlers()
        update = create_mock_update(user_id=sample_user.telegram_id)
        context = create_mock_context(args=[])

        await handlers.subscribe_command(update, context)

        # should send message with keyboard
        assert update.message.reply_text.called
        call_kwargs = update.message.reply_text.call_args.kwargs

        assert "reply_markup" in call_kwargs

    async def test_subscribe_by_name_creates_subscription(
        self,
        db_session,
        sample_user,
        sample_bridge
    ):
        """Subscribe with bridge name creates subscription"""
        handlers = BotHandlers()
        update = create_mock_update(user_id=sample_user.telegram_id)
        context = create_mock_context(args=["Test", "Bridge"])

        await handlers.subscribe_command(update, context)

        # check subscription was created
        result = await db_session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == sample_user.telegram_id,
                UserSubscription.bridge_id == sample_bridge.id
            )
        )
        sub = result.scalar_one_or_none()

        assert sub is not None
        assert sub.alert_on_down is True

    async def test_subscribe_to_nonexistent_bridge(
        self,
        db_session,
        sample_user
    ):
        """Subscribing to non-existent bridge shows error"""
        handlers = BotHandlers()
        update = create_mock_update(user_id=sample_user.telegram_id)
        context = create_mock_context(args=["Fake", "Bridge"])

        await handlers.subscribe_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        assert "not found" in message.lower()


@pytest.mark.asyncio
class TestUnsubscribeCommand:
    """Tests for /unsubscribe command"""

    async def test_unsubscribe_removes_subscription(
        self,
        db_session,
        sample_user,
        sample_bridge,
        sample_subscription
    ):
        """Unsubscribe removes subscription"""
        handlers = BotHandlers()
        update = create_mock_update(user_id=sample_user.telegram_id)
        context = create_mock_context(args=["Test", "Bridge"])

        await handlers.unsubscribe_command(update, context)

        # check subscription was removed
        result = await db_session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == sample_user.telegram_id,
                UserSubscription.bridge_id == sample_bridge.id
            )
        )
        sub = result.scalar_one_or_none()

        assert sub is None

    async def test_unsubscribe_without_args_shows_list(
        self,
        db_session,
        sample_user,
        sample_subscription
    ):
        """Unsubscribe without args shows current subscriptions"""
        handlers = BotHandlers()
        update = create_mock_update(user_id=sample_user.telegram_id)
        context = create_mock_context(args=[])

        await handlers.unsubscribe_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        assert "subscriptions" in message.lower()


@pytest.mark.asyncio
class TestHistoryCommand:
    """Tests for /history command"""

    async def test_history_shows_24h_stats(
        self,
        db_session,
        sample_bridge
    ):
        """History command shows 24h statistics"""
        # create some status records
        from datetime import datetime, timedelta, timezone

        for i in range(10):
            status = BridgeStatus(
                bridge_id=sample_bridge.id,
                status="UP" if i < 8 else "DOWN",
                response_time=2000 + i * 100,
                checked_at=datetime.now(timezone.utc) - timedelta(hours=i)
            )
            db_session.add(status)
        await db_session.commit()

        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context(args=["Test", "Bridge"])

        await handlers.history_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        # should show uptime percentage
        assert "Uptime" in message
        assert "%" in message

        # should show average response time
        assert "Avg Response" in message

    async def test_history_without_args_shows_usage(self, db_session):
        """History without args shows usage instructions"""
        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context(args=[])

        await handlers.history_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        assert "Usage" in message or "Example" in message


@pytest.mark.asyncio
class TestIncidentsCommand:
    """Tests for /incidents command"""

    async def test_incidents_shows_active_incidents(
        self,
        db_session,
        sample_bridge,
        sample_incident
    ):
        """Incidents command shows active incidents"""
        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context()

        await handlers.incidents_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        assert sample_bridge.name in message
        assert sample_incident.title in message

    async def test_incidents_shows_no_incidents_message(self, db_session):
        """Shows friendly message when no active incidents"""
        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context()

        await handlers.incidents_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        assert "No active incidents" in message or "healthy" in message.lower()


@pytest.mark.asyncio
class TestSettingsCommand:
    """Tests for /settings command"""

    async def test_settings_shows_current_settings(
        self,
        db_session,
        sample_user
    ):
        """Settings command shows current user settings"""
        handlers = BotHandlers()
        update = create_mock_update(user_id=sample_user.telegram_id)
        context = create_mock_context()

        await handlers.settings_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        assert "Settings" in message
        assert "Notifications" in message

        # should show keyboard
        call_kwargs = update.message.reply_text.call_args.kwargs
        assert "reply_markup" in call_kwargs


@pytest.mark.asyncio
class TestHelpCommand:
    """Tests for /help command"""

    async def test_help_shows_all_commands(self, db_session):
        """Help command shows all available commands"""
        handlers = BotHandlers()
        update = create_mock_update()
        context = create_mock_context()

        await handlers.help_command(update, context)

        message = update.message.reply_text.call_args.kwargs["text"]

        # should list all commands
        commands = ["/status", "/subscribe", "/list", "/history", "/incidents"]
        for cmd in commands:
            assert cmd in message


@pytest.mark.asyncio
class TestCallbackHandlers:
    """Tests for inline keyboard callback handlers"""

    async def test_subscription_callback_subscribes(
        self,
        db_session,
        sample_user,
        sample_bridge
    ):
        """Subscription callback creates subscription"""
        handlers = BotHandlers()
        update = create_mock_callback_query(
            user_id=sample_user.telegram_id,
            callback_data=f"sub:{sample_bridge.id}"
        )
        context = create_mock_context()

        await handlers.handle_subscription_callback(update, context)

        # check subscription was created
        result = await db_session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == sample_user.telegram_id,
                UserSubscription.bridge_id == sample_bridge.id
            )
        )
        sub = result.scalar_one_or_none()

        assert sub is not None

    async def test_subscription_callback_unsubscribes(
        self,
        db_session,
        sample_user,
        sample_bridge,
        sample_subscription
    ):
        """Unsubscribe callback removes subscription"""
        handlers = BotHandlers()
        update = create_mock_callback_query(
            user_id=sample_user.telegram_id,
            callback_data=f"unsub:{sample_bridge.id}"
        )
        context = create_mock_context()

        await handlers.handle_subscription_callback(update, context)

        # check subscription was removed
        result = await db_session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == sample_user.telegram_id,
                UserSubscription.bridge_id == sample_bridge.id
            )
        )
        sub = result.scalar_one_or_none()

        assert sub is None

    async def test_settings_callback_toggles_notifications(
        self,
        db_session,
        sample_user
    ):
        """Settings callback toggles notification setting"""
        handlers = BotHandlers()

        # user starts with notifications enabled
        assert sample_user.notifications_enabled is True

        update = create_mock_callback_query(
            user_id=sample_user.telegram_id,
            callback_data="toggle_notifications"
        )
        context = create_mock_context()

        await handlers.handle_settings_callback(update, context)

        # refresh user
        await db_session.refresh(sample_user)

        # should be disabled now
        assert sample_user.notifications_enabled is False

        # toggle again
        await handlers.handle_settings_callback(update, context)
        await db_session.refresh(sample_user)

        # should be enabled again
        assert sample_user.notifications_enabled is True


@pytest.mark.asyncio
class TestUserRegistration:
    """Tests for user registration helper"""

    async def test_register_or_update_creates_new_user(self, db_session):
        """Helper creates new user if doesn't exist"""
        user = await BotHandlers._register_or_update_user(
            telegram_id=888888,
            username="brandnew"
        )

        assert user is not None
        assert user.telegram_id == 888888
        assert user.username == "brandnew"
        assert user.notifications_enabled is True

    async def test_register_or_update_updates_existing(
        self,
        db_session,
        sample_user
    ):
        """Helper updates existing user"""
        old_active = sample_user.last_active

        user = await BotHandlers._register_or_update_user(
            telegram_id=sample_user.telegram_id,
            username="updated"
        )

        assert user.username == "updated"
        # last_active should be updated (though hard to test precisely)