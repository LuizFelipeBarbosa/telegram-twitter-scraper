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
        # Removed segment-based commands must not appear.
        self.assertNotIn("kg-segment-preview", root_result.output)
        self.assertNotIn("kg-segment-worker", root_result.output)
        self.assertNotIn("kg-resegment-channel", root_result.output)
        self.assertNotIn("kg-resegment-channels", root_result.output)
        for command in (
            "kg-profile-upsert",
            "kg-profile-show",
            "kg-process-worker",
            "kg-reset-channel",
            "kg-repair-channels",
            "kg-rebuild-event-hierarchy",
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

    def test_process_worker_help_exposes_loop_options(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-process-worker", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--loop", result.output)
        self.assertIn("Idle poll interval.", result.output)

    def test_process_worker_help_exposes_all_flags(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-process-worker", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--consumer", result.output)
        self.assertIn("--batch-size", result.output)
        self.assertIn("--loop", result.output)
        self.assertIn("--poll-interval-secon", result.output)  # may be truncated in narrow help output

    def test_node_show_help_exposes_kind_and_slug(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-node-show", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--kind", result.output)
        self.assertIn("--slug", result.output)

    def test_events_list_help_exposes_include_children_toggle(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-events-list", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--include-children", result.output)

    def test_repair_channels_help_exposes_since_and_workers(self):
        runner = CliRunner()

        result = runner.invoke(app, ["kg-repair-channels", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--channel", result.output)
        self.assertIn("--since", result.output)
        self.assertIn("--workers", result.output)


if __name__ == "__main__":
    unittest.main()
