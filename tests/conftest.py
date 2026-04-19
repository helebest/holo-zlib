"""pytest 共享 fixtures。

zlib.py 里的 _credentials / _opener 是模块级缓存，需要在每个测试前后清零，
否则上一条测试的 mock 会泄漏到下一条。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 把 scripts/ 加入 sys.path，使 `import zlib_script` 可用
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def zlib_module(monkeypatch, tmp_path):
    """导入 zlib 模块的干净副本，并把凭据文件指向临时路径。"""
    import importlib

    # zlib.py 名字和标准库 zlib 冲突，需要从路径 import
    spec = importlib.util.spec_from_file_location("zlib_script", SCRIPTS_DIR / "zlib.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    creds_file = tmp_path / "zlibrary_credentials.json"
    creds_file.write_text(
        json.dumps({"remix_userid": "uid_test", "remix_userkey": "key_test"})
    )
    monkeypatch.setattr(module, "CREDENTIALS_FILE", str(creds_file))
    monkeypatch.setattr(module, "DOWNLOAD_DIR", str(tmp_path / "books"))

    # 每条测试都从空缓存开始
    module._credentials = None
    module._opener = None
    return module


@pytest.fixture
def mock_opener(monkeypatch, zlib_module):
    """返回一个可编程的 opener，代替 urllib 真实请求。

    用法：
        mock_opener.queue = [b'{"success": 1, "books": []}']
        # 或：
        mock_opener.side_effect = [b'...', URLError('unreachable')]
    """

    class _MockResponse:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self, size=-1):
            if size == -1 or size >= len(self._payload):
                chunk, self._payload = self._payload, b""
                return chunk
            chunk, self._payload = self._payload[:size], self._payload[size:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _MockOpener:
        def __init__(self):
            self.queue: list = []
            self.calls: list = []

        def open(self, req, timeout=None):
            self.calls.append({"url": req.full_url, "method": req.get_method(), "timeout": timeout})
            if not self.queue:
                raise AssertionError("mock opener queue exhausted")
            item = self.queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return _MockResponse(item)

    opener = _MockOpener()
    monkeypatch.setattr(zlib_module, "_get_opener", lambda: opener)
    return opener
