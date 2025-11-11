#!/usr/bin/env python3
"""
UI Service Tests - Basic smoke tests

Verifies that ui_service functions can be called and return expected structure.
"""

import pytest
from datetime import date
from multibagger.ui_service import (
    get_latest_snapshot,
    get_health_summary,
    list_stage_artifacts,
)


def test_get_latest_snapshot():
    """Test get_latest_snapshot returns expected structure."""
    result = get_latest_snapshot()

    assert isinstance(result, dict)
    assert "as_of" in result
    assert "path" in result
    assert "stage_files" in result
    assert "exists" in result

    # Should be bool
    assert isinstance(result["exists"], bool)


def test_get_health_summary():
    """Test get_health_summary with non-existent month."""
    result = get_health_summary("2099-01")  # Future month

    assert isinstance(result, dict)
    assert "status" in result
    assert "checks_run" in result
    assert "report_path" in result
    assert "metrics" in result

    # Should indicate unknown status for non-existent month
    assert result["status"] == "UNKNOWN"
    assert result["checks_run"] is False


def test_list_stage_artifacts():
    """Test list_stage_artifacts with non-existent month."""
    result = list_stage_artifacts("2099-01")

    assert isinstance(result, list)

    # Should return empty list for non-existent month
    assert result == []


def test_list_stage_artifacts_structure():
    """Test that artifacts have expected structure if they exist."""
    # Try with latest snapshot
    latest = get_latest_snapshot()

    if latest["exists"]:
        artifacts = list_stage_artifacts(latest["as_of"])

        if artifacts:
            artifact = artifacts[0]

            # Check structure
            assert "name" in artifact
            assert "path" in artifact
            assert "size_bytes" in artifact
            assert "type" in artifact

            assert isinstance(artifact["name"], str)
            assert isinstance(artifact["size_bytes"], int)
            assert isinstance(artifact["type"], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
