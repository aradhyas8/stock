# Bootstrap Guide

This document explains the tooling choices and setup decisions for the Multi-Bagger Research System.

## Environment Manager: uv

**Choice**: We use [uv](https://github.com/astral-sh/uv) instead of pip, poetry, or conda.

**Rationale**:
- **Speed**: 10-100x faster than pip for dependency resolution and installation
- **Deterministic**: Automatically generates lockfiles with exact versions
- **Zero Configuration**: No need to manage separate virtual environments  
- **Cross-Platform**: Identical behavior on Linux, macOS, and Windows
- **Future-Proof**: Built by Astral (creators of ruff and black)
- **Cargo-inspired**: Modern dependency management similar to Rust's Cargo

**Key Benefits for This Project**:
- Monthly runs need fast, reliable dependency resolution
- CI/CD pipelines benefit from consistent, cached installs
- Local development setup is trivial (`uv sync`)
- No virtual environment activation needed

## Task Runner: Make

**Choice**: GNU Make with cross-platform compatibility.

**Rationale**:
- **Universal**: Available on all target platforms (Linux, macOS, Windows WSL)
- **Simple**: Easy-to-read targets with clear dependencies
- **Standard**: Expected tool in most development environments
- **Self-Documenting**: Built-in help system via comments

**Key Targets**:
```bash
make setup          # Complete project setup
make check          # Run linting and tests  
make run-monthly    # Execute monthly pipeline
make clean          # Clean build artifacts
make format         # Auto-format code
```

## Code Quality Stack

**Linting & Formatting**:
- **ruff**: Ultra-fast Python linter (replaces flake8, isort, etc.)
- **black**: Opinionated code formatter
- **mypy**: Static type checking

**Testing**:
- **pytest**: Test framework with rich plugin ecosystem
- **pytest-cov**: Coverage reporting
- **typer.testing**: CLI testing utilities

**Pre-commit Hooks**:
- Enforces formatting and linting on every commit
- Prevents committing broken code
- Fast feedback loop for developers

## Database Strategy

**Development**: SQLite (zero-ops, perfect for local development)
**Production**: Same SQLite (until scale demands PostgreSQL)

**Rationale**:
- SQLite handles millions of records efficiently
- Zero configuration or maintenance
- Perfect for monthly batch processing
- Can migrate to PostgreSQL later if needed

## Configuration Management

**Structure**:
```
config.example.yml  # Template with all options
config.yml          # Local configuration (git-ignored)
.env.example        # Environment variables template  
.env                # Local secrets (git-ignored)
```

**Benefits**:
- Clear separation of config vs secrets
- Easy onboarding (copy examples)
- No accidental secret commits
- Version-controlled defaults

## Dependency Strategy

**Runtime Dependencies**: Minimal, well-maintained packages
- `yfinance`: Yahoo Finance data (most reliable free source)
- `pandas/numpy`: Data processing (industry standard)
- `typer/rich`: CLI with beautiful output
- `sqlalchemy`: Database ORM (future-proof)

**Development Dependencies**: Modern toolchain
- `ruff/black`: Fast linting and formatting
- `pytest`: Testing framework
- `mypy`: Type checking
- `pre-commit`: Git hooks

**Dependency Pinning**:
- Major versions pinned (`>=2.1.0` not `^2.1.0`)
- Lockfile ensures reproducible builds
- Regular updates via `make deps-update`

## Directory Structure Rationale

```
src/multibagger/           # Main package (importable)
├── universe/              # Stock universe management
├── data/                  # Data ingestion layer
├── screens/               # Multi-factor screening
├── forensics/             # Red flag detection  
├── research/              # Business analysis
├── portfolio/             # Position management
├── monitor/               # Continuous monitoring
└── cli/                   # Command-line interface

data/                      # Raw data (git-ignored)
reports/                   # Generated reports (git-ignored)
logs/                      # Application logs (git-ignored)  
snapshots/YYYY-MM/         # Monthly run outputs
├── reports/               # PDF research reports
├── logs/                  # Execution logs
└── candidates.json        # Top stock picks

tests/                     # Test suite
docs/                      # Documentation
config/                    # Configuration templates
```

**Benefits**:
- Clear separation of concerns
- Easy to find relevant code
- Scales from MVP to full system
- Standard Python package structure

## CI/CD Strategy

**GitHub Actions**: 
- Test on Python 3.10, 3.11, 3.12
- Run linting, type checking, tests
- Generate coverage reports
- Build distribution packages

**Quality Gates**:
- All tests must pass
- 80%+ code coverage
- No linting errors
- Type checking passes

**Deployment**: 
- Initial: Manual deployment to single server
- Future: Docker containers with automated deployments

## Development Workflow

1. **Setup**: `make setup` (one-time)
2. **Development**: Edit code, tests auto-run via pre-commit
3. **Testing**: `make check` before pushing
4. **Monthly Run**: `make run-monthly` 
5. **Updates**: `make deps-update` monthly

**Branch Strategy**:
- `main`: Production-ready code
- `develop`: Integration branch
- Feature branches for new functionality

## Production Considerations

**Scheduling**: 
```bash
# Cron entry for first of each month
0 0 1 * * cd /path/to/project && make run-monthly
```

**Monitoring**:
- Application logs in `logs/`
- Monthly snapshots for audit trail
- Email alerts on failures (configurable)

**Backup**:
- SQLite database backed up monthly
- Git repository contains all code/config
- Snapshots preserved for historical analysis

## Future Migration Paths

**Phase 1 → Phase 2**: Add screening algorithms
**Phase 2 → Phase 3**: Add forensic accounting  
**Phase 3+**: Add ML models, advanced analytics

**Technical Debt Management**:
- Regular dependency updates
- Code quality monitoring
- Performance profiling of monthly runs
- Migration to PostgreSQL when data exceeds 10GB

This bootstrap approach prioritizes:
1. **Speed**: Fast setup and development cycles
2. **Reliability**: Deterministic builds and deployments  
3. **Simplicity**: Minimal complexity, maximum functionality
4. **Maintainability**: Clear structure, good documentation
