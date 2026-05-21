import json
import urllib.error
from unittest.mock import patch, MagicMock
from io import BytesIO
import pytest

from app_classifier.llm._http import post_json


def _mock_response(payload: dict, status: int = 200):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.getcode.return_value = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_post_json_happy_path():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_response({"ok": True, "value": 42})
        result = post_json(
            "https://api.example.com/v1/x",
            body={"prompt": "hi"},
            headers={"Authorization": "Bearer KEY"},
        )
    assert result == {"ok": True, "value": 42}
    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    assert req.full_url == "https://api.example.com/v1/x"
    assert req.get_method() == "POST"
    assert req.headers["Authorization"] == "Bearer KEY"
    assert req.headers["Content-type"] == "application/json"
    assert json.loads(req.data.decode()) == {"prompt": "hi"}


def test_post_json_returns_none_on_401():
    with patch("urllib.request.urlopen") as mock_urlopen:
        err = urllib.error.HTTPError(
            url="x", code=401, msg="Unauthorized", hdrs=None, fp=BytesIO(b"")
        )
        mock_urlopen.side_effect = err
        assert post_json("https://x", {}, retries=0) is None


def test_post_json_retries_on_429_then_returns_none():
    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("time.sleep") as mock_sleep:
        err = urllib.error.HTTPError(
            url="x", code=429, msg="Too Many", hdrs=None, fp=BytesIO(b"")
        )
        mock_urlopen.side_effect = [err, err]
        assert post_json("https://x", {}) is None
        assert mock_urlopen.call_count == 2
        mock_sleep.assert_called_once_with(2.0)


def test_post_json_retries_on_5xx_then_succeeds():
    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("time.sleep"):
        err = urllib.error.HTTPError(
            url="x", code=503, msg="Bad Gateway", hdrs=None, fp=BytesIO(b"")
        )
        mock_urlopen.side_effect = [err, _mock_response({"ok": True})]
        assert post_json("https://x", {}) == {"ok": True}


def test_post_json_returns_none_on_network_error():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        assert post_json("https://x", {}, retries=0) is None


def test_post_json_returns_none_on_invalid_json():
    resp = MagicMock()
    resp.read.return_value = b"not-json"
    resp.getcode.return_value = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        assert post_json("https://x", {}, retries=0) is None
