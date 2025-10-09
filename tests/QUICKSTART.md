# Quick Start - Running Tests

Super simple guide to get you testing right away.

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Run All Tests

```bash
# basic run
pytest

# with pretty output
pytest -v

# show print statements
pytest -s
```

## Run Specific Tests

```bash
# only unit tests
pytest tests/unit/

# only integration tests  
pytest tests/integration/

# specific file
pytest tests/unit/test_status_analyzer.py

# specific test
pytest tests/unit/test_status_analyzer.py::test_status_up_fast_response
```

## Check Coverage

```bash
# run with coverage
pytest --cov=app

# generate HTML report
pytest --cov=app --cov-report=html

# open the report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Watch Mode (Re-run on Changes)

```bash
# install pytest-watch first
pip install pytest-watch

# watch and re-run
ptw
```

## Parallel Execution (Faster)

```bash
# install pytest-xdist first
pip install pytest-xdist

# run in parallel
pytest -n auto
```

## Common Issues

### "No module named app"
```bash
# make sure you're in project root
cd bridge-status-bot/

# or set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### "Database errors"
Tests use in-memory SQLite, not your real DB. If you see DB errors, check that conftest.py is loaded correctly.

### "Async errors"
Make sure async tests have `@pytest.mark.asyncio` decorator.

## What Gets Tested?

- ✅ Status logic (UP/DOWN/SLOW/WARNING)
- ✅ Bridge monitoring
- ✅ Notifications
- ✅ Bot commands
- ✅ API endpoints
- ✅ WebSocket
- ✅ Database models

## CI/CD

Tests run automatically in CI:
```bash
# this is what CI runs
pytest --cov=app --cov-report=xml --cov-fail-under=70
```

## Need Help?

Check the full README in tests/README.md