# Multi-Bagger Research System

A systematic investment research pipeline that identifies potential multi-bagger stocks (2-5x returns) from ~5,000 stocks monthly.

## What It Does

- **Screens** 5,000 stocks down to 10-15 high-conviction candidates
- **Analyzes** business models, financials, and competitive moats
- **Detects** accounting red flags and governance issues
- **Generates** institutional-quality PDF research reports
- **Monitors** portfolio positions for thesis changes

## Prerequisites

- Python 3.10+ 
- Git
- Make (optional but recommended)

## Quick Start

```bash
# Clone and setup
git clone <this-repo>
cd multi-bagger-research

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: pip install uv

# Create environment and install dependencies
make setup

# Run monthly pipeline (placeholder for now)
make run-monthly

# Run tests and linting
make check
```

## Environment Manager Choice: uv

We chose **uv** over pip/poetry/conda because:

- **Speed**: 10-100x faster than pip for installs
- **Deterministic**: Automatic lockfile generation and resolution
- **Zero-config**: No separate virtual env management needed
- **Cross-platform**: Works identically on Linux/macOS/Windows
- **Future-proof**: Built by Astral (ruff, black creators)

## Project Structure

```
src/
├── universe/          # Stock universe definition and filtering
├── data/             # Data ingestion from APIs (Yahoo, Alpha Vantage)
├── screens/          # Multi-factor screening and scoring
├── forensics/        # Accounting red flag detection (M-Score, etc.)
├── research/         # Business analysis and competitive moats
├── portfolio/        # Position sizing and portfolio construction
├── monitor/          # Continuous monitoring and alerts
└── cli/              # Command-line interface

data/                 # Raw data storage (git-ignored)
reports/              # Generated PDF reports (git-ignored)  
logs/                 # Application logs (git-ignored)
snapshots/            # Monthly run snapshots (2025-11/, etc.)
```

## Development Phases

**Current Phase**: Foundation (Phase 1-2)
- ✅ Repository scaffold and tooling
- 🚧 Data infrastructure (APIs, caching, storage)
- 🚧 Basic quantitative screening
- ⏳ Report generation

**Next**: Forensic analysis, business model evaluation, portfolio optimization

## Configuration

Copy `config.example.yml` to `config.yml` and customize:

```yaml
markets: [US, INDIA]
data_sources: [YAHOO, ALPHA_VANTAGE, FMP]
universe_size: 5000
monthly_candidates: 15
```

API keys go in `.env` (never committed):

```bash
ALPHA_VANTAGE_KEY=your_key_here
FMP_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

## Monthly Operation

The system runs monthly via cron:

```bash
# Example crontab entry (first day of each month at midnight)
0 0 1 * * cd /path/to/multi-bagger-research && make run-monthly
```

Each run creates a timestamped snapshot:
```
snapshots/2025-11/
├── candidates.json    # Top stocks identified
├── reports/          # PDF research reports
├── logs/             # Execution logs
└── metrics.json      # Pipeline performance
```

## Documentation

- [Bootstrap Guide](docs/BOOTSTRAP.md) - Setup details and tool choices
- [Runbook](docs/RUNBOOK.md) - Operations and scheduling
- [Contributing](CONTRIBUTING.md) - Development guidelines

## License

MIT License - see [LICENSE](LICENSE) for details.
