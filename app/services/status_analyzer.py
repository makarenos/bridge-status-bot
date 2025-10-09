"""
Bridge status determination logic
This is where we figure out if a bridge is UP, DOWN, SLOW or WARNING
"""

from typing import Optional


def determine_status(
        response_time: Optional[int],
        http_code: int,
        bridge_specific_checks: dict
) -> str:
    """
    Figure out bridge status based on various metrics

    Args:
        response_time: response time in milliseconds (None if timeout)
        http_code: HTTP status code
        bridge_specific_checks: bridge-specific checks (liquidity, queue size, etc)

    Returns:
        One of: UP, DOWN, SLOW, WARNING

    Logic breakdown:
        - UP: all good, responds fast (< 10s), HTTP 200
        - SLOW: sluggish (10-30s) but still working
        - WARNING: serious issues (30-60s) or specific problems detected
        - DOWN: not responding, HTTP error, or critical failures
    """

    # non-200 HTTP code = instant DOWN
    if http_code != 200:
        return "DOWN"

    # no response at all (timeout) = also DOWN
    if response_time is None:
        return "DOWN"

    # check bridge-specific problems
    # e.g. if Hop Protocol has no liquidity - that's critical
    if bridge_specific_checks.get('critical_failure'):
        return "DOWN"

    # less critical issues like service degradation
    if bridge_specific_checks.get('degraded_service'):
        return "WARNING"

    # now look at response time
    # > 30 seconds is definitely a problem
    if response_time > 30000:  # 30 seconds in milliseconds
        return "WARNING"

    # 10-30 seconds - slow but functional
    elif response_time > 10000:  # 10 seconds
        return "SLOW"

    # all good, responding quickly
    else:
        return "UP"


def calculate_severity(status: str,
                       previous_status: Optional[str] = None) -> str:
    """
    Figure out how serious the problem is for incident creation

    Args:
        status: current status
        previous_status: previous status (if we know it)

    Returns:
        Severity level: LOW, MEDIUM, HIGH, CRITICAL
    """

    # if status didn't change - not as critical
    if previous_status == status:
        severity_map = {
            "DOWN": "HIGH",  # bridge is down but we already know about it
            "WARNING": "MEDIUM",
            "SLOW": "LOW",
            "UP": "LOW"
        }
        return severity_map.get(status, "MEDIUM")

    # if status changed - see how bad it is
    if status == "DOWN":
        # bridge went down - always critical when first detected
        return "CRITICAL"

    elif status == "WARNING":
        # warning - medium-high severity
        return "HIGH" if previous_status == "UP" else "MEDIUM"

    elif status == "SLOW":
        # slow - low severity
        return "MEDIUM" if previous_status == "UP" else "LOW"

    else:  # UP
        # recovered - low severity (good news)
        return "LOW"