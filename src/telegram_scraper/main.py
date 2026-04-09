from __future__ import annotations

from telegram_scraper.cli import app


def main() -> None:
    if app is None:
        raise SystemExit("Typer is not installed. Install project dependencies before using the CLI.")
    app()


if __name__ == "__main__":
    main()
