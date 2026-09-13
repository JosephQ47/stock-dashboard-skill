import sys
from pathlib import Path
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from http_client import HttpClient, SourceDown
import endpoints


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text

    def json(self):
        return {"text": self.text}


def make_client(monkeypatch, behavior):
    """behavior 是一个函数，接收调用序号返回 FakeResponse 或抛异常。"""
    slept = []
    calls = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        return behavior(calls["n"])

    monkeypatch.setattr(requests, "get", fake_get)
    client = HttpClient(sleeper=slept.append)
    return client, slept, calls


def test_get_returns_response(monkeypatch):
    client, _, _ = make_client(monkeypatch, lambda n: FakeResponse())
    r = client.get("http://x", source="tencent")
    assert r.status_code == 200


def test_eastmoney_sleeps_two_seconds_between_calls(monkeypatch):
    client, slept, _ = make_client(monkeypatch, lambda n: FakeResponse())
    client.get("http://x", source="eastmoney")
    client.get("http://x", source="eastmoney")
    assert slept and slept[-1] == pytest.approx(endpoints.EM_MIN_INTERVAL)


def test_first_call_does_not_sleep(monkeypatch):
    client, slept, _ = make_client(monkeypatch, lambda n: FakeResponse())
    client.get("http://x", source="eastmoney")
    assert slept == []


def test_eastmoney_call_cap_enforced(monkeypatch):
    client, _, _ = make_client(monkeypatch, lambda n: FakeResponse())
    for _ in range(endpoints.EM_MAX_CALLS):
        client.get("http://x", source="eastmoney")
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")


def test_connection_error_trips_breaker(monkeypatch):
    def behavior(n):
        raise requests.ConnectionError("closed")

    client, _, _ = make_client(monkeypatch, behavior)
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")
    assert client.is_tripped("eastmoney")


def test_tripped_source_refuses_without_network_call(monkeypatch):
    def behavior(n):
        raise requests.ConnectionError("closed")

    client, _, calls = make_client(monkeypatch, behavior)
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")
    before = calls["n"]
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")
    assert calls["n"] == before


def test_breaker_is_per_source(monkeypatch):
    def behavior(n):
        if n == 1:
            raise requests.ConnectionError("closed")
        return FakeResponse()

    client, _, _ = make_client(monkeypatch, behavior)
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")
    assert client.get("http://y", source="tencent").status_code == 200


def test_non_200_raises_sourcedown(monkeypatch):
    client, _, _ = make_client(monkeypatch, lambda n: FakeResponse(status_code=500))
    with pytest.raises(SourceDown):
        client.get("http://x", source="cninfo")


def test_call_count_tracks_per_source(monkeypatch):
    client, _, _ = make_client(monkeypatch, lambda n: FakeResponse())
    client.get("http://x", source="tencent")
    client.get("http://x", source="tencent")
    assert client.call_count("tencent") == 2
    assert client.call_count("eastmoney") == 0
