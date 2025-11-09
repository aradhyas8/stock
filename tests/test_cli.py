"""Tests for CLI interface"""

from typer.testing import CliRunner

from multibagger.cli.main import app

runner = CliRunner()


def test_version_command():
    """Test version command returns expected output"""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Multi-Bagger Research System" in result.stdout
    assert "Version: 0.1.0" in result.stdout


def test_status_command():
    """Test status command runs without error"""
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "System Status" in result.stdout


def test_monthly_dry_run():
    """Test monthly command in dry run mode"""
    result = runner.invoke(app, ["monthly", "--dry-run"])
    assert result.exit_code == 0
    assert "Monthly Multi-Bagger Hunt" in result.stdout
    assert "DRY RUN mode" in result.stdout


def test_monitor_placeholder():
    """Test monitor command placeholder"""
    result = runner.invoke(app, ["monitor"])
    assert result.exit_code == 0
    assert "Portfolio Monitoring" in result.stdout


def test_universe_placeholder():
    """Test universe command placeholder"""
    result = runner.invoke(app, ["universe", "info"])
    assert result.exit_code == 0
    assert "Stock Universe Management" in result.stdout


def test_screen_placeholder():
    """Test screen command placeholder"""
    result = runner.invoke(app, ["screen"])
    assert result.exit_code == 0
    assert "Stock Screening" in result.stdout


def test_help():
    """Test help command"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Multi-Bagger Research System" in result.stdout
