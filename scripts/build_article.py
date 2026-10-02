"""Build docs/study/article.html from the notebook exports in docs/study/data/.

Run after scripts/run_notebooks.sh:  uv run python scripts/build_article.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "docs" / "study"
DATA = STUDY / "data"
ORDER = ["presstv", "irna-en", "idfofficial", "iltvnews", "thetimesofisrael2022", "jewishbreakingnewstelegram"]


def build_data() -> dict:
    daily_df = pd.read_csv(DATA / "02_daily_timelines.csv")
    daily_df["date"] = pd.to_datetime(daily_df["date"]).dt.strftime("%Y-%m-%d")
    dates = sorted(daily_df["date"].unique())
    counts = daily_df.groupby(["channel_slug", "date"])["posts"].sum()
    daily = {s: [int(counts.get((s, d), 0)) for d in dates] for s in ORDER}

    rates_df = pd.read_csv(DATA / "02_rates_full.csv").set_index("channel_slug")
    rates = {
        s: [round(rates_df.loc[s, "posts_per_day"], 1), round(rates_df.loc[s, "ci_low"], 1),
            round(rates_df.loc[s, "ci_high"], 1), int(rates_df.loc[s, "n_posts"])]
        for s in ORDER
    }

    comm_df = pd.read_csv(DATA / "03_commemoration.csv")
    comm = {
        measure: {
            row.channel_slug: [round(row.share * 100, 2), round(max(row.ci_low, 0) * 100, 2),
                               round(row.ci_high * 100, 2), int(row.successes), int(row.n)]
            for row in group.itertuples()
        }
        for measure, group in comm_df.groupby("measure")
    }

    tri_df = pd.read_csv(DATA / "04_triangle_network.csv")
    tri = {
        row.channel_slug: [round(row.share * 100, 1), round(row.ci_low * 100, 1), round(row.ci_high * 100, 1)]
        for row in tri_df[tri_df["measure"] == "triangle"].itertuples()
    }

    ratios = pd.read_csv(DATA / "02_rate_ratios.csv").to_dict("records")
    return {"dates": dates, "daily": daily, "rates": rates, "comm": comm, "tri": tri, "ratios": ratios}


def main() -> None:
    template = (STUDY / "article_template.html").read_text(encoding="utf-8")
    html = template.replace("__DATA__", json.dumps(build_data()))
    out = STUDY / "article.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
