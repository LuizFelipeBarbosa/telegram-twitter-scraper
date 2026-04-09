import unittest

from typer.testing import CliRunner

from telegram_scraper.cli import app


class CliTests(unittest.TestCase):
    def test_help_does_not_expose_topic_reindexing(self):
        runner = CliRunner()

        root_result = runner.invoke(app, ["--help"])
        self.assertEqual(root_result.exit_code, 0)
        self.assertNotIn("reindex-topics", root_result.output)

        for command in ("sync-all", "sync-chat", "backfill", "repair-media"):
            result = runner.invoke(app, [command, "--help"])
            self.assertEqual(result.exit_code, 0)
            self.assertNotIn("--reindex", result.output)


if __name__ == "__main__":
    unittest.main()
