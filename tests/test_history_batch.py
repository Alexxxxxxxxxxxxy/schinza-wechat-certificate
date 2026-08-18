import unittest

from app.history_batch import fetch_history_batch


def _acc(i: str, *, active: bool = True, cred: bool = True) -> dict:
    credentials = {"__biz": f"b{i}", "uin": "1", "key": "k"} if cred else {}
    return {
        "id": i,
        "name": f"号{i}",
        "credentials": credentials,
        "active": active,
    }


class HistoryBatchTests(unittest.TestCase):
    def test_skips_inactive_then_fetches_next(self):
        calls: list[str] = []

        def fetch_one(cred, **_kw):
            calls.append(cred["__biz"])
            return {
                "ok": True,
                "articles": [{"title": "t", "identity": cred["__biz"]}],
                "pages": 1,
                "stopped_reason": "completed",
            }

        sleeps: list[float] = []
        result = fetch_history_batch(
            [_acc("1", active=False), _acc("2")],
            fetch_one=fetch_one,
            sleep_fn=sleeps.append,
            between_s=(0.0, 0.0),
            extra_after_rate_limit_s=0.0,
        )
        self.assertEqual(calls, ["b2"])
        self.assertEqual(result["groups"][0]["status"], "expired")
        self.assertEqual(result["groups"][1]["status"], "completed")
        self.assertEqual(result["summary"]["expired"], 1)
        self.assertEqual(result["summary"]["completed"], 1)
        self.assertEqual(result["summary"]["articles"], 1)

    def test_rate_limit_keeps_articles_and_continues(self):
        def fetch_one(cred, **_kw):
            if cred["__biz"] == "b1":
                return {
                    "ok": False,
                    "articles": [{"title": "partial", "identity": "p"}],
                    "pages": 2,
                    "error": "unknownerror",
                    "stopped_reason": "rate_limited",
                }
            return {
                "ok": True,
                "articles": [{"title": "ok", "identity": "o"}],
                "pages": 1,
                "stopped_reason": "completed",
            }

        sleeps: list[float] = []
        result = fetch_history_batch(
            [_acc("1"), _acc("2")],
            fetch_one=fetch_one,
            sleep_fn=sleeps.append,
            between_s=(3.0, 3.0),
            extra_after_rate_limit_s=15.0,
        )
        self.assertEqual(result["groups"][0]["status"], "rate_limited")
        self.assertEqual(len(result["groups"][0]["articles"]), 1)
        self.assertEqual(result["groups"][1]["status"], "completed")
        self.assertTrue(any(s >= 18.0 for s in sleeps))

    def test_cancel_skips_remaining_without_fetch(self):
        calls: list[str] = []
        cancelled = {"n": 0}

        def should_cancel():
            return cancelled["n"] >= 1

        def fetch_one(cred, **_kw):
            calls.append(cred["__biz"])
            cancelled["n"] += 1
            return {
                "ok": False,
                "cancelled": True,
                "articles": [],
                "pages": 0,
                "error": "已取消",
                "stopped_reason": "cancelled",
            }

        result = fetch_history_batch(
            [_acc("1"), _acc("2"), _acc("3")],
            fetch_one=fetch_one,
            should_cancel=should_cancel,
            sleep_fn=lambda _s: None,
            between_s=(0.0, 0.0),
        )
        self.assertEqual(calls, ["b1"])
        self.assertEqual(result["groups"][1]["status"], "cancelled")
        self.assertEqual(result["groups"][2]["status"], "cancelled")
        self.assertTrue(result["cancelled"])
        self.assertTrue(result["ok"])

    def test_progress_callback_indexes(self):
        seen: list[tuple[int, int, str]] = []

        def fetch_one(_cred, **kw):
            cb = kw.get("on_progress")
            if cb:
                cb("第 1 页")
            return {"ok": True, "articles": [], "pages": 1, "stopped_reason": "completed"}

        fetch_history_batch(
            [_acc("1"), _acc("2")],
            fetch_one=fetch_one,
            on_progress=lambda i, n, name, msg: seen.append((i, n, name)),
            sleep_fn=lambda _s: None,
            between_s=(0.0, 0.0),
        )
        self.assertEqual(seen[0], (1, 2, "号1"))
        self.assertEqual(seen[-1][0], 2)


if __name__ == "__main__":
    unittest.main()
