"""
FastAPI + Telegram Bot in single process
Using webhook for production (no polling conflicts)
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application

from app.config import settings
from app.core.database import close_db, async_session_maker, engine
from app.core.redis import redis_client
from app.services.scheduler import initialize_scheduler, bridge_scheduler
from app.utils.logger import logger
from app.api.routes import bridges, health
from app.api.routes.websocket import websocket_endpoint, manager as ws_manager
from app.bot import BridgeStatusBot
from app.services.keep_alive import KeepAliveService

# global bot instance
telegram_bot: Application = None
WEBHOOK_PATH = f"/webhook/{settings.telegram_bot_token}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown for API + Bot together
    """
    global telegram_bot

    logger.info("Starting API + Bot in single process...")

    keep_alive = None  # declare here so it's available in shutdown

    # connect to Redis
    try:
        await redis_client.connect()
        logger.info("Redis connected")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise

    # START TELEGRAM BOT
    logger.info("Starting Telegram bot...")
    try:
        bot_instance = BridgeStatusBot()

        telegram_bot = (
            Application.builder()
                .token(settings.telegram_bot_token)
                .build()
        )

        # set session_maker BEFORE registering handlers
        bot_instance.handlers.engine = engine
        bot_instance.handlers.session_maker = async_session_maker
        logger.info("Handlers configured with DB session")

        bot_instance.application = telegram_bot
        bot_instance.setup_handlers()

        # initialize bot
        await telegram_bot.initialize()
        await telegram_bot.start()

        logger.info("Bot initialized")

        # set webhook URL
        webhook_url = f"https://bridge-status-bot.onrender.com{WEBHOOK_PATH}"

        try:
            await telegram_bot.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True
            )
            logger.info(f"Webhook set to: {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            # fallback to polling if webhook fails
            asyncio.create_task(
                telegram_bot.updater.start_polling(
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True
                )
            )
            logger.warning("Fell back to polling mode")

    except Exception as e:
        logger.error(f"Bot startup failed: {e}", exc_info=True)
        raise

    # start scheduler with telegram_bot.bot for notifications
    try:
        scheduler = initialize_scheduler(
            bot=telegram_bot.bot,
            websocket_manager=ws_manager
        )
        scheduler.start()

        # start keep-alive to prevent Render from sleeping
        keep_alive = KeepAliveService("https://bridge-status-bot.onrender.com")
        keep_alive.start()

        logger.info("Scheduler and keep-alive started")
    except Exception as e:
        logger.error(f"Scheduler failed: {e}")
        raise

    # run initial check
    try:
        logger.info("Running initial bridge check...")
        await scheduler.run_immediate_check()
        logger.info("Initial check done")
    except Exception as e:
        logger.warning(f"Initial check failed: {e}")

    logger.info("API + Bot both running now!")

    yield

    # SHUTDOWN
    logger.info("Shutting down...")

    # stop keep-alive first
    if keep_alive:
        keep_alive.stop()

    # delete webhook
    if telegram_bot:
        try:
            await telegram_bot.bot.delete_webhook()
            logger.info("Webhook deleted")
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")

    # stop bot
    if telegram_bot:
        try:
            await telegram_bot.stop()
            await telegram_bot.shutdown()
            logger.info("Bot stopped")
        except Exception as e:
            logger.error(f"Bot shutdown error: {e}")

    # stop scheduler
    if bridge_scheduler:
        try:
            bridge_scheduler.shutdown()
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Scheduler shutdown error: {e}")

    # close connections
    try:
        await redis_client.close()
        await close_db()
        logger.info("Connections closed")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


# FastAPI app
app = FastAPI(
    title="Bridge Status Bot",
    description="Bridge monitoring with Telegram notifications",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# register routes
app.include_router(health.router)
app.include_router(bridges.router)


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint
    Receives updates from Telegram instead of polling
    """
    if not telegram_bot:
        return {"status": "bot not initialized"}

    try:
        data = await request.json()
        update = Update.de_json(data, telegram_bot.bot)
        await telegram_bot.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    """Real-time bridge updates via WebSocket"""
    await websocket_endpoint(websocket)


@app.get("/")
async def root():
    """API info"""
    bot_status = "running" if telegram_bot and telegram_bot.running else "not running"

    return {
        "name": "Bridge Status Bot",
        "version": "1.0.0",
        "api": "operational",
        "bot": bot_status,
        "webhook": WEBHOOK_PATH,
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "ws": "/ws"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )