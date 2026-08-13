"""Console entry point for unattended startup diagnostics."""

import logging
import sys
import time

from src.main import FishingBot
from src.settings import settings


logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


bot = FishingBot()
for remaining in range(settings.startup_delay_sec, 0, -1):
    print(f"Starting in {remaining}s...", flush=True)
    time.sleep(1)

bot.start()
try:
    while bot.is_running:
        print(f"status={bot.status}", flush=True)
        time.sleep(2)
except KeyboardInterrupt:
    pass
finally:
    bot.stop()
