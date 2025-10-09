# Tests for Bridge Status Bot

Comprehensive test suite covering all core functionality.

## Structure

```
tests/
├── conftest.py              # shared fixtures and test config
├── unit/                    # unit tests (isolated components)
│   ├── test_status_analyzer.py
│   ├── test_bridge_monitor.py
│   └── test_notification.py
├── integration/             # integration tests (DB + services)
│   ├── test_bot_commands.py
│   ├── test_api_endpoints.py
│   └── test_websocket.py
└── fixtures/
    └── sample_responses.json # mock API responses
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run with coverage
```bash
pytest --cov=app --cov-report=html
```

### Run specific test file
```bash
pytest tests/unit/test_status_analyzer.py
```

### Run specific test class
```bash
pytest tests/unit/test_status_analyzer.py::TestDetermineStatus
```

### Run specific test
```bash
pytest tests/unit/test_status_analyzer.py::TestDetermineStatus::test_status_up_fast_response
```

### Run only unit tests
```bash
pytest tests/unit/
```

### Run only integration tests
```bash
pytest tests/integration/
```

### Run with verbose output
```bash
pytest -v
```

### Run in parallel (faster)
```bash
pytest -n auto
```

## Test Coverage

Current coverage: **>70%**

Key areas covered:
- ✅ Status determination logic (UP/DOWN/SLOW/WARNING)
- ✅ Incident severity calculation
- ✅ Bridge health monitoring
- ✅ Notification delivery
- ✅ Rate limiting
- ✅ User subscriptions
- ✅ Bot commands (/start, /status, /subscribe, etc)
- ✅ API endpoints (bridges, incidents, health)
- ✅ WebSocket connections and broadcasts

## Fixtures

### Database Fixtures
- `db_engine` - test database engine
- `db_session` - database session with auto-rollback
- `sample_bridge` - single test bridge
- `sample_bridges` - multiple test bridges
- `sample_user` - test user
- `sample_subscription` - test subscription
- `sample_status` - test bridge status
- `sample_incident` - test incident

### Mock Fixtures
- `mock_redis_client` - in-memory Redis mock
- `mock_http_response` - mock HTTP response builder
- `mock_update` - mock Telegram Update
- `mock_context` - mock Telegram Context

## Writing New Tests

### Unit Test Example
```python
import pytest
from app.services.status_analyzer import determine_status

def test_new_status_logic():
    """Test new status determination logic"""
    status = determine_status(
        response_time=5000,
        http_code=200,
        bridge_specific_checks={}
    )
    assert status == "UP"
```

### Integration Test Example
```python
import pytest

@pytest.mark.asyncio
async def test_new_endpoint(db_session, sample_bridge):
    """Test new API endpoint"""
    # your test here
    pass
```

## CI/CD

Tests run automatically on:
- Every pull request
- Every commit to main branch
- Before deployment

Required:
- All tests must pass
- Coverage must be >70%
- No linting errors

## Troubleshooting

### Tests fail with database errors
Make sure you're using the test database (in-memory SQLite), not production DB.

### Tests timeout
Increase timeout in pytest.ini or use `@pytest.mark.timeout(30)` decorator.

### Mock not working
Check import order - mocks must be set up before importing the code being tested.

### Async test errors
Make sure to use `@pytest.mark.asyncio` decorator for async tests.

## Best Practices

1. **One assertion per test** (when possible)
2. **Descriptive test names** - should explain what's being tested
3. **Use fixtures** - don't repeat setup code
4. **Mock external dependencies** - HTTP calls, Redis, Telegram API
5. **Test edge cases** - not just happy paths
6. **Keep tests fast** - use in-memory DB, avoid sleep()
7. **Clean up after tests** - use fixtures with auto-cleanup

## Coverage Report

View HTML coverage report:
```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```