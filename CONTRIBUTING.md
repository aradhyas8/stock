# Contributing to Multi-Bagger Research System

Thank you for your interest in contributing! This document provides guidelines for contributing to the Multi-Bagger Research System.

## Development Setup

### Prerequisites
- Python 3.10+
- Git
- Make

### Initial Setup
```bash
# Fork and clone the repository
git clone https://github.com/your-username/multi-bagger-research.git
cd multi-bagger-research

# Set up development environment
make setup

# Install pre-commit hooks
make install-git-hooks

# Verify setup
make check
```

## Development Workflow

### Making Changes
1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Write code following our style guidelines
   - Add tests for new functionality
   - Update documentation as needed

3. **Test your changes**:
   ```bash
   # Run tests and linting
   make check
   
   # Format code
   make format
   
   # Test specific functionality
   make run-monthly --dry-run
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add new screening algorithm"
   ```

5. **Push and create pull request**:
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Style Guidelines

### Python Code Style
- **Formatting**: Use `black` (automated via `make format`)
- **Linting**: Use `ruff` (checked via `make lint`)
- **Type Hints**: Required for all public functions and methods
- **Docstrings**: Use Google-style docstrings for all public APIs

### Example Code Style
```python
from typing import List, Optional
import pandas as pd

def calculate_roce(
    ebit: float, 
    total_assets: float, 
    current_liabilities: float
) -> Optional[float]:
    """Calculate Return on Capital Employed (ROCE).
    
    Args:
        ebit: Earnings Before Interest and Taxes
        total_assets: Total assets from balance sheet
        current_liabilities: Current liabilities from balance sheet
        
    Returns:
        ROCE as a percentage, or None if calculation not possible
        
    Raises:
        ValueError: If inputs are negative or invalid
    """
    if total_assets <= current_liabilities:
        return None
        
    capital_employed = total_assets - current_liabilities
    return (ebit / capital_employed) * 100
```

## Testing Guidelines

### Test Structure
- Place tests in `tests/` directory
- Mirror source structure: `tests/test_screens.py` for `src/multibagger/screens/`
- Use descriptive test names: `test_calculate_roce_with_valid_inputs()`

### Test Requirements
- **Unit Tests**: Test individual functions and methods
- **Integration Tests**: Test component interactions
- **CLI Tests**: Test command-line interface
- **Coverage**: Maintain 80%+ code coverage

### Example Test
```python
import pytest
from multibagger.screens.factors import calculate_roce

def test_calculate_roce_with_valid_inputs():
    """Test ROCE calculation with normal inputs."""
    result = calculate_roce(ebit=100, total_assets=1000, current_liabilities=200)
    assert result == 12.5

def test_calculate_roce_with_invalid_inputs():
    """Test ROCE calculation handles invalid inputs."""
    result = calculate_roce(ebit=100, total_assets=100, current_liabilities=200)
    assert result is None
```

## Documentation Guidelines

### Code Documentation
- **Docstrings**: Required for all public functions, classes, and modules
- **Type Hints**: Use for all function parameters and returns
- **Comments**: Explain business logic, especially financial calculations

### Financial Formula Documentation
Always document financial calculations with sources:

```python
def calculate_piotroski_score(financials: dict) -> int:
    """Calculate Piotroski F-Score for fundamental analysis.
    
    The Piotroski F-Score is a 9-point scale (0-9) that assesses the 
    financial strength of a company based on profitability, leverage, 
    liquidity, and operational efficiency.
    
    Reference: Piotroski, J. D. (2000). "Value Investing: The Use of 
    Historical Financial Statement Information to Separate Winners from Losers"
    
    Args:
        financials: Dictionary containing financial statement data
        
    Returns:
        Integer score from 0 (weak) to 9 (strong)
    """
```

## Contributing Areas

### Phase 1: Data Infrastructure (Current Priority)
- **Universe Builder**: Stock filtering and classification
- **API Connectors**: Yahoo Finance, Alpha Vantage integration
- **Data Storage**: SQLite schema and caching layer
- **Rate Limiting**: API request management

### Phase 2: Screening Engine
- **Factor Calculations**: Financial ratios and metrics
- **Scoring Algorithms**: Multi-factor composite scoring
- **Performance**: Optimization for large datasets

### Phase 3+: Advanced Features
- **Forensic Accounting**: Red flag detection algorithms
- **Business Analysis**: Moat identification and scoring
- **Portfolio Management**: Optimization and monitoring

## Commit Message Guidelines

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add yahoo finance data connector
fix: handle missing earnings data gracefully
docs: update API rate limiting documentation
test: add unit tests for ROCE calculation
refactor: extract common database utilities
perf: optimize screening pipeline for large datasets
```

**Types**:
- `feat`: New features
- `fix`: Bug fixes  
- `docs`: Documentation changes
- `test`: Test additions/modifications
- `refactor`: Code restructuring
- `perf`: Performance improvements
- `chore`: Maintenance tasks

## Pull Request Guidelines

### PR Checklist
- [ ] Tests pass (`make check`)
- [ ] Code is formatted (`make format`)
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (for significant changes)
- [ ] PR description explains the change and rationale

### PR Template
```markdown
## Description
Brief description of changes and motivation.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Performance improvement

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Financial Logic
If adding financial calculations:
- [ ] Formula documented with academic/industry source
- [ ] Edge cases handled (missing data, zero division)
- [ ] Validated against known benchmarks
```

## Review Process

### Code Review Focus Areas
1. **Correctness**: Does the code do what it claims?
2. **Financial Accuracy**: Are calculations correct and well-sourced?
3. **Performance**: Will it handle 5,000 stocks efficiently?
4. **Maintainability**: Is the code clear and well-documented?
5. **Testing**: Are edge cases covered?

### Review Checklist for Financial Code
- [ ] Formula matches academic/industry standards
- [ ] Handles missing or invalid data gracefully
- [ ] Performance acceptable for large datasets
- [ ] Unit tests cover edge cases
- [ ] Documentation includes calculation source

## Getting Help

### Resources
- **Documentation**: Check `docs/` directory first
- **Issues**: Search existing GitHub issues
- **Discussions**: Use GitHub Discussions for questions

### Financial Domain Knowledge
This project requires understanding of:
- **Financial Statements**: Balance sheet, income statement, cash flow
- **Financial Ratios**: ROE, ROCE, debt ratios, etc.
- **Valuation Methods**: DCF, multiples, screening factors
- **Market Mechanics**: Corporate actions, data adjustments

### Recommended Reading
- "The Intelligent Investor" by Benjamin Graham
- "One Up On Wall Street" by Peter Lynch
- "Financial Statement Analysis" by Martin Fridson
- Academic papers on factor investing and screening

## Code of Conduct

### Our Standards
- **Respectful**: Treat all contributors with respect
- **Collaborative**: Work together toward better investment research
- **Learning-Focused**: Help others learn financial analysis
- **Quality-Oriented**: Strive for accurate, well-tested code

### Scope
This project focuses on systematic, rules-based investment research. We avoid:
- Market timing or trading strategies
- Individual stock recommendations
- Get-rich-quick schemes
- Unsubstantiated financial claims

Thank you for contributing to systematic, evidence-based investment research!
