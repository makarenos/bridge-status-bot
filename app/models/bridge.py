"""
Models for bridges and their statuses
Here we store information about bridges, their current status, and audit history.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Boolean, Text, DateTime, Index, JSON, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Bridge(Base):
    """
    Basic information about the bridge
    Here are API endpoints, verification settings, etc.
    """
    __tablename__ = "bridges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    api_endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    backup_endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # links to other tables
    statuses: Mapped[list["BridgeStatus"]] = relationship(
        back_populates="bridge",
        cascade="all, delete-orphan"
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="bridge",
        cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["UserSubscription"]] = relationship(
        back_populates="bridge",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Bridge {self.name}>"


class BridgeStatus(Base):
    """
    Bridge inspection history
    Each inspection = a new entry with results
    """
    __tablename__ = "bridge_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bridge_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bridges.id', ondelete='CASCADE'),
        nullable=False
    )

    # check results
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # UP, DOWN, SLOW, WARNING
    response_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # в миллисекундах
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # additional data specific to each bridge
    # For example, liquidity for Hop, queue size for Optimism
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # connection to the bridge
    bridge: Mapped["Bridge"] = relationship(back_populates="statuses")

    # indexes for quick search
    __table_args__ = (
        Index('idx_bridge_status_time', 'bridge_id', 'checked_at'),
        Index('idx_status_active', 'status', 'checked_at'),
    )

    def __repr__(self):
        return f"<BridgeStatus {self.bridge_id}: {self.status}>"


class Incident(Base):
    """
    Incidents - when a bridge collapses or slows down
    We track when it started, when it ended, and how serious it was.
    """
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bridge_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bridges.id', ondelete='CASCADE'),
        nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # incident status
    status: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVE"
    )  # ACTIVE или RESOLVED

    # how bad things are
    severity: Mapped[str] = mapped_column(
        String(20),
        default="MEDIUM"
    )  # LOW, MEDIUM, HIGH, CRITICAL

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # additional information in JSON
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # connection to the bridge
    bridge: Mapped["Bridge"] = relationship(back_populates="incidents")

    # index for quick search of active incidents
    __table_args__ = (
        Index('idx_active_incidents', 'status', 'started_at'),
    )

    def __repr__(self):
        return f"<Incident {self.title}: {self.status}>"


# import UserSubscription so that connections work
from app.models.user import UserSubscription