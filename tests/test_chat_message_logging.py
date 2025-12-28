import pytest
import logging
from chat_aggregator import ChatAggregator


class DummyAuthor:
    def __init__(self, name, id=None):
        self.name = name
        self.id = id


class DummyChannel:
    def __init__(self, name):
        self.name = name


class DummyMessage:
    def __init__(self, content, author, channel, tags=None, echo=False):
        self.content = content
        self.author = author
        self.channel = channel
        self.tags = tags or {}
        self.echo = echo


@pytest.mark.asyncio
async def test_event_message_logs(caplog):
    caplog.set_level(logging.INFO, logger="chat_aggregator")

    agg = ChatAggregator({})

    author = DummyAuthor('someuser', id='12345')
    channel = DummyChannel('vj_games')
    msg = DummyMessage('Hello https://twitch.tv/somechannel', author, channel, tags={'mod': '0'})

    # call module-level logger helper directly (no bot instantiation required)
    from chat_aggregator import log_chat_message
    log_chat_message(msg)

    # find structured log record
    records = [r for r in caplog.records if r.getMessage() == 'chat.message']
    assert records, 'chat.message not found in logs'
    rec = records[0]

    assert getattr(rec, 'channel') == 'vj_games'
    assert getattr(rec, 'author') == 'someuser'
    assert getattr(rec, 'author_id') == '12345'
    # link should be removed by sanitizer
    assert getattr(rec, 'content') == 'Hello'
    assert isinstance(getattr(rec, 'tags'), dict)
