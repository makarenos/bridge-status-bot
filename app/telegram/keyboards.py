# app/telegram/keyboards.py
"""
Inline keyboard builders for bot menus
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bridge import Bridge
from app.models.user import User, UserSubscription


async def build_subscription_keyboard(
        db: AsyncSession,
        user_id: int
) -> InlineKeyboardMarkup:
    """Build keyboard with bridges - shows subscription status"""
    result = await db.execute(
        select(Bridge).where(Bridge.is_active == True).order_by(Bridge.name)
    )
    bridges = result.scalars().all()

    result = await db.execute(
        select(UserSubscription.bridge_id).where(
            UserSubscription.user_id == user_id
        )
    )
    subscribed_ids = set(row[0] for row in result.all())

    buttons = []
    for bridge in bridges:
        if bridge.id in subscribed_ids:
            text = f"✅ {bridge.name}"
            callback = f"unsub:{bridge.id}"
        else:
            text = f"➕ {bridge.name}"
            callback = f"sub:{bridge.id}"

        buttons.append([InlineKeyboardButton(text, callback_data=callback)])

    return InlineKeyboardMarkup(buttons)


def build_settings_keyboard(user: User) -> InlineKeyboardMarkup:
    """Build settings keyboard"""
    toggle_text = "🔕 Disable" if user.notifications_enabled else "🔔 Enable"

    keyboard = [
        [InlineKeyboardButton(
            f"{toggle_text} Notifications",
            callback_data="toggle_notifications"
        )]
    ]

    return InlineKeyboardMarkup(keyboard)