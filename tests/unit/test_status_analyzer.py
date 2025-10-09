"""
Unit tests for status determination logic
Testing the core logic of how we decide if bridge is UP/DOWN/SLOW/WARNING
"""

import pytest
from app.services.status_analyzer import determine_status, calculate_severity


class TestDetermineStatus:
    """Tests for status determination"""

    def test_status_up_fast_response(self):
        """Bridge is UP when response is fast and no issues"""
        status = determine_status(
            response_time=5000,  # 5 seconds
            http_code=200,
            bridge_specific_checks={}
        )
        assert status == "UP"

    def test_status_up_edge_case(self):
        """Bridge is UP at exactly 10s response time"""
        status = determine_status(
            response_time=10000,  # exactly 10s
            http_code=200,
            bridge_specific_checks={}
        )
        assert status == "UP"

    def test_status_slow(self):
        """Bridge is SLOW when response is 10-30s"""
        status = determine_status(
            response_time=15000,  # 15 seconds
            http_code=200,
            bridge_specific_checks={}
        )
        assert status == "SLOW"

    def test_status_slow_edge_case(self):
        """Bridge is SLOW at 29.9s"""
        status = determine_status(
            response_time=29900,
            http_code=200,
            bridge_specific_checks={}
        )
        assert status == "SLOW"

    def test_status_warning_slow_response(self):
        """Bridge is WARNING when response > 30s"""
        status = determine_status(
            response_time=35000,  # 35 seconds
            http_code=200,
            bridge_specific_checks={}
        )
        assert status == "WARNING"

    def test_status_warning_degraded_service(self):
        """Bridge is WARNING when service is degraded"""
        status = determine_status(
            response_time=5000,
            http_code=200,
            bridge_specific_checks={'degraded_service': True}
        )
        assert status == "WARNING"

    def test_status_down_bad_http_code(self):
        """Bridge is DOWN when HTTP code is not 200"""
        status = determine_status(
            response_time=5000,
            http_code=500,
            bridge_specific_checks={}
        )
        assert status == "DOWN"

    def test_status_down_timeout(self):
        """Bridge is DOWN when request times out (None response_time)"""
        status = determine_status(
            response_time=None,
            http_code=200,
            bridge_specific_checks={}
        )
        assert status == "DOWN"

    def test_status_down_critical_failure(self):
        """Bridge is DOWN when critical check fails"""
        status = determine_status(
            response_time=5000,
            http_code=200,
            bridge_specific_checks={'critical_failure': True}
        )
        assert status == "DOWN"

    def test_various_http_codes(self):
        """Test different HTTP error codes all result in DOWN"""
        error_codes = [404, 500, 502, 503, 504]

        for code in error_codes:
            status = determine_status(
                response_time=1000,
                http_code=code,
                bridge_specific_checks={}
            )
            assert status == "DOWN", f"HTTP {code} should be DOWN"


class TestCalculateSeverity:
    """Tests for incident severity calculation"""

    def test_severity_critical_new_down(self):
        """New DOWN status is CRITICAL"""
        severity = calculate_severity(
            status="DOWN",
            previous_status="UP"
        )
        assert severity == "CRITICAL"

    def test_severity_high_down_ongoing(self):
        """Ongoing DOWN is HIGH (we already know about it)"""
        severity = calculate_severity(
            status="DOWN",
            previous_status="DOWN"
        )
        assert severity == "HIGH"

    def test_severity_high_new_warning(self):
        """New WARNING from UP is HIGH"""
        severity = calculate_severity(
            status="WARNING",
            previous_status="UP"
        )
        assert severity == "HIGH"

    def test_severity_medium_ongoing_warning(self):
        """Ongoing WARNING is MEDIUM"""
        severity = calculate_severity(
            status="WARNING",
            previous_status="WARNING"
        )
        assert severity == "MEDIUM"

    def test_severity_medium_new_slow(self):
        """New SLOW status is MEDIUM"""
        severity = calculate_severity(
            status="SLOW",
            previous_status="UP"
        )
        assert severity == "MEDIUM"

    def test_severity_low_ongoing_slow(self):
        """Ongoing SLOW is LOW"""
        severity = calculate_severity(
            status="SLOW",
            previous_status="SLOW"
        )
        assert severity == "LOW"

    def test_severity_low_recovery(self):
        """Recovery to UP is always LOW (good news!)"""
        severity = calculate_severity(
            status="UP",
            previous_status="DOWN"
        )
        assert severity == "LOW"

    def test_severity_no_previous_status(self):
        """Handle case when we don't know previous status"""
        severity = calculate_severity(
            status="DOWN",
            previous_status=None
        )
        assert severity == "CRITICAL"

    def test_severity_warning_degradation(self):
        """WARNING after SLOW is MEDIUM"""
        severity = calculate_severity(
            status="WARNING",
            previous_status="SLOW"
        )
        assert severity == "MEDIUM"