"""
Models for bot users and their alert subscriptions
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger, String, Boolean, DateTime, Integer, UniqueConstraint, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    """
    Bot users from Telegram
    Using Telegram ID as primary key since it's unique
    """
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # notification settings
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # when user registered and last active
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()  # auto-updates
    )

    # relationships
    subscriptions: Mapped[list["UserSubscription"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.telegram_id}: {self.username}>"


class UserSubscription(Base):
    """
    User subscriptions to bridge alerts
    Can configure which alert types to receive
    """
    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey('users.telegram_id', ondelete='CASCADE'),
        nullable=False
    )
    bridge_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bridges.id', ondelete='CASCADE'),
        nullable=False
    )

    # alert type settings
    alert_on_down: Mapped[bool] = mapped_column(Boolean, default=True)  # when bridge goes down
    alert_on_slow: Mapped[bool] = mapped_column(Boolean, default=False)  # when it's slow
    alert_on_warning: Mapped[bool] = mapped_column(Boolean, default=True)  # warnings

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # relationships
    user: Mapped["User"] = relationship(back_populates="subscriptions")
    bridge: Mapped["Bridge"] = relationship(back_populates="subscriptions")

    # one user can't subscribe to same bridge twice
    __table_args__ = (
        UniqueConstraint('user_id', 'bridge_id', name='uq_user_bridge'),
    )

    def __repr__(self):
        return f"<Subscription user={self.user_id} bridge={self.bridge_id}>"


# import Bridge so relationships work
from app.models.bridge import Bridge