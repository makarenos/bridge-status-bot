"""
Скрипт для первоначального заполнения базы мостами
Запускать после миграций: python scripts/seed_bridges.py
"""

import asyncio
import sys
from pathlib import Path

# добавляем корень проекта в path чтобы импорты работали
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import async_session_maker, engine
from app.models.bridge import Bridge


# данные мостов из спеки
BRIDGES_DATA = [
    {
        "name": "Stargate",
        "api_endpoint": "https://api.stargate.finance/v1/status",
        "backup_endpoint": None,
        "check_interval_seconds": 60,
        "is_active": True,
    },
    {
        "name": "Hop Protocol",
        "api_endpoint": "https://hop.exchange/v1-1/available-liquidity",
        "backup_endpoint": None,
        "check_interval_seconds": 60,
        "is_active": True,
    },
    {
        "name": "Arbitrum Bridge",
        "api_endpoint": "https://bridge.arbitrum.io/api/status",
        "backup_endpoint": "https://arbiscan.io/api",
        "check_interval_seconds": 60,
        "is_active": True,
    },
    {
        "name": "Polygon Bridge",
        "api_endpoint": "https://wallet.polygon.technology/bridge/status",
        "backup_endpoint": None,
        "check_interval_seconds": 60,
        "is_active": True,
    },
    {
        "name": "Optimism Bridge",
        "api_endpoint": "https://gateway.optimism.io/v1/status",
        "backup_endpoint": None,
        "check_interval_seconds": 60,
        "is_active": True,
    },
]


async def seed_bridges():
    """Заполняем базу мостами если их еще нет"""

    async with async_session_maker() as session:
        # проверяем что мостов еще нет
        result = await session.execute(select(Bridge))
        existing_bridges = result.scalars().all()

        if existing_bridges:
            print(f"⚠️  В базе уже есть {len(existing_bridges)} мостов, пропускаем")
            return

        # добавляем мосты
        print("🌉 Добавляем мосты в базу...")
        for bridge_data in BRIDGES_DATA:
            bridge = Bridge(**bridge_data)
            session.add(bridge)
            print(f"  ✅ {bridge_data['name']}")

        await session.commit()
        print(f"\n🎉 Успешно добавлено {len(BRIDGES_DATA)} мостов!")


async def main():
    """Точка входа"""
    try:
        await seed_bridges()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
    finally:
        # закрываем соединение с БД
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())