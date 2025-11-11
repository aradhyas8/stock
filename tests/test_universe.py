#!/usr/bin/env python3
"""Test script for universe building functionality"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multibagger.config import get_config
from multibagger.data.cache import HttpCache
from multibagger.universe.builder import UniverseBuilder

def main():
    print("Testing universe building...")

    try:
        # Load configuration
        config = get_config()
        print(f"Markets: {config.markets}")
        print(f"Universe config: {config.universe}")

        # Create cache
        cache = HttpCache("data/http_cache.db")

        # Create builder
        builder = UniverseBuilder(config, cache)

        # Test universe info
        print("\nTesting universe info...")
        info = builder.get_universe_info()
        print(f"Config markets: {info['config']['markets']}")
        print(f"Min market cap: {info['config']['min_market_cap']}")

        print("\n✅ Universe module test completed successfully!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
