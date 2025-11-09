#!/usr/bin/env python3
"""Test script for data CLI commands"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from typer.testing import CliRunner
from multibagger.cli.main import app

def test_data_commands():
    runner = CliRunner()

    print("Testing data subcommand help...")
    result = runner.invoke(app, ['data', '--help'])
    print("Exit code:", result.exit_code)
    print("Output:", result.stdout)
    print()

    print("Testing data warm command help...")
    result = runner.invoke(app, ['data', 'warm', '--help'])
    print("Exit code:", result.exit_code)
    print("Output:", result.stdout)
    print()

    print("Testing data stats command help...")
    result = runner.invoke(app, ['data', 'stats', '--help'])
    print("Exit code:", result.exit_code)
    print("Output:", result.stdout)
    print()

    print("Testing data check command...")
    result = runner.invoke(app, ['data', 'check'])
    print("Exit code:", result.exit_code)
    print("Output:", result.stdout)
    print()

if __name__ == "__main__":
    test_data_commands()
