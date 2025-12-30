import asyncio
import signal
from chat_aggregator import ChatAggregator
from stream_manager import StreamManager
from metadata_updater import MetadataUpdater
from config import load_config
import os
from logger import setup_logging
import logging

# initialize logging; allow overriding via LOG_LEVEL env var
log_level = os.getenv("LOG_LEVEL", "INFO")
logger = setup_logging(level=log_level)

async def main():
    config = load_config()
    logger.info("Config loaded.")
    chat = ChatAggregator(config.get("chat", {}))
    stream = StreamManager(config.get("stream", {}))
    meta = MetadataUpdater(config.get("metadata", {}))

    # start chat aggregator as a background task
    chat_task = asyncio.create_task(chat.start())

    logger.info("Main loop started - chat aggregator is running")
    logger.info("Press Ctrl+C to stop")
    
    try:
        # Keep running indefinitely until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # attempt graceful shutdown
        logger.info("Shutting down...")
        chat_task.cancel()
        await chat.stop()
        try:
            await asyncio.gather(chat_task, return_exceptions=True)
        except Exception:
            pass
        logger.info("Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")

