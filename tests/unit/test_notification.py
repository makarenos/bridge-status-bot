"""
Unit tests for notification service
Testing alert delivery to users
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select

from app.services.notification import NotificationService
from app.models.user import User


@pytest.mark.asyncio
class TestNotificationService:
    """Tests for NotificationService"""

    async def test_send_alert_to_subscribers(
        self,
        db_session,
        mock_redis_client,
        sample_bridge,
        sample_user,
        sample_subscription
    ):
        """Alert is sent to subscribed users"""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        service = NotificationService(mock_bot, db_session, mock_redis_client)

        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="DOWN",
            old_status="UP",
            severity="CRITICAL"
        )

        # verify message was sent
        assert mock_bot.send_message.called
        call_args = mock_bot.send_message.call_args
        assert call_args.kwargs['chat_id'] == sample_user.telegram_id
        assert 'DOWN' in call_args.kwargs['text']

    async def test_rate_limiting_prevents_spam(
        self,
        db_session,
        mock_redis_client,
        sample_bridge,
        sample_user,
        sample_subscription
    ):
        """Rate limiting prevents sending same alert multiple times"""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        service = NotificationService(mock_bot, db_session, mock_redis_client)

        # send first alert
        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="DOWN",
            severity="HIGH"
        )

        assert mock_bot.send_message.call_count == 1

        # try to send same alert again
        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="DOWN",
            severity="HIGH"
        )

        # should still be 1 (rate limited)
        assert mock_bot.send_message.call_count == 1

    async def test_no_alert_if_no_subscribers(
        self,
        db_session,
        mock_redis_client,
        sample_bridge
    ):
        """No alerts sent if nobody is subscribed"""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        service = NotificationService(mock_bot, db_session, mock_redis_client)

        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="DOWN",
            severity="HIGH"
        )

        # no messages sent
        assert not mock_bot.send_message.called

    async def test_filter_by_alert_preferences(
        self,
        db_session,
        mock_redis_client,
        sample_bridge,
        sample_user,
        sample_subscription
    ):
        """Users only get alerts they opted into"""
        # user disabled SLOW alerts
        sample_subscription.alert_on_slow = False
        await db_session.commit()

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        service = NotificationService(mock_bot, db_session, mock_redis_client)

        # send SLOW alert
        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="SLOW",
            severity="LOW"
        )

        # no message sent (user doesn't want SLOW alerts)
        assert not mock_bot.send_message.called

        # but DOWN alert should work
        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="DOWN",
            severity="HIGH"
        )

        assert mock_bot.send_message.called

    async def test_disabled_notifications_skip_user(
        self,
        db_session,
        mock_redis_client,
        sample_bridge,
        sample_user,
        sample_subscription
    ):
        """Users with disabled notifications don't get alerts"""
        # disable notifications for user
        sample_user.notifications_enabled = False
        await db_session.commit()

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        service = NotificationService(mock_bot, db_session, mock_redis_client)

        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="DOWN",
            severity="HIGH"
        )

        # no messages sent
        assert not mock_bot.send_message.called

    async def test_failed_send_disables_blocked_user(
        self,
        db_session,
        mock_redis_client,
        sample_bridge,
        sample_user,
        sample_subscription
    ):
        """User who blocked bot gets notifications disabled"""
        mock_bot = MagicMock()
        # simulate bot being blocked
        mock_bot.send_message = AsyncMock(
            side_effect=Exception("bot was blocked by the user")
        )

        service = NotificationService(mock_bot, db_session, mock_redis_client)

        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="DOWN",
            severity="HIGH"
        )

        # refresh user
        await db_session.refresh(sample_user)

        # notifications should be disabled
        assert sample_user.notifications_enabled is False

    async def test_recovery_alert(
        self,
        db_session,
        mock_redis_client,
        sample_bridge,
        sample_user,
        sample_subscription
    ):
        """Recovery alerts are sent without rate limiting"""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        service = NotificationService(mock_bot, db_session, mock_redis_client)

        await service.send_recovery_alert(
            bridge=sample_bridge,
            downtime_minutes=45
        )

        # message sent
        assert mock_bot.send_message.called
        call_args = mock_bot.send_message.call_args
        assert 'RECOVERED' in call_args.kwargs['text']
        assert '45' in call_args.kwargs['text']

    async def test_message_formatting(
        self,
        db_session,
        mock_redis_client,
        sample_bridge,
        sample_user,
        sample_subscription
    ):
        """Alert messages are properly formatted"""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        service = NotificationService(mock_bot, db_session, mock_redis_client)

        await service.send_bridge_alert(
            bridge=sample_bridge,
            new_status="WARNING",
            old_status="UP",
            severity="MEDIUM",
            response_time=35000
        )

        call_args = mock_bot.send_message.call_args
        message = call_args.kwargs['text']

        # check message contains key info
        assert sample_bridge.name in message
        assert 'WARNING' in message
        assert 'MEDIUM' in message
        assert '35000ms' in message or '35000' in message
        assert 'parse_mode' in call_args.kwargs
        assert call_args.kwargs['parse_mode'] == 'HTML'