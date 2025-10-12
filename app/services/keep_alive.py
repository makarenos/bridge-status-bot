"""
Keep-alive to prevent Render from sleeping
"""

import asyncio
import aiohttp
from app.utils.logger import logger


class KeepAliveService:
    def __init__(self, url: str, interval: int = 840):  # ping every 14 min
        self.url = url
        self.interval = interval
        self.task = None
        self.running = False

    async def _ping(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"{self.url}/health/live",
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.debug("Keep-alive ping OK")
        except Exception as e:
            logger.error(f"Keep-alive failed: {e}")

    async def _loop(self):
        logger.info(f"Keep-alive: pinging every {self.interval}s")
        while self.running:
            await asyncio.sleep(self.interval)
            if self.running:
                await self._ping()

    def start(self):
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._loop())
            logger.info("Keep-alive started")

    def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()