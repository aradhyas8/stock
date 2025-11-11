#!/usr/bin/env python3
"""
Phase 7 Smoke Tests - Basic validation that modules load and functions exist

This is a minimal test suite to ensure Phase 7 implementation is structurally sound.
Full integration tests would require extensive fixtures and test data.
"""

import pytest


def test_ops_module_imports():
    """Test that ops module can be imported"""
    from multibagger.ops import (
        check_system_health,
        print_health_report,
        save_health_report,
        rotate_snapshots,
        print_rotation_report,
        save_rotation_report,
        run_monthly,
        run_daily,
    )

    # Verify all functions are callable
    assert callable(check_system_health)
    assert callable(print_health_report)
    assert callable(save_health_report)
    assert callable(rotate_snapshots)
    assert callable(print_rotation_report)
    assert callable(save_rotation_report)
    assert callable(run_monthly)
    assert callable(run_daily)


def test_analytics_module_imports():
    """Test that analytics module can be imported"""
    from multibagger.analytics import (
        compute_analytics,
        generate_reports,
        print_analytics_summary,
    )

    # Verify all functions are callable
    assert callable(compute_analytics)
    assert callable(generate_reports)
    assert callable(print_analytics_summary)


def test_ops_health_structure():
    """Test health check returns expected structure"""
    from multibagger.ops.health import HealthStatus, HealthCheck

    # Create a test health check
    check = HealthCheck(
        name="Test Check",
        status=HealthStatus.GREEN,
        message="Test passed",
        details={"foo": "bar"}
    )

    assert check.name == "Test Check"
    assert check.status == HealthStatus.GREEN
    assert check.message == "Test passed"
    assert check.details == {"foo": "bar"}

    # Test serialization
    check_dict = check.to_dict()
    assert check_dict["name"] == "Test Check"
    assert check_dict["status"] == HealthStatus.GREEN


def test_ops_rotation_candidate_structure():
    """Test rotation candidate structure"""
    from multibagger.ops.rotation import RotationCandidate
    from pathlib import Path

    # Create test candidate
    test_path = Path("/tmp/test-snapshot")
    test_path.mkdir(parents=True, exist_ok=True)

    candidate = RotationCandidate("2024-01", test_path)

    assert candidate.month == "2024-01"
    assert candidate.path == test_path
    assert candidate.can_delete is True
    assert candidate.skip_reason is None

    # Test marking as skipped
    candidate.mark_skip("Test reason")
    assert candidate.can_delete is False
    assert candidate.skip_reason == "Test reason"

    # Cleanup
    test_path.rmdir()


def test_config_has_phase7_sections():
    """Test that config includes ops and analytics sections"""
    from multibagger.config import Config

    config = Config()

    # Verify ops config exists
    ops_config = config.get("ops", {})
    assert "health" in ops_config
    assert "retention" in ops_config

    health_config = ops_config["health"]
    assert "universe_size_min" in health_config
    assert "universe_size_max" in health_config
    assert "research_coverage_min" in health_config

    # Verify analytics config exists
    analytics_config = config.get("analytics", {})
    assert "lookback_months" in analytics_config
    assert "bench_symbols" in analytics_config
    assert "slippage_bps" in analytics_config


def test_rotation_month_format_validation():
    """Test month format validation in rotation"""
    from multibagger.ops.rotation import _is_valid_month_format

    # Valid formats
    assert _is_valid_month_format("2024-01")
    assert _is_valid_month_format("2025-12")

    # Invalid formats
    assert not _is_valid_month_format("2024-13")  # Month > 12
    assert not _is_valid_month_format("2024-00")  # Month < 1
    assert not _is_valid_month_format("202401")   # Missing dash
    assert not _is_valid_month_format("2024-1")   # Single digit month
    assert not _is_valid_month_format("24-01")    # Short year


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
