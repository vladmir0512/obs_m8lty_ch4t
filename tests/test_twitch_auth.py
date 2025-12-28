import types
import pytest
import twitch_auth


class DummyResp:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


def test_exchange_code_for_token(monkeypatch):
    called = {}

    def fake_post(url, data, timeout):
        called['url'] = url
        called['data'] = data
        return DummyResp({"access_token": "at", "refresh_token": "rt", "expires_in": 3600})

    monkeypatch.setattr(twitch_auth, 'requests', types.SimpleNamespace(post=fake_post))

    res = twitch_auth.exchange_code_for_token('cid', 'csec', 'code123', 'http://localhost/cb')
    assert res['access_token'] == 'at'
    assert res['refresh_token'] == 'rt'


def test_refresh_access_token(monkeypatch):
    def fake_post(url, data, timeout):
        assert data['grant_type'] == 'refresh_token'
        return DummyResp({"access_token": "newat", "refresh_token": "newrt", "expires_in": 3600})

    monkeypatch.setattr(twitch_auth, 'requests', types.SimpleNamespace(post=fake_post))

    res = twitch_auth.refresh_access_token('cid', 'csec', 'oldrt')
    assert res['access_token'] == 'newat'


def test_write_tokens_to_env(monkeypatch, tmp_path):
    # intercept _write_env to ensure it's called with expected values
    captured = {}

    def fake_write_env(updates, path=None):
        captured.update(updates)

    monkeypatch.setattr(twitch_auth, '_write_env', fake_write_env)
    twitch_auth.write_tokens_to_env('a', 'r', 123)
    assert captured['TWITCH_IRC_TOKEN'].startswith('oauth:')
    assert 'TWITCH_REFRESH_TOKEN' in captured
    assert 'TWITCH_TOKEN_EXPIRES_AT' in captured
