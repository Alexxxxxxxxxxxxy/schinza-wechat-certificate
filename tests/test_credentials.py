import unittest

from app.credentials import (
    OPTIONAL,
    credentials_enough,
    credentials_to_json,
    normalize_credentials,
)


class CredentialsFingerprintTests(unittest.TestCase):
    def test_enough_still_only_requires_biz_uin_key(self):
        self.assertTrue(
            credentials_enough({"__biz": "b", "uin": "1", "key": "k"})
        )

    def test_normalize_keeps_fingerprint_keys(self):
        cred = normalize_credentials(
            {
                "__biz": "b",
                "uin": "1",
                "key": "k",
                "user_agent": "MicroMessenger/8.0",
                "devicetype": "windowswechat",
                "clientversion": "0x63090a13",
                "wxtoken": "wt",
                "slave_sid": "sid",
                "data_ticket": "dt",
                "noise": "drop-me",
            }
        )
        self.assertEqual(cred["user_agent"], "MicroMessenger/8.0")
        self.assertEqual(cred["devicetype"], "windowswechat")
        self.assertEqual(cred["clientversion"], "0x63090a13")
        self.assertEqual(cred["slave_sid"], "sid")
        self.assertEqual(cred["data_ticket"], "dt")
        self.assertNotIn("noise", cred)

    def test_normalize_drops_empty_optional(self):
        cred = normalize_credentials(
            {"__biz": "b", "uin": "1", "key": "k", "user_agent": "  "}
        )
        self.assertNotIn("user_agent", cred)

    def test_json_includes_fingerprint_when_present(self):
        text = credentials_to_json(
            {"__biz": "b", "uin": "1", "key": "k", "user_agent": "UA"}
        )
        self.assertIn("user_agent", text)
        self.assertIn("UA", text)

    def test_optional_declares_new_keys(self):
        for key in (
            "user_agent",
            "devicetype",
            "clientversion",
            "wxtoken",
            "slave_sid",
            "data_ticket",
        ):
            self.assertIn(key, OPTIONAL)


if __name__ == "__main__":
    unittest.main()
