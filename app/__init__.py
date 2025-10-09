# Prevent PyCharm from confusing local telegram folder with python-telegram-bot package
import sys
from pathlib import Path

# Remove app/telegram from potential import paths
app_telegram = str(Path(__file__).parent / "telegram")
if app_telegram in sys.path:
    sys.path.remove(app_telegram)