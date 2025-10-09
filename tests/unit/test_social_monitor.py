"""
Unit tests for social monitor stub
Testing that the placeholder/TODO implementation works correctly
"""

import pytest

from app.services.social_monitor import SocialMonitor, \
    initialize_social_monitor


@pytest.mark.asyncio
class TestSocialMonitorStub:
    """
    Tests for social monitor stub
    These tests verify the mock/TODO implementation works
    When Phase 2 is implemented, these tests should be updated
    """

    async def test_init_without_credentials(self):
        """Social monitor can be created without credentials"""
        monitor = SocialMonitor()

        assert monitor.twitter_token is None
        assert monitor.discord_webhook is None

    async def test_init_with_credentials(self):
        """Social monitor can be created with credentials"""
        monitor = SocialMonitor(
            twitter_token="test_token",
            discord_webhook="https://discord.webhook"
        )

        assert monitor.twitter_token == "test_token"
        assert monitor.discord_webhook == "https://discord.webhook"

    async def test_check_twitter_mentions_returns_empty(self):
        """TODO: Twitter mentions returns empty list (stub)"""
        monitor = SocialMonitor()

        mentions = await monitor.check_twitter_mentions("Stargate")

        # stub returns empty list
        assert mentions == []
        assert isinstance(mentions, list)

    async def test_check_discord_reports_returns_empty(self):
        """TODO: Discord reports returns empty list (stub)"""
        monitor = SocialMonitor()

        reports = await monitor.check_discord_reports("Hop Protocol")

        # stub returns empty list
        assert reports == []
        assert isinstance(reports, list)

    async def test_analyze_sentiment_returns_neutral(self):
        """TODO: Sentiment analysis returns neutral (stub)"""
        monitor = SocialMonitor()

        sentiment = await monitor.analyze_sentiment("Bridge is down!")

        # stub returns neutral sentiment
        assert sentiment["neutral"] == 1.0
        assert sentiment["positive"] == 0.0
        assert sentiment["negative"] == 0.0
        assert "urgency_score" in sentiment

    async def test_post_to_discord_returns_false(self):
        """TODO: Discord posting returns False (stub, not implemented)"""
        monitor = SocialMonitor()

        result = await monitor.post_to_discord("Test alert", "CRITICAL")

        # stub returns False (not actually posting)
        assert result is False

    async def test_get_community_sentiment_returns_mock(self):
        """TODO: Community sentiment returns mock data"""
        monitor = SocialMonitor()

        sentiment = await monitor.get_community_sentiment("Arbitrum Bridge",
                                                          hours=12)

        # stub returns mock structure
        assert "bridge" in sentiment
        assert "overall_sentiment" in sentiment
        assert sentiment["mention_count"] == 0
        assert sentiment["trending_issues"] == []

    async def test_correlate_with_status_returns_mock(self):
        """TODO: Status correlation returns mock data"""
        monitor = SocialMonitor()

        correlation = await monitor.correlate_with_status(
            bridge_name="Optimism",
            actual_status="UP",
            social_mentions=[]
        )

        # stub returns mock correlation
        assert "matches_social" in correlation
        assert "early_detection" in correlation
        assert correlation["early_detection"] is False

    async def test_monitor_all_platforms_returns_empty(self):
        """TODO: All platforms monitoring returns empty data"""
        monitor = SocialMonitor()

        data = await monitor.monitor_all_platforms("Polygon Bridge")

        # stub returns empty mentions from all platforms
        assert data["total_mentions"] == 0
        assert data["twitter"] == []
        assert data["discord"] == []
        assert "timestamp" in data

    async def test_initialize_social_monitor_without_creds(self):
        """Initialize without credentials returns None"""
        monitor = initialize_social_monitor()

        # should return None or disabled instance
        assert monitor is None or monitor.twitter_token is None

    async def test_initialize_social_monitor_with_creds(self):
        """Initialize with credentials creates instance"""
        monitor = initialize_social_monitor(
            twitter_token="test",
            discord_webhook="https://test.webhook"
        )

        assert monitor is not None
        assert isinstance(monitor, SocialMonitor)

# TODO Phase 2: When implementing real social monitoring, add these tests:
# - test_twitter_api_integration
# - test_discord_webhook_posting
# - test_sentiment_analysis_accuracy
# - test_real_time_monitoring
# - test_alert_correlation
# - test_false_positive_detection
# - test_early_warning_system