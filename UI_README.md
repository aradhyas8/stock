# Multi-Bagger Research System - UI Documentation

Streamlit web interface for the Multi-Bagger Research System.

## Overview

Single-file tabbed UI that provides a clean interface for:
- Running monthly/daily workflows
- Previewing research results
- Reconciling portfolio holdings
- Monitoring positions
- Computing performance analytics
- System health checks
- Snapshot management

**Key Principles:**
- ✅ Calls only the `ui_service` layer (no direct core module imports)
- ✅ All actions require explicit `as_of` / `date` parameters (deterministic)
- ✅ No business logic in UI (only display and service calls)
- ✅ Graceful error handling (no crashes)

---

## Installation

### 1. Install UI Dependencies

```bash
# Using uv (recommended)
uv pip install -r requirements-ui.txt

# Or using pip
pip install -r requirements-ui.txt
```

### 2. Verify Installation

```bash
streamlit --version
```

---

## Running the UI

### Basic Usage

From the project root:

```bash
uv run streamlit run ui/app.py
```

Or with regular Python:

```bash
streamlit run ui/app.py
```

The UI will open in your default browser at `http://localhost:8501`.

### Configuration

The UI reads from `config.yml` in the project root. Key settings:

```yaml
# Database path (default: multibagger.db)
database:
  path: "multibagger.db"

# Snapshot directory (default: snapshots/)
# Set via UI sidebar or config

# Data sources (displayed in sidebar status)
data:
  sources:
    yfinance:
      enabled: true
    alpha_vantage:
      enabled: false
```

### Environment Variables

For API keys (not displayed in UI):

```bash
# Create .env file in project root
echo "ALPHA_VANTAGE_API_KEY=your_key_here" >> .env
```

---

## UI Layout

### Sidebar (Global Controls)

Always visible, contains:

- **📅 As-of Month (YYYY-MM)**: Month for pipeline operations (default: latest snapshot)
- **📆 Check Date**: Date for monitoring/price checks (default: today)
- **📁 Output Directory**: Directory for outputs (default: `snapshots/`)
- **🔍 Dry-Run Mode**: Preview actions without executing

**Status Panel:**
- 💾 Database status and path
- 📂 Latest snapshot and file count
- 🏥 Health status (🟢/🟡/🔴)
- 🔌 Enabled data sources

### Tab 1: Dashboard

Quick overview of system state:
- Latest snapshot metrics
- Health status
- Artifact counts
- Quick links to stage outputs

### Tab 2: Run Pipeline

Execute workflows:

**Monthly Pipeline:**
- Universe → Screens → Red Flags → Research → Portfolio
- Shows metrics and generated artifacts
- Respects dry-run mode

**Daily Monitoring:**
- Checks portfolio positions for alerts
- Generates alert reports
- Shows signal types (STOP_LOSS, NEAR_TARGET, THESIS_RISK)

### Tab 3: Research

Browse research results:
- Filter by min upside %, sector, red-flag status
- View all candidates in table
- Download CSV/JSON

### Tab 4: Portfolio

**Sub-tab 1: Reconcile Holdings**
- Upload holdings file (CSV/JSON)
- Run reconciliation vs model
- View recommended actions (BUY/SELL/TRIM/ADD/HOLD)
- Option to persist to database

**Sub-tab 2: Show Saved Portfolio**
- Load portfolio from database for selected `as_of`
- View positions with weights
- View action history

### Tab 5: Monitoring

Run daily monitoring:
- Input check date (defaults to today)
- View alerts table with color-coded signals
- Download alerts CSV/JSON

### Tab 6: Analytics

Compute performance metrics:
- Set lookback window (default: 36 months)
- Specify benchmark symbols (default: SPY)
- View summary metrics (CAGR, vol, Sharpe, Calmar, max DD)
- View alpha/beta/R² vs benchmark
- View top contributors/detractors
- Download reports (JSON/Markdown)

### Tab 7: Ops & Health

**Sub-tab 1: Health Checks**
- Run system validation
- View status table (8 checks)
- See overall status (🟢/🟡/🔴)
- Access detailed metrics JSON

**Sub-tab 2: Snapshot Rotation**
- Preview old snapshots for deletion
- Set keep policy (default: 12 months)
- Dry-run by default (safety)
- Requires typing "DELETE" to execute

---

## Determinism & Observability

### Deterministic Outputs

Every action uses explicit parameters:
- `as_of` (YYYY-MM): Month for pipeline operations
- `date` (YYYY-MM-DD): Date for monitoring/price checks

No wall-clock timestamps leak into filenames. Outputs are stable and reproducible.

### Observability

After each action, the UI displays:
- ✅ Success/failure status
- 📊 Metrics (JSON)
- 📂 Generated artifacts (paths)
- ⚠️ Warnings (if any)

Logs are persisted to files in `snapshots/{as_of}/logs/` and displayed in UI.

---

## Error Handling

The UI never crashes. Instead:

- **Missing artifacts**: Shows friendly message with suggestion (e.g., "Run Research stage first")
- **Empty DB tables**: Suggests prior stage to run
- **Permission errors**: Shows path and recommendations
- **Exceptions**: Displays error class and message in `st.error()` box

All errors are logged and surfaced in the UI's "warnings" sections.

---

## File Upload Formats

### Holdings File (Portfolio Reconciliation)

**CSV Format:**
```csv
symbol,shares,entry_price
AAPL,100,150.00
MSFT,50,300.00
```

**JSON Format:**
```json
[
  {"symbol": "AAPL", "shares": 100, "entry_price": 150.00},
  {"symbol": "MSFT", "shares": 50, "entry_price": 300.00}
]
```

---

## Troubleshooting

### UI won't start

```bash
# Check Streamlit installation
streamlit --version

# Reinstall if needed
uv pip install --force-reinstall streamlit
```

### "No snapshots found"

Run the monthly pipeline first:
```bash
uv run python -m multibagger.cli.main screen all --as-of 2025-11
```

### Database errors

Ensure database exists and is initialized:
```bash
uv run python -m multibagger.cli.main db init
```

### Config not loading

Ensure `config.yml` exists in project root (copy from `config.example.yml` if needed):
```bash
cp config.example.yml config.yml
```

---

## Architecture

```
UI (Streamlit)
    ↓
ui_service (facade)
    ↓
core modules (ops, analytics, portfolio, screens, monitor)
    ↓
DB/snapshots
    ↓
ui_service returns (DataFrames, dicts, paths)
    ↓
UI renders (tables, charts, downloads)
```

**Key Files:**
- `ui/app.py` - Streamlit UI (single file)
- `src/multibagger/ui_service/service.py` - Service layer facade
- `src/multibagger/ui_service/__init__.py` - Exports

---

## Performance Tips

### Caching

The UI uses `st.cache_data` sparingly to cache read-only rendering:
- Invalidated on `as_of` / `date` changes
- No caching of mutable operations

### Long-Running Operations

For operations that might take time:
- Dry-run mode allows previewing without full execution
- Spinners show progress
- Logs are streamed to collapsible text areas

### Large Tables

Tables use `use_container_width=True` for responsive sizing.
For very large DataFrames (>10k rows), consider:
- Adding pagination
- Filtering before display
- Downloading full CSV instead

---

## Security Notes

- **API keys**: Never displayed in UI. Store in `.env` file.
- **File uploads**: Saved to `/tmp/` with original filename. Not persisted beyond reconciliation.
- **Database**: Read/write access required. Ensure `multibagger.db` has correct permissions.
- **Snapshots**: Read/write access required. Ensure `snapshots/` directory has correct permissions.

---

## Extending the UI

To add a new tab:

1. **Add service method** in `src/multibagger/ui_service/service.py`:
   ```python
   def my_new_feature(as_of: str, param: int) -> Dict:
       """Description"""
       try:
           # Call core modules
           result = some_core_function(as_of, param)

           # Return typed dict
           return {
               "data_df": pd.DataFrame(result),
               "metrics": {...},
               "warnings": []
           }
       except Exception as e:
           return {"warnings": [str(e)]}
   ```

2. **Add render function** in `ui/app.py`:
   ```python
   def render_my_feature(globals_dict):
       st.header("🎯 My Feature")

       # Get inputs
       param = st.number_input("Parameter", value=10)

       # Call service
       if st.button("Run"):
           result = my_new_feature(globals_dict["as_of"], param)

           # Display results
           if result["warnings"]:
               for w in result["warnings"]:
                   st.warning(w)

           st.dataframe(result["data_df"])
   ```

3. **Add tab** in `main()`:
   ```python
   tabs = st.tabs([..., "🎯 My Feature"])

   with tabs[N]:
       render_my_feature(globals_dict)
   ```

---

## Known Limitations

- **No real-time updates**: UI must be manually refreshed
- **No background jobs**: All operations are blocking (use dry-run for long ops)
- **No multi-user support**: Single-user local deployment only
- **No auth**: No built-in authentication (Streamlit Community Cloud has basic auth)

---

## Support

For issues:
1. Check this README
2. Check main project README
3. Review error messages in UI (they're actionable!)
4. Check logs in `snapshots/{as_of}/logs/`

---

## License

Same as main project.
