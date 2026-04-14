import unittest

from typer.testing import CliRunner

from telegram_scraper.cli import app


class CliTests(unittest.TestCase):
    def test_help_exposes_archive_commands_only(self):
        runner = CliRunner()

        result = runner.invoke(app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        for command in (
            "login",
            "list-chats",
            "sync-all",
            "sync-chat",
            "backfill",
            "repair-media",
        ):
            self.assertIn(command, result.output)

        for removed in (
            "kg-profile-upsert",
            "kg-process-worker",
            "kg-themes-now",
            "kg-node-show",
            "viz-api",
        ):
            self.assertNotIn(removed, result.output)

    def test_sync_chat_help_exposes_chat_option(self):
        runner = CliRunner()

        result = runner.invoke(app, ["sync-chat", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--chat", result.output)

    def test_backfill_help_exposes_limit_option(self):
        runner = CliRunner()

        result = runner.invoke(app, ["backfill", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--limit", result.output)

    def test_repair_media_help_exposes_optional_chat_selector(self):
        runner = CliRunner()

        result = runner.invoke(app, ["repair-media", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--chat", result.output)


if __name__ == "__main__":
    unittest.main()
