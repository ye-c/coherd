import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from coherd.id_gen import next_id


class TestIdGen(unittest.TestCase):
    def test_ac1_default_explicit_seq(self):
        now = datetime(2026, 11, 20, 0, 31, 53, tzinfo=timezone.utc)
        self.assertEqual(next_id("ws", now), "ws-20261120003153-01")
        self.assertEqual(next_id("ws", now, seq=3), "ws-20261120003153-03")
        self.assertEqual(next_id("ws", now, seq=12), "ws-20261120003153-12")

    def test_ac2_invalid_seq_raises(self):
        now = datetime(2026, 11, 20, 0, 31, 53, tzinfo=timezone.utc)
        for bad in [0, 100, -1, 1.5, "1", None]:
            with self.assertRaises(ValueError):
                next_id("ws", now, seq=bad)

    @patch("coherd.id_gen.Path", create=True)
    @patch("coherd.id_gen.os", create=True)
    @patch("builtins.open")
    def test_ac3_pure_function(self, mock_open, mock_os, mock_path):
        mock_open.side_effect = RuntimeError("IO forbidden")
        mock_path.glob.side_effect = RuntimeError("IO forbidden")
        now = datetime(2026, 11, 20, 0, 31, 53, tzinfo=timezone.utc)
        self.assertEqual(next_id("ws", now, 1), "ws-20261120003153-01")

    def test_ac8_sort_order_mixed(self):
        ids = [
            "w37-20261120000001-01",
            "w37-20261120000000",
        ]
        sorted_ids = sorted(ids)
        self.assertEqual(sorted_ids, [
            "w37-20261120000000",
            "w37-20261120000001-01",
        ])

    def test_ac11_invalid_ws_raises(self):
        now = datetime(2026, 11, 20, 0, 31, 53, tzinfo=timezone.utc)
        for bad_ws in ["a/b", "a b", "w$!", "../w"]:
            with self.assertRaises(ValueError):
                next_id(bad_ws, now)

if __name__ == "__main__":
    unittest.main()
