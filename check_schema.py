#!/usr/bin/env python
"""Check fundamentals table schema"""

import sys
sys.path.insert(0, '/home/user/stock/src')

from sqlalchemy import inspect, text
from multibagger.database.schema import get_engine

engine = get_engine()
inspector = inspect(engine)

print("Fundamentals table columns:")
for column in inspector.get_columns('fundamentals'):
    print(f"  {column['name']}: {column['type']}")
