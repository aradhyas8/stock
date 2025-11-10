#!/usr/bin/env python
"""Backfill forensics data for Stage 2.3 survivors"""

import sys
sys.path.insert(0, '/home/user/stock/src')

from pathlib import Path
from multibagger.config import get_config
from multibagger.data.populate import DataPopulator

def main():
    """Backfill forensics fields for existing survivors"""

    # Check if Stage 2.3 CSV exists
    csv_path = Path('snapshots/2025-11/stage_business_2025-11.csv')

    if not csv_path.exists():
        print(f"❌ CSV not found: {csv_path}")
        print("Run 'screen business --as-of 2025-11' first")
        return 1

    print("=" * 60)
    print("Backfilling Forensics Data for Stage 2.3 Survivors")
    print("=" * 60)

    config = get_config('/home/user/stock/config.yml')
    populator = DataPopulator(config)

    # Populate fundamentals with forensics fields
    stats = populator.populate_from_survivors_csv(
        csv_path=str(csv_path),
        stage_name='Stage 2.3 Business Filter'
    )

    print("\n" + "=" * 60)
    print("✅ Backfill complete!")
    print("=" * 60)

    return 0

if __name__ == '__main__':
    sys.exit(main())
