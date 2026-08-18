import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.mitm_addon import extract_request_fingerprint
from app.mitm_capture import MitmCaptureService


class _Hdr(dict):
    def get(self, key, default=""):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class ExtractFingerprintTests(unittest.TestCase):
    def test_extracts_ua_query_and_cookies(self):
        url = (
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg"
            "&__biz=MzA%3D&devicetype=WindowsWechat"
            "&clientversion=0x63090a13&wxtoken=77"
        )
        headers = _Hdr(
            {
                "User-Agent": "WindowsWechat UA",
                "Cookie": "pass_ticket=pt; slave_sid=sid1; data_ticket=dt1; extra=no",
            }
        )
        fp = extract_request_fingerprint(url, headers)
        self.assertEqual(fp["user_agent"], "WindowsWechat UA")
        self.assertEqual(fp["devicetype"], "WindowsWechat")
        self.assertEqual(fp["clientversion"], "0x63090a13")
        self.assertEqual(fp["wxtoken"], "77")
        self.assertEqual(fp["slave_sid"], "sid1")
        self.assertEqual(fp["data_ticket"], "dt1")
        self.assertNotIn("extra", fp)

    def test_missing_headers_returns_empty(self):
        self.assertEqual(extract_request_fingerprint("", None), {})


class InboxReaderTests(unittest.TestCase):
    def test_read_new_credentials_keeps_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inbox = root / "data" / "capture_inbox.jsonl"
            inbox.parent.mkdir()
            row = {
                "__biz": "b",
                "uin": "1",
                "key": "k",
                "pass_ticket": "pt",
                "user_agent": "UA-1",
                "clientversion": "0x1",
                "slave_sid": "sid",
            }
            inbox.write_text(json.dumps(row) + "\n", encoding="utf-8")
            svc = MitmCaptureService(root)
            svc._inbox_offset = 0
            got = svc.read_new_credentials(consume=True)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["user_agent"], "UA-1")
            self.assertEqual(got[0]["clientversion"], "0x1")
            self.assertEqual(got[0]["slave_sid"], "sid")


if __name__ == "__main__":
    unittest.main()
