I'll help you rewrite the README in English with a casual, clear style. Here's the updated version:

# Bridge Status Bot 🌉

A Telegram bot that monitors cross-chain bridges in real-time. Watches bridge status, sends alerts when stuff breaks, and generally makes life easier.

## What It Does

- 🔍 Monitors 5 popular bridges (Stargate, Hop, Arbitrum, Polygon, Optimism)
- 🚨 Sends Telegram alerts when bridges go down or slow down
- 📊 Shows incident history
- 🔔 Flexible notification subscriptions
- 🌐 REST API + WebSocket for integrations
- 💾 Stores everything in PostgreSQL

## Quick Start

### What You Need

- Python 3.11+
- Docker and Docker Compose (for local dev)
- Telegram bot token (get it from @BotFather)

### Running with Docker (recommended)

```bash
# Clone the repo
git clone <your-repo-url>
cd bridge-status-bot

# Copy env file and add your bot token
cp .env.example .env
# Edit .env and paste your TELEGRAM_BOT_TOKEN

# Start everything
docker-compose up -d

# Check that services are alive
docker-compose ps

# View logs
docker-compose logs -f bot
```

Done! Bot is live at `@your_bot_name`, API at `http://localhost:8000`

### Running without Docker (for development)

```bash
# Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis (needs Docker)
docker-compose up -d db redis

# Run migrations
alembic upgrade head

# Seed bridges into database
python scripts/seed_bridges.py

# Start API
uvicorn app.main:app --reload

# In another terminal, start bot
python -m app.bot
```

## Bot Commands

- `/start` - get started
- `/status` - current status of all bridges
- `/subscribe <bridge>` - subscribe to alerts
- `/unsubscribe <bridge>` - unsubscribe
- `/list` - list all monitored bridges
- `/history <bridge>` - 24h history
- `/incidents` - active problems
- `/settings` - notification settings
- `/help` - help info

## API

Docs available at `http://localhost:8000/docs` (Swagger UI)

### Main Endpoints

```
GET  /api/v1/bridges              - list bridges with current status
GET  /api/v1/bridges/{id}/status  - bridge status history
GET  /api/v1/bridges/{id}/incidents - bridge incidents
GET  /health                       - health check
WS   /ws                           - WebSocket for real-time updates
```

## Architecture

Project is split into independent parts:

- **FastAPI server** - REST API + WebSocket
- **Telegram bot** - separate process with command handlers
- **Bridge Monitor** - core system, checks bridges and logs status
- **Notification Service** - sends alerts to subscribers
- **PostgreSQL** - data storage
- **Redis** - caching + rate limiting

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/
```

## Project Structure

```
bridge-status-bot/
├── app/
│   ├── main.py              # FastAPI app
│   ├── bot.py               # Telegram bot
│   ├── config.py            # configs
│   ├── core/                # basic stuff (DB, Redis)
│   ├── models/              # SQLAlchemy models
│   ├── services/            # business logic
│   ├── api/                 # REST endpoints
│   ├── telegram/            # bot handlers
│   └── utils/               # helper functions
├── tests/                   # tests
├── alembic/                 # DB migrations
├── scripts/                 # utilities
└── docs/                    # documentation
```

## Bridge Monitoring

Bot checks each bridge every 5 minutes (configurable in `.env`).

**Status logic:**
- 🟢 **UP** - all good, response < 10 seconds
- 🟡 **SLOW** - sluggish, response 10-30 seconds
- ⚠️ **WARNING** - problems, response 30-60 seconds or specific metric issues
- 🔴 **DOWN** - not responding or error

Each bridge has specific checks:
- **Hop Protocol** - check liquidity (should be > $100K)
- **Optimism** - withdrawal queue length (should be < 1000)
- **Arbitrum** - average withdrawal time (should be < 30 minutes)
- etc.

## DB Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current version
alembic current
```

## Deployment

For production:
1. Use external PostgreSQL and Redis (not in Docker)
2. Set up HTTPS for API
3. Enable Telegram webhook instead of polling
4. Add monitoring (Prometheus + Grafana)
5. Configure logging to external service

More details in `docs/DEPLOYMENT.md`

## Possible Improvements

- [ ] Add social media monitoring (Twitter/Discord)
- [ ] ML for incident prediction
- [ ] More bridges (currently 5, could add 10+)
- [ ] Web dashboard in React
- [ ] Bridge fee comparison
- [ ] Mobile push notifications
- [ ] CI/CD pipeline

## License

MIT - do whatever you want 🤷‍♂️

## Contact

If something breaks or you have ideas - open an issue!