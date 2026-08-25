import unittest

from app.batch_import import (
    BATCH_IMPORT_EXAMPLE,
    BATCH_IMPORT_HELP,
    BATCH_IMPORT_HINT,
    parse_batch_import,
)


class BatchImportFormatTests(unittest.TestCase):
    def test_help_shows_columns_and_example(self):
        self.assertIn("公众号", BATCH_IMPORT_HINT)
        self.assertIn("文章链接", BATCH_IMPORT_HINT)
        self.assertIn("CSV", BATCH_IMPORT_HINT)
        self.assertIn("mp.weixin.qq.com", BATCH_IMPORT_EXAMPLE)
        self.assertIn("公众号,文章链接", BATCH_IMPORT_HELP)
        self.assertIn(BATCH_IMPORT_EXAMPLE, BATCH_IMPORT_HELP)

    def test_parse_skips_header_and_reads_row(self):
        rows, errors = parse_batch_import(
            "公众号,文章链接\n"
            f"{BATCH_IMPORT_EXAMPLE}\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "数模加油站")


if __name__ == "__main__":
    unittest.main()
