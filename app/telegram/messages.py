# app/telegram/messages.py
"""
Message templates and formatters for Telegram bot
All the text that users see comes from here
"""

from datetime import datetime, timezone
from typing import List, Tuple, Optional

from app.models.bridge import Bridge, BridgeStatus


def get_welcome_message() -> str:
    """Welcome message for /start - first thing users see"""
    return """
👋 <b>Welcome to Bridge Status Bot!</b>

I monitor 5 popular cross-chain bridges and notify you about issues in real-time.

<b>Quick Start:</b>
• /status - Check current bridge status
• /subscribe - Get alerts when bridges go down
• /list - See all monitored bridges

<b>Monitored Bridges:</b>
• Stargate (LayerZero)
• Hop Protocol  
• Arbitrum Bridge
• Polygon Bridge
• Optimism Bridge

Ready? Try /status to see how bridges are doing! 🚀
    """.strip()


def format_status_message(
        bridge_statuses: List[Tuple[Bridge, BridgeStatus]]) -> str:
    """
    Format status message showing all bridges
    Makes it nice and readable with emojis and speed indicators
    """
    lines = ["<b>🌉 Bridge Status</b>\n"]

    for bridge, status in bridge_statuses:
        emoji = _get_status_emoji(status.status)

        # make response time human-readable
        if not status.response_time:
            speed = "Not responding"
        elif status.response_time < 1000:
            speed = "⚡ Fast"
        elif status.response_time < 5000:
            speed = "✅ Normal"
        elif status.response_time < 10000:
            speed = "🐌 Slow"
        else:
            speed = "🐢 Very slow"

        # show status or speed depending on what's more important
        if status.status == "UP":
            lines.append(
                f"{emoji} <b>{bridge.name}</b> - {speed} ({status.response_time}ms)")
        else:
            lines.append(f"{emoji} <b>{bridge.name}</b> - {status.status}")
            if status.response_time:
                lines.append(f"   Response: {status.response_time}ms")

    # add timestamp so user knows how fresh the data is
    now = datetime.now(timezone.utc)
    lines.append(f"\n<i>Updated: {now.strftime('%H:%M:%S UTC')}</i>")

    lines.append("\nUse /subscribe to get alerts!")

    return "\n".join(lines)


def _get_status_emoji(status: str) -> str:
    """
    Get emoji for each status type
    Makes messages visual and easy to scan
    """
    return {
        "UP": "🟢",
        "SLOW": "🟡",
        "WARNING": "⚠️",
        "DOWN": "🔴",
        "UNKNOWN": "⚪"
    }.get(status, "⚪")


def format_subscription_success(bridge_name: str, subscribed: bool) -> str:
    """
    Format subscription confirmation message
    Shows users what they just subscribed/unsubscribed to
    """
    if subscribed:
        return f"""
✅ <b>Subscribed to {bridge_name}</b>

You'll receive alerts when this bridge:
• Goes down
• Shows warnings
• Returns to normal

Use /unsubscribe {bridge_name} to stop alerts
        """.strip()
    else:
        return f"""
❌ <b>Unsubscribed from {bridge_name}</b>

You won't receive alerts for this bridge anymore.

Use /subscribe {bridge_name} to re-enable alerts
        """.strip()


def format_help_message() -> str:
    """
    Help message with all commands
    Users see this when they need to figure out what the bot can do
    """
    return """
<b>Bridge Status Bot - Commands</b>

<b>Monitoring:</b>
/status - Current status of all bridges
/list - View all monitored bridges
/history <name> - 24h history for a bridge
/incidents - Active incidents

<b>Subscriptions:</b>
/subscribe [name] - Subscribe to alerts
/unsubscribe [name] - Unsubscribe

<b>Settings:</b>
/settings - Configure notifications
/help - Show this message

<b>Examples:</b>
/subscribe Stargate
/history Hop Protocol
/unsubscribe Arbitrum

Need help? Send /help anytime!
    """.strip()


def format_alert_message(
        bridge_name: str,
        status: str,
        severity: str,
        response_time: Optional[int] = None
) -> str:
    """
    Format alert message when bridge status changes
    This gets sent to subscribed users
    """
    emoji = _get_status_emoji(status)

    # make severity more visible with emojis
    severity_emoji = {
        'LOW': '🟡',
        'MEDIUM': '🟠',
        'HIGH': '🔴',
        'CRITICAL': '🔥'
    }.get(severity, '⚪')

    lines = [
        f"{emoji} <b>ALERT: {bridge_name}</b>",
        f"Status: {status}",
        f"Severity: {severity_emoji} {severity}"
    ]

    if response_time:
        lines.append(f"Response time: {response_time}ms")

    now = datetime.now(timezone.utc)
    lines.append(f"\nTime: {now.strftime('%H:%M:%S UTC')}")

    lines.append("\nUse /status to see all bridges")

    return "\n".join(lines)