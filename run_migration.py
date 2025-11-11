#!/usr/bin/env python
"""Run pending database migrations"""

import sys
sys.path.insert(0, '/home/user/stock/src')

from multibagger.database.migrations import run_migrations

def main():
    print("Running database migrations...")
    # run_migrations expects db_path, not Engine
    applied_count = run_migrations(db_path='data/multibagger.db')
    print(f"✓ Applied {applied_count} migration(s)")
    return 0

if __name__ == '__main__':
    sys.exit(main())
