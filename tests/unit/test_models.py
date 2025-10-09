"""
Unit tests for database models
Testing SQLAlchemy models and relationships
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from app.models.bridge import Bridge, BridgeStatus, Incident
from app.models.user import User, UserSubscription


@pytest.mark.asyncio
class TestBridgeModel:
    """Tests for Bridge model"""

    async def test_create_bridge(self, db_session):
        """Can create new bridge"""
        bridge = Bridge(
            name="New Bridge",
            api_endpoint="https://newbridge.io/api",
            is_active=True
        )
        db_session.add(bridge)
        await db_session.commit()
        await db_session.refresh(bridge)

        assert bridge.id is not None
        assert bridge.name == "New Bridge"
        assert bridge.created_at is not None

    async def test_bridge_unique_name(self, db_session, sample_bridge):
        """Bridge names must be unique"""
        duplicate = Bridge(
            name=sample_bridge.name,  # same name
            api_endpoint="https://different.io/api"
        )
        db_session.add(duplicate)

        with pytest.raises(Exception):  # will raise IntegrityError
            await db_session.commit()

    async def test_bridge_defaults(self, db_session):
        """Bridge has correct default values"""
        bridge = Bridge(
            name="Default Test",
            api_endpoint="https://test.io/api"
        )
        db_session.add(bridge)
        await db_session.commit()
        await db_session.refresh(bridge)

        assert bridge.is_active is True
        assert bridge.check_interval_seconds == 300
        assert bridge.backup_endpoint is None

    async def test_bridge_repr(self, sample_bridge):
        """Bridge __repr__ works"""
        repr_str = repr(sample_bridge)
        assert "Bridge" in repr_str
        assert sample_bridge.name in repr_str


@pytest.mark.asyncio
class TestBridgeStatusModel:
    """Tests for BridgeStatus model"""

    async def test_create_status(self, db_session, sample_bridge):
        """Can create bridge status"""
        status = BridgeStatus(
            bridge_id=sample_bridge.id,
            status="UP",
            response_time=2500,
            extra_data={"test": True}
        )
        db_session.add(status)
        await db_session.commit()
        await db_session.refresh(status)

        assert status.id is not None
        assert status.checked_at is not None

    async def test_status_bridge_relationship(
            self,
            db_session,
            sample_bridge,
            sample_status
    ):
        """Status has relationship to bridge"""
        assert sample_status.bridge is not None
        assert sample_status.bridge.id == sample_bridge.id

    async def test_bridge_cascade_delete_statuses(
            self,
            db_session,
            sample_bridge,
            sample_status
    ):
        """Deleting bridge deletes its statuses"""
        status_id = sample_status.id

        await db_session.delete(sample_bridge)
        await db_session.commit()

        # status should be gone
        result = await db_session.execute(
            select(BridgeStatus).where(BridgeStatus.id == status_id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
class TestIncidentModel:
    """Tests for Incident model"""

    async def test_create_incident(self, db_session, sample_bridge):
        """Can create incident"""
        incident = Incident(
            bridge_id=sample_bridge.id,
            title="Test Incident",
            severity="HIGH",
            status="ACTIVE"
        )
        db_session.add(incident)
        await db_session.commit()
        await db_session.refresh(incident)

        assert incident.id is not None
        assert incident.started_at is not None
        assert incident.resolved_at is None

    async def test_incident_defaults(self, db_session, sample_bridge):
        """Incident has correct defaults"""
        incident = Incident(
            bridge_id=sample_bridge.id,
            title="Test"
        )
        db_session.add(incident)
        await db_session.commit()
        await db_session.refresh(incident)

        assert incident.status == "ACTIVE"
        assert incident.severity == "MEDIUM"

    async def test_resolve_incident(self, db_session, sample_incident):
        """Can resolve incident"""
        sample_incident.status = "RESOLVED"
        sample_incident.resolved_at = datetime.now(timezone.utc)

        await db_session.commit()
        await db_session.refresh(sample_incident)

        assert sample_incident.status == "RESOLVED"
        assert sample_incident.resolved_at is not None


@pytest.mark.asyncio
class TestUserModel:
    """Tests for User model"""

    async def test_create_user(self, db_session):
        """Can create user"""
        user = User(
            telegram_id=999999,
            username="testuser"
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.telegram_id == 999999
        assert user.created_at is not None
        assert user.last_active is not None

    async def test_user_defaults(self, db_session):
        """User has correct defaults"""
        user = User(telegram_id=888888)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.notifications_enabled is True
        assert user.username is None

    async def test_user_primary_key(self, db_session, sample_user):
        """telegram_id is primary key"""
        result = await db_session.execute(
            select(User).where(User.telegram_id == sample_user.telegram_id)
        )
        found_user = result.scalar_one()

        assert found_user.telegram_id == sample_user.telegram_id


@pytest.mark.asyncio
class TestUserSubscriptionModel:
    """Tests for UserSubscription model"""

    async def test_create_subscription(
            self,
            db_session,
            sample_user,
            sample_bridge
    ):
        """Can create subscription"""
        sub = UserSubscription(
            user_id=sample_user.telegram_id,
            bridge_id=sample_bridge.id,
            alert_on_down=True
        )
        db_session.add(sub)
        await db_session.commit()
        await db_session.refresh(sub)

        assert sub.id is not None
        assert sub.created_at is not None

    async def test_subscription_defaults(
            self,
            db_session,
            sample_user,
            sample_bridge
    ):
        """Subscription has correct defaults"""
        sub = UserSubscription(
            user_id=sample_user.telegram_id,
            bridge_id=sample_bridge.id
        )
        db_session.add(sub)
        await db_session.commit()
        await db_session.refresh(sub)

        assert sub.alert_on_down is True
        assert sub.alert_on_slow is False
        assert sub.alert_on_warning is True

    async def test_subscription_unique_constraint(
            self,
            db_session,
            sample_subscription
    ):
        """Can't subscribe to same bridge twice"""
        duplicate = UserSubscription(
            user_id=sample_subscription.user_id,
            bridge_id=sample_subscription.bridge_id
        )
        db_session.add(duplicate)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    async def test_subscription_relationships(
            self,
            db_session,
            sample_subscription,
            sample_user,
            sample_bridge
    ):
        """Subscription has correct relationships"""
        assert sample_subscription.user is not None
        assert sample_subscription.bridge is not None
        assert sample_subscription.user.telegram_id == sample_user.telegram_id
        assert sample_subscription.bridge.id == sample_bridge.id

    async def test_cascade_delete_user(
            self,
            db_session,
            sample_user,
            sample_subscription
    ):
        """Deleting user deletes subscriptions"""
        sub_id = sample_subscription.id

        await db_session.delete(sample_user)
        await db_session.commit()

        # subscription should be gone
        result = await db_session.execute(
            select(UserSubscription).where(UserSubscription.id == sub_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_cascade_delete_bridge(
            self,
            db_session,
            sample_bridge,
            sample_subscription
    ):
        """Deleting bridge deletes subscriptions"""
        sub_id = sample_subscription.id

        await db_session.delete(sample_bridge)
        await db_session.commit()

        # subscription should be gone
        result = await db_session.execute(
            select(UserSubscription).where(UserSubscription.id == sub_id)
        )
        assert result.scalar_one_or_none() is None