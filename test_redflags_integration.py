#!/usr/bin/env python
"""Integration test for red flags screening"""

import sys
sys.path.insert(0, '/home/user/stock/src')

from multibagger.config import get_config
from multibagger.screens.redflags import screen_redflags

def main():
    """Test the red flags screening pipeline"""
    print("=" * 60)
    print("Red Flags Screening Integration Test")
    print("=" * 60)

    # Load config
    print("\n[1/3] Loading configuration...")
    config = get_config('/home/user/stock/config.yml')
    print(f"✓ Config loaded")

    # Run screening
    print("\n[2/3] Running red flags screening for 2025-11...")
    try:
        result = screen_redflags(
            config=config,
            as_of='2025-11',
            output_dir='snapshots'
        )

        print(f"\n✓ Screening completed successfully!")

        # Display results
        print("\n[3/3] Results Summary:")
        print(f"  Stage: {result.stage_name}")
        print(f"  Input tickers: {result.total_input}")
        print(f"  Survivors: {result.total_survivors} ({result.total_survivors/result.total_input*100:.1f}%)")
        print(f"  Eliminated: {result.total_input - result.total_survivors}")
        print(f"  Runtime: {result.runtime_seconds:.2f} seconds")

        if result.removed_by_rule:
            print(f"\n  Elimination Breakdown:")
            for rule, count in result.removed_by_rule.items():
                print(f"    {rule}: {count} tickers")

        print("\n" + "=" * 60)
        print("✓ Integration test PASSED")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\n✗ Screening failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
