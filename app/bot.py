"""
Telegram bot entry point
Handles bot initialization and lifecycle management
"""

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.core.database import close_db
from app.core.redis import redis_client
from app.telegram.handlers import BotHandlers
from app.utils.logger import logger


class BridgeStatusBot:
    """Main bot class - sets up handlers and manages lifecycle"""

    def __init__(self):
        self.application = None
        self.handlers = BotHandlers()
        self.bot_engine = None

    def setup_handlers(self):
        """
        Register all command and callback handlers
        Maps bot commands to handler functions
        """
        # basic commands
        self.application.add_handler(
            CommandHandler("start", self.handlers.start_command)
        )
        self.application.add_handler(
            CommandHandler("help", self.handlers.help_command)
        )

        # monitoring commands
        self.application.add_handler(
            CommandHandler("status", self.handlers.status_command)
        )
        self.application.add_handler(
            CommandHandler("list", self.handlers.list_command)
        )
        self.application.add_handler(
            CommandHandler("history", self.handlers.history_command)
        )
        self.application.add_handler(
            CommandHandler("incidents", self.handlers.incidents_command)
        )

        # subscription commands
        self.application.add_handler(
            CommandHandler("subscribe", self.handlers.subscribe_command)
        )
        self.application.add_handler(
            CommandHandler("unsubscribe", self.handlers.unsubscribe_command)
        )

        # settings
        self.application.add_handler(
            CommandHandler("settings", self.handlers.settings_command)
        )

        # callback query handlers for inline keyboard buttons
        self.application.add_handler(
            CallbackQueryHandler(
                self.handlers.handle_subscription_callback,
                pattern=r"^(sub|unsub):\d+$"
            )
        )
        self.application.add_handler(
            CallbackQueryHandler(
                self.handlers.handle_settings_callback,
                pattern=r"^toggle_notifications$"
            )
        )

        logger.info("All bot handlers registered successfully")

    async def post_init(self, application):
        """Called after bot starts up - connect to external services"""
        logger.info("Initializing bot services...")

        # create separate database engine for bot thread
        logger.info("Creating bot database engine...")
        database_url = settings.database_url.replace(
            "postgresql://",
            "postgresql+asyncpg://"
        )

        self.bot_engine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

        bot_session_maker = async_sessionmaker(
            self.bot_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # pass session maker to handlers
        self.handlers.engine = self.bot_engine
        self.handlers.session_maker = bot_session_maker
        logger.info("Bot database engine created")

        # connect to Redis for caching
        await redis_client.connect()
        logger.info("Redis connected")

        logger.info("Bot initialized and ready to handle commands")

    async def post_shutdown(self, application):
        """Called before shutdown - clean up connections"""
        logger.info("Shutting down bot...")

        # close bot engine
        if self.bot_engine:
            await self.bot_engine.dispose()
            logger.info("Bot database engine closed")

        await redis_client.close()
        await close_db()

        logger.info("Bot shutdown complete")


def main():
    """Entry point - start the bot"""
    try:
        logger.info("Starting Bridge Status Bot...")

        bot = BridgeStatusBot()

        # create application with token from config
        bot.application = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .post_init(bot.post_init)
            .post_shutdown(bot.post_shutdown)
            .build()
        )

        # register all command handlers
        bot.setup_handlers()

        # run bot in polling mode
        logger.info("Bot running in polling mode...")
        logger.info("Press Ctrl+C to stop")

        # run_polling() manages its own event loop
        bot.application.run_polling(
            allowed_updates=["message", "callback_query"],
            close_loop=False,  # don't mess with event loop in thread
            stop_signals=None  # disable signal handlers (not main thread)
        )

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    main()