import unittest

from typer.testing import CliRunner

from telegram_scraper.cli import app


class CliTests(unittest.TestCase):
    def test_help_exposes_node_and_theme_commands(self):
        runner = CliRunner()

        root_result = runner.invoke(app, ["--help"])
        self.assertEqual(root_result.exit_code, 0)
        self.assertNotIn("kg-cluster-topics", root_result.output)
        self.assertNotIn("kg-merge-topics", root_result.output)
        for command in (
            "kg-profile-upsert",
            "kg-profile-show",
            "kg-segment-preview",
            "kg-segment-worker",
            "kg-reset-channel",
            "kg-repair-channels",
            "kg-resegment-channel",
            "kg-resegment-channels",
            "kg-sync-status",
            "kg-themes-now",
            "kg-themes-emerging",
            "kg-themes-fading",
            "kg-themes-history",
            "kg-topics-now",
            "kg-topics-emerging",
            "kg-topics-fading",
            "kg-topic-history",
            "kg-events-list",
            "kg-people-list",
            "kg-nations-list",
            "kg-orgs-list",
            "kg-places-list",
            "kg-node-show",
            "viz-api",
        ):
            self.assertIn(command, root_result.output)

    def test_segment_worker_help_exposes_loop_options(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-segment-worker", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--loop", result.output)
        self.assertIn("Idle poll interval.", result.output)

    def test_node_show_help_exposes_kind_and_slug(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-node-show", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--kind", result.output)
        self.assertIn("--slug", result.output)

    def test_resegment_channels_help_exposes_repeatable_channel_and_workers(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-resegment-channels", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--channel", result.output)
        self.assertIn("--workers", result.output)

    def test_repair_channels_help_exposes_since_and_workers(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-repair-channels", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--channel", result.output)
        self.assertIn("--since", result.output)
        self.assertIn("--workers", result.output)


if __name__ == "__main__":
    unittest.main()
