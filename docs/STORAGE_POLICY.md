# Storage Policy - Phase A

**Version**: 1.0
**Status**: Implemented
**Date**: 2025-11-11

## Overview

The Storage Policy optimizes database storage by routing heavy data (fundamentals & factors) to ephemeral staging tables for non-finalists during screening. Only Top N finalists (confirmed in Research stage) have their data promoted to canonical tables.

This reduces DB size, speeds up screening, and maintains clean canonical data containing only research-validated stocks.

---

## Configuration

**Location**: `config.yml` → `storage` section

```yaml
storage:
  persist_finalists_only: true   # Enable staging-first policy (default: true)
  keep_price_days: 90            # Days of price history to retain (Phase B)
```

**Viewing Current Policy**:
- UI: Sidebar shows "🎯 Storage: Finalists-only" or "💾 Storage: All tickers"
- CLI: Population logs show policy at start

---

## Policy Matrix

| Feature | `persist_finalists_only: false` (Legacy) | `persist_finalists_only: true` (Phase A) |
|---------|------------------------------------------|------------------------------------------|
| **Fundamentals Write** | → `fundamentals` table | → `fundamentals_temp` table |
| **Factors Write** | → `factors` table | → `factors_temp` table |
| **Fundamentals Read** | FROM `fundamentals` | FROM `fundamentals_temp` UNION `fundamentals` (staging-first) |
| **Factors Read** | FROM `factors` | FROM `factors_temp` UNION `factors` (staging-first) |
| **Promotion** | N/A (all data canonical) | Research stage promotes Top N to canonical |
| **DB Growth** | Linear with universe size | Sub-linear (only finalists persist) |
| **Cleanup** | Manual | Phase B auto-purge staging after Research |

---

## Architecture

### Data Flow (persist_finalists_only: true)

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: Data Population                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Universe (5000 tickers)                                        │
│         │                                                        │
│         ↓                                                        │
│  populate.py (writer routing based on policy)                   │
│         │                                                        │
│         ├─────────────→ fundamentals_temp (all 5000)            │
│         └─────────────→ factors_temp (all 5000)                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: Screening                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Screens read from staging-first (UNION with canonical)         │
│         │                                                        │
│         ├─ quality.py   → reads factors_temp ∪ factors          │
│         └─ business.py  → reads fundamentals_temp ∪ fundamentals│
│                                                                  │
│  Survivors: 5000 → 500 → 100 → 30 → 15 finalists               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: Research & Promotion                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  research.py identifies Top 15 finalists                        │
│         │                                                        │
│         ↓                                                        │
│  batch_promote_finalists([ticker1, ticker2, ...])               │
│         │                                                        │
│         ├─────────────→ fundamentals (UPSERT 15 tickers)        │
│         └─────────────→ factors (UPSERT 15 tickers)             │
│                                                                  │
│  Result: Canonical tables contain ONLY validated finalists      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Phase B (Future): Cleanup                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Auto-purge staging tables after Research stage                 │
│  Keep canonical + last N days of prices                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. Writer Routing (populate.py)

**Method**: `DataPopulator._get_target_tables()`

```python
def _get_target_tables(self) -> dict[str, str]:
    if self.persist_finalists_only:
        return {'fundamentals': 'fundamentals_temp', 'factors': 'factors_temp'}
    else:
        return {'fundamentals': 'fundamentals', 'factors': 'factors'}
```

- All writes during population use raw SQL with dynamic table names
- Converts ORM inserts to `text(f"INSERT INTO {table_name} ...")` for routing

### 2. Reader Fallback (quality.py, business.py)

**Pattern**: UNION ALL with priority-based deduplication

```sql
WITH combined AS (
    SELECT *, 1 as priority FROM factors_temp WHERE ...
    UNION ALL
    SELECT *, 2 as priority FROM factors WHERE ...
)
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY ticker_id, as_of_date
        ORDER BY priority ASC
    ) as rn
    FROM combined
) WHERE rn = 1
```

- Staging rows (priority=1) take precedence over canonical (priority=2)
- Single batch SQL query (no per-row loops)
- Transparent to screening logic (same DataFrame output)

### 3. Promotion API (data/promotion.py)

**Functions**:
- `promote_finalist(session, ticker_id, as_of_date)` - Single ticker
- `batch_promote_finalists(session, ticker_ids, as_of_date)` - Batch (preferred)

**SQL Pattern**: `INSERT OR REPLACE INTO`

```sql
INSERT OR REPLACE INTO fundamentals (...)
SELECT ... FROM fundamentals_temp WHERE ticker_id = :ticker_id
```

**Idempotency**: Safe to call multiple times. Second call yields zero new rows (REPLACE updates with same data).

### 4. Research Hook (screens/research.py)

After Top N filtering (max_reports):

```python
if persist_finalists_only and ticker_ids:
    promotion_results = batch_promote_finalists(session, ticker_ids, as_of_date)
    # Log: "✓ Promoted 15 finalists: 75 fundamentals, 15 factors"
```

---

## Usage Examples

### Example 1: Monthly Pipeline with Policy ON

```bash
# config.yml: persist_finalists_only: true

$ python -m multibagger.cli universe build
$ python -m multibagger.cli populate --sample-mode  # Writes to staging
$ python -m multibagger.cli screen fast quality business redflags  # Reads from staging
$ python -m multibagger.cli screen research  # Promotes Top 15 to canonical
```

**Result**:
- `fundamentals_temp`: 5000 rows (all tickers)
- `factors_temp`: 5000 rows (all tickers)
- `fundamentals`: 15 rows (finalists only)
- `factors`: 15 rows (finalists only)

**Storage**: ~99.7% reduction in canonical tables (15 vs 5000)

### Example 2: Legacy Mode (Policy OFF)

```bash
# config.yml: persist_finalists_only: false

$ python -m multibagger.cli populate --sample-mode  # Writes to canonical
$ python -m multibagger.cli screen fast quality business redflags research
```

**Result**:
- `fundamentals_temp`: 0 rows (unused)
- `factors_temp`: 0 rows (unused)
- `fundamentals`: 5000 rows (all tickers)
- `factors`: 5000 rows (all tickers)

**Storage**: No optimization (all data canonical)

### Example 3: Idempotent Promotion

```python
from multibagger.data.promotion import promote_finalist
from multibagger.database.schema import get_engine
from sqlalchemy.orm import Session
from datetime import date

engine = get_engine()
as_of = date(2025, 11, 1)

with Session(engine) as session:
    # First call: moves data
    result1 = promote_finalist(session, ticker_id=123, as_of_date=as_of)
    print(result1)  # PromotionResult(ticker_id=123, fundamentals_rows=5, factors_rows=1)

    # Second call: no change (idempotent)
    result2 = promote_finalist(session, ticker_id=123, as_of_date=as_of)
    print(result2)  # PromotionResult(ticker_id=123, fundamentals_rows=1, factors_rows=1)
    # (SQLite INSERT OR REPLACE always reports 1 row even if replacing)
```

---

## Benefits

### 1. **Storage Efficiency**
- Canonical tables 99.7% smaller (15 vs 5000 rows)
- Staging tables auto-purged after Research (Phase B)
- Prices table trimmed to keep_price_days (Phase B)

### 2. **Performance**
- Smaller canonical tables → faster portfolio queries
- Screening performance unchanged (staging tables indexed same as canonical)
- Batch promotion (single transaction) is fast

### 3. **Data Quality**
- Canonical tables contain only research-validated stocks
- Clear semantic boundary: staging = screening, canonical = research
- Historical snapshots unaffected (CSV/JSON exports remain deterministic)

### 4. **Backwards Compatibility**
- Toggle policy OFF for legacy behavior (no change to outputs)
- Screening math unchanged (same rules, same survivors)
- UI/CLI unchanged (works with both modes)

---

## Testing

### Acceptance Tests

**File**: `tests/test_promotion.py`

Tests validate:
1. `test_promote_finalist_moves_data()` - Data moves from temp → canonical
2. `test_promote_finalist_idempotent()` - Second call yields no duplicates
3. `test_batch_promote_finalists()` - Batch promotion works for multiple tickers

**Status**: Tests written but failing due to DB fixture setup (temp tables not created in test environment). Migration execution in fixture needs work.

### Manual Validation

```bash
# 1. Enable policy
# config.yml: persist_finalists_only: true

# 2. Run full pipeline
python -m multibagger.cli universe build
python -m multibagger.cli populate --sample-mode
python -m multibagger.cli screen fast quality business redflags research

# 3. Verify canonical tables only have finalists
sqlite3 multibagger.db "SELECT COUNT(*) FROM fundamentals;"  # Should be ~15
sqlite3 multibagger.db "SELECT COUNT(*) FROM factors;"  # Should be ~15
sqlite3 multibagger.db "SELECT COUNT(*) FROM fundamentals_temp;"  # Should be ~5000
sqlite3 multibagger.db "SELECT COUNT(*) FROM factors_temp;"  # Should be ~5000
```

---

## Migration Path

### Enabling Policy (Legacy → Phase A)

1. **Backup database**: `cp multibagger.db multibagger.db.backup`
2. **Run migration**: `python database/migrations/20251111_ephemeral_staging.sql`
3. **Update config**: Set `persist_finalists_only: true`
4. **Run pipeline**: Next monthly run will use new policy
5. **Verify**: Check staging tables populated, canonical tables small

**Rollback**: Set `persist_finalists_only: false` in config. Next run uses canonical tables.

### Disabling Policy (Phase A → Legacy)

1. **Update config**: Set `persist_finalists_only: false`
2. **Run populate**: All data goes to canonical tables
3. **Optional**: Drop staging tables (but keep for future use)

**Note**: Disabling policy does NOT delete existing canonical data. Staging tables remain but unused.

---

## Future Enhancements (Phase B)

### Auto-Purge Staging

After Research stage completes:
```python
# Phase B: Auto-purge staging tables
if persist_finalists_only:
    session.execute(text("DELETE FROM fundamentals_temp"))
    session.execute(text("DELETE FROM factors_temp"))
    logger.info("✓ Purged staging tables")
```

### Price Retention Policy

```python
# Keep only recent prices
cutoff_date = as_of_date - timedelta(days=keep_price_days)
session.execute(
    text("DELETE FROM prices WHERE date < :cutoff"),
    {"cutoff": cutoff_date}
)
```

### Monitoring

Add to Ops & Health tab:
- Staging table row counts
- Canonical table row counts
- Storage savings percentage
- Last purge timestamp

---

## FAQ

**Q: Does this change screening outputs (CSV/JSON)?**
A: No. Screening outputs are identical. Only storage location changes.

**Q: What happens if I run Research twice?**
A: Promotion is idempotent. Second run updates same rows (no duplicates).

**Q: Can I disable policy mid-month?**
A: Yes. Set `persist_finalists_only: false` and re-run pipeline. Data goes to canonical.

**Q: Are staging tables backed up in snapshots?**
A: No. Only canonical tables and CSV/JSON outputs are backed up. Staging is ephemeral.

**Q: What if a non-finalist needs historical data later?**
A: Staging tables kept until Phase B purge. After purge, re-fetch from API.

**Q: Does this affect portfolio monitoring?**
A: No. Portfolio reads from canonical (which has finalists). Monitoring unchanged.

---

## References

- **Migration**: `database/migrations/20251111_ephemeral_staging.sql`
- **Models**: `src/multibagger/database/models.py` (FundamentalTemp, FactorTemp)
- **Promotion API**: `src/multibagger/data/promotion.py`
- **Writer Routing**: `src/multibagger/data/populate.py`
- **Reader Fallback**: `src/multibagger/screens/quality.py`, `src/multibagger/screens/business.py`
- **Research Hook**: `src/multibagger/screens/research.py`
- **Tests**: `tests/test_promotion.py`

---

**End of Document**
