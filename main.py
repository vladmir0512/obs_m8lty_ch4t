import asyncio
import signal
from chat_aggregator import ChatAggregator
from stream_manager import StreamManager
from metadata_updater import MetadataUpdater
from config import load_config
from logger import setup_logging
import logging

# initialize logging
logger = setup_logging()

async def main():
    config = load_config()
    logger.info("Config loaded.")
    chat = ChatAggregator(config.get("chat", {}))
    stream = StreamManager(config.get("stream", {}))
    meta = MetadataUpdater(config.get("metadata", {}))

    # start chat aggregator as a background task so we can cancel on signal
    chat_task = asyncio.create_task(chat.start())

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _on_signal():
        logger.info("Signal received, shutting down...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # add_signal_handler may not be implemented on Windows
            pass

    try:
        await stop_event.wait()
    finally:
        # attempt graceful shutdown
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

