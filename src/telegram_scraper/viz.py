"""House chart style (matplotlib + Plotly) and chart builders for the story notebooks.

Conventions
-----------
* Iran = warm hues (Press TV deep crimson, IRNA amber); Israel = cool hues (IDF navy, ILTV teal,
  ToI blue, JBN slate). Ownership is carried by line style / marker: state = solid line + filled
  marker, private = dashed line + hollow marker.
* Titles state the finding (callers pass the sentence; build it from computed numbers).
* Every saved figure carries a source line under the chart.
* ``save(fig, name)`` writes ``docs/study/figures/<name>.png`` (dpi 200) for matplotlib figures and
  ``docs/study/interactive/<name>.html`` (``include_plotlyjs="cdn"``) for Plotly figures;
  ``export_data(df, name)`` writes the tidy data behind a figure to ``docs/study/data/<name>.csv``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.lines import Line2D

from telegram_scraper.study import (
    CHANNELS,
    CHANNEL_ORDER,
    EXPORT_DATA_DIR,
    FIGURES_DIR,
    INTERACTIVE_DIR,
    SHORT_NAMES,
)

INK = "#1D2733"
MUTED = "#6B7683"
GRID = "#E3E6EA"
PAPER = "#FFFFFF"
ACCENT = "#9B1B30"
FONT_STACK = ["Arial", "Helvetica Neue", "DejaVu Sans"]
SOURCE_LINE = (
    "Source: Telegram channel snapshot, 28 Feb - 17 Apr 2026 (UTC). A post = one message or one album. "
    "Analysis: telegram-twitter-scraper."
)
STATE_OWNERSHIP = "state"

CHANNEL_COLORS = {slug: meta["color"] for slug, meta in CHANNELS.items()}
OWNERSHIP_COLORS = {"state": "#2B2F36", "private": "#8A929C"}
COUNTRY_COLORS = {"Iran": "#C0392B", "Israel": "#2E6DA4"}

# Sequential map used for heat strips / heatmaps: paper white -> deep ink-blue.
SEQ_CMAP = LinearSegmentedColormap.from_list("study_seq", ["#F7F4EE", "#F2D7A6", "#E39A55", "#B8473A", "#5B1A2B"])
DIV_CMAP = LinearSegmentedColormap.from_list("study_div", ["#1F5F8B", "#8FB8D6", "#F7F7F5", "#E5A27E", "#9B1B30"])


# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------


def apply_style() -> None:
    """Install the house rcParams (idempotent). Inline figures are 100 dpi, saved PNGs 200 dpi."""
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "font.size": 10,
            "text.color": INK,
            "axes.edgecolor": "#B8BEC6",
            "axes.labelcolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "axes.facecolor": PAPER,
            "grid.color": GRID,
            "grid.linewidth": 0.7,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "figure.facecolor": PAPER,
            "figure.dpi": 100,
            "savefig.dpi": 200,
            "savefig.facecolor": PAPER,
            "savefig.bbox": "tight",
            "figure.max_open_warning": 40,
        }
    )


def style(slug: str) -> dict[str, Any]:
    """Line / marker style of a channel: state = solid + filled, private = dashed + hollow."""
    color = CHANNEL_COLORS[slug]
    state = CHANNELS[slug]["ownership"] == STATE_OWNERSHIP
    return {
        "color": color,
        "linestyle": "-" if state else (0, (4, 2)),
        "marker": "o" if state else "o",
        "markerfacecolor": color if state else "white",
        "markeredgecolor": color,
        "markeredgewidth": 1.6,
    }


def channel_handles(slugs: Sequence[str] | None = None, *, kind: str = "line") -> list[Line2D]:
    slugs = list(slugs or CHANNEL_ORDER)
    handles = []
    for slug in slugs:
        st = style(slug)
        label = f"{SHORT_NAMES[slug]} ({CHANNELS[slug]['ownership']})"
        if kind == "patch":
            handles.append(plt.Rectangle((0, 0), 1, 1, color=st["color"], label=label))
        else:
            handles.append(Line2D([0], [0], label=label, lw=2, markersize=7, **st))
    return handles


def channel_legend(ax: Any, slugs: Sequence[str] | None = None, *, kind: str = "line", **kwargs: Any) -> Any:
    return ax.legend(handles=channel_handles(slugs, kind=kind), **kwargs)


def headline(fig: Any, title: str, subtitle: str | None = None, *, wrap: int = 105, y: float = 1.02) -> None:
    """Left-aligned finding-style title (bold) with an optional grey subtitle."""
    title = "\n".join(textwrap.wrap(title, wrap)) or title
    fig.text(0.0, y, title, ha="left", va="bottom", fontsize=14, fontweight="bold", color=INK, transform=fig.transFigure)
    if subtitle:
        sub = "\n".join(textwrap.wrap(subtitle, int(wrap * 1.25)))
        fig.text(0.0, y - 0.005, sub, ha="left", va="top", fontsize=9.5, color=MUTED, fontweight="normal", transform=fig.transFigure)


def footer(fig: Any, note: str | None = None, *, y: float = -0.02) -> None:
    """Source line under the chart (plus an optional method note on a line above it)."""
    text = SOURCE_LINE if not note else f"{note}\n{SOURCE_LINE}"
    fig.text(0.0, y, text, ha="left", va="top", fontsize=7.5, color=MUTED, transform=fig.transFigure)


def shade_ownership_label(ax: Any, slug: str, *, axis: str = "y") -> None:
    """Colour the tick label of ``slug`` with its channel colour (call after setting tick labels)."""
    labels = ax.get_yticklabels() if axis == "y" else ax.get_xticklabels()
    for label in labels:
        if label.get_text() in (SHORT_NAMES[slug], CHANNELS[slug]["name"]):
            label.set_color(CHANNEL_COLORS[slug])
            label.set_fontweight("bold")


def color_channel_ticklabels(ax: Any, *, axis: str = "y") -> None:
    labels = ax.get_yticklabels() if axis == "y" else ax.get_xticklabels()
    reverse = {meta["short"]: slug for slug, meta in CHANNELS.items()}
    for label in labels:
        slug = reverse.get(label.get_text())
        if slug:
            label.set_color(CHANNEL_COLORS[slug])
            label.set_fontweight("bold")


# ---------------------------------------------------------------------------
# Saving / exporting
# ---------------------------------------------------------------------------


def save(fig: Any, name: str, *, note: str | None = None, source: bool = True) -> Path:
    """Save a matplotlib figure to ``figures/<name>.png`` (dpi 200) or a Plotly figure to ``interactive/<name>.html``."""
    if hasattr(fig, "write_html"):  # Plotly
        INTERACTIVE_DIR.mkdir(parents=True, exist_ok=True)
        path = INTERACTIVE_DIR / f"{name}.html"
        fig.write_html(str(path), include_plotlyjs="cdn", full_html=True)
        return path
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    if source:
        footer(fig, note)
    path = FIGURES_DIR / f"{name}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=PAPER)
    return path


def export_data(df: pd.DataFrame, name: str) -> Path:
    """Write the tidy data behind a figure to ``docs/study/data/<name>.csv`` (UTF-8, no index)."""
    EXPORT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DATA_DIR / f"{name}.csv"
    frame = df.reset_index(drop=True) if not isinstance(df.index, pd.RangeIndex) or df.index.name else df
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def done(fig: Any, name: str, df: pd.DataFrame | None = None, *, note: str | None = None) -> None:
    """Save figure + data, then close the inline figure after it has been displayed."""
    save(fig, name, note=note)
    if df is not None:
        export_data(df, name)
    from IPython.display import display

    display(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Matplotlib chart builders
# ---------------------------------------------------------------------------


def dot_whisker(
    ax: Any,
    df: pd.DataFrame,
    *,
    label_col: str,
    est_col: str,
    lo_col: str,
    hi_col: str,
    slug_col: str | None = "channel_slug",
    log: bool = False,
    ref: float | None = None,
    value_fmt: str = "{:.1f}",
    xlabel: str | None = None,
    annotate: bool = True,
) -> None:
    """Horizontal dot-and-whisker plot. Rows are drawn top-to-bottom in the order of ``df``."""
    frame = df.reset_index(drop=True)
    ypos = np.arange(len(frame))[::-1]
    for y, row in zip(ypos, frame.itertuples(index=False)):
        slug = getattr(row, slug_col) if slug_col else None
        st = style(slug) if slug else {"color": INK, "markerfacecolor": INK, "markeredgecolor": INK, "markeredgewidth": 1.6}
        est, lo, hi = getattr(row, est_col), getattr(row, lo_col), getattr(row, hi_col)
        ax.plot([lo, hi], [y, y], color=st["color"], lw=2.2, solid_capstyle="round", zorder=2)
        ax.plot(
            [est],
            [y],
            marker="o",
            markersize=9,
            markerfacecolor=st["markerfacecolor"],
            markeredgecolor=st["markeredgecolor"],
            markeredgewidth=st["markeredgewidth"],
            linestyle="none",
            zorder=3,
        )
        if annotate:
            ax.annotate(
                value_fmt.format(est),
                (1.0, y),
                xycoords=("axes fraction", "data"),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                fontsize=8.5,
                color=MUTED,
                annotation_clip=False,
            )
    ax.set_yticks(ypos)
    ax.set_yticklabels(frame[label_col])
    if log:
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    if ref is not None:
        ax.axvline(ref, color=MUTED, lw=1, ls=":", zorder=1)
    ax.grid(axis="y", visible=False)
    ax.set_ylim(-0.7, len(frame) - 0.3)
    if xlabel:
        ax.set_xlabel(xlabel)
    color_channel_ticklabels(ax)


def event_key(events: Sequence[Mapping[str, Any]]) -> str:
    """Text key for the numbered event markers drawn by :func:`timeline_small_multiples`."""
    return "Events: " + "   ".join(f"({i}) {e['short']} {pd.Timestamp(e['date']):%d %b}" for i, e in enumerate(events, start=1))


def timeline_small_multiples(
    daily: pd.DataFrame,
    events: Sequence[Mapping[str, Any]],
    *,
    value_label: str = "posts per day",
    slugs: Sequence[str] | None = None,
    ncols: int = 2,
    smooth: int = 3,
    sharey: bool = False,
    figsize: tuple[float, float] | None = None,
) -> Any:
    """One panel per channel: daily bars + rolling mean line, vertical event markers.

    ``daily`` is indexed by date with one column per channel slug.
    """
    slugs = [s for s in (slugs or CHANNEL_ORDER) if s in daily.columns]
    nrows = int(np.ceil(len(slugs) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize or (5.6 * ncols, 2.15 * nrows), sharex=True, sharey=sharey)
    axes = np.atleast_1d(axes).ravel()
    for ax, slug in zip(axes, slugs):
        st = style(slug)
        series = daily[slug]
        ax.bar(series.index, series.values, width=0.85, color=st["color"], alpha=0.28, linewidth=0)
        rolling = series.rolling(smooth, center=True, min_periods=1).mean()
        ax.plot(rolling.index, rolling.values, color=st["color"], lw=2, ls=st["linestyle"])
        ax.set_title(f"{CHANNELS[slug]['name']}  ({CHANNELS[slug]['ownership']}, {CHANNELS[slug]['country']})", fontsize=10, color=st["color"])
        for event in events:
            ax.axvline(pd.Timestamp(event["date"], tz="UTC"), color=INK, lw=0.8, ls=":", alpha=0.7)
        ax.grid(axis="x", visible=False)
        ax.tick_params(axis="x", labelsize=8)
    for ax in axes[len(slugs) :]:
        ax.set_visible(False)
    for ax in axes[: len(slugs)]:
        ymax = ax.get_ylim()[1]
        for index, event in enumerate(events, start=1):
            ax.annotate(
                str(index),
                (pd.Timestamp(event["date"], tz="UTC"), ymax),
                xytext=(0, -2),
                textcoords="offset points",
                fontsize=7,
                color="white",
                ha="center",
                va="top",
                bbox={"boxstyle": "circle,pad=0.18", "fc": INK, "ec": "none"},
            )
    for ax in axes[:: ncols]:
        ax.set_ylabel(value_label, fontsize=8.5)
    import matplotlib.dates as mdates

    axes[0].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.SU, interval=1))
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout(h_pad=1.6)
    return fig


def heat_strips(
    matrix: pd.DataFrame,
    ax: Any,
    *,
    cmap: Any = SEQ_CMAP,
    xlabel: str = "hour of day",
    colorbar_label: str | None = None,
    vmax: float | None = None,
) -> Any:
    """Rows = channels (index slugs), columns = hours; one strip per channel."""
    values = matrix.to_numpy(dtype=float)
    image = ax.imshow(values, aspect="auto", cmap=cmap, vmin=0, vmax=vmax or np.nanmax(values), interpolation="nearest")
    ax.set_yticks(range(len(matrix)))
    ax.set_yticklabels([SHORT_NAMES.get(slug, slug) for slug in matrix.index])
    ax.set_xticks(range(0, matrix.shape[1], 3))
    ax.set_xticklabels([str(c) for c in matrix.columns[::3]])
    ax.set_xlabel(xlabel)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    color_channel_ticklabels(ax)
    if colorbar_label:
        cbar = plt.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
        cbar.set_label(colorbar_label, fontsize=8.5)
        cbar.outline.set_visible(False)
    return image


def ridgeline(
    ax: Any,
    samples: Mapping[str, Sequence[float]],
    *,
    xlim: tuple[float, float] = (-1, 1),
    overlap: float = 0.85,
    means: Mapping[str, tuple[float, float, float]] | None = None,
    bw: float = 0.25,
    xlabel: str = "",
) -> None:
    """Ridgeline of per-channel distributions (KDE). ``means`` maps slug -> (mean, lo, hi) markers."""
    from scipy.stats import gaussian_kde

    grid = np.linspace(xlim[0], xlim[1], 400)
    slugs = [s for s in CHANNEL_ORDER if s in samples]
    densities = {}
    for slug in slugs:
        values = np.asarray(pd.Series(samples[slug]).dropna(), dtype=float)
        kde = gaussian_kde(values, bw_method=bw)
        densities[slug] = kde(grid)
    peak = max(d.max() for d in densities.values())
    for index, slug in enumerate(slugs):
        base = (len(slugs) - 1 - index)
        density = densities[slug] / peak * overlap
        st = style(slug)
        ax.fill_between(grid, base, base + density, color=st["color"], alpha=0.35 if CHANNELS[slug]["ownership"] == "state" else 0.18, zorder=2 + index * 0.1)
        ax.plot(grid, base + density, color=st["color"], lw=1.8, ls=st["linestyle"], zorder=3 + index * 0.1)
        ax.axhline(base, color=GRID, lw=0.8, zorder=1)
        if means and slug in means:
            mean, lo, hi = means[slug]
            ax.plot([lo, hi], [base + 0.04] * 2, color=INK, lw=3, solid_capstyle="round", zorder=5)
            ax.plot([mean], [base + 0.04], marker="D", color="white", markeredgecolor=INK, markersize=5.5, zorder=6)
    ax.set_yticks([len(slugs) - 1 - i for i in range(len(slugs))])
    ax.set_yticklabels([SHORT_NAMES[s] for s in slugs])
    color_channel_ticklabels(ax)
    ax.axvline(0, color=MUTED, lw=0.8, ls=":")
    ax.set_xlim(*xlim)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(xlabel)


def annotated_heatmap(
    ax: Any,
    matrix: pd.DataFrame,
    *,
    cmap: Any = SEQ_CMAP,
    fmt: str = "{:.0%}",
    vmin: float | None = None,
    vmax: float | None = None,
    center: float | None = None,
    min_label: float = 0.0,
    cbar_label: str | None = None,
    rotate: int = 0,
) -> Any:
    values = matrix.to_numpy(dtype=float)
    if center is not None:
        span = max(abs(np.nanmin(values) - center), abs(np.nanmax(values) - center)) if vmax is None else vmax
        vmin, vmax = center - span, center + span
    image = ax.imshow(values, aspect="auto", cmap=cmap, vmin=vmin if vmin is not None else 0, vmax=vmax if vmax is not None else np.nanmax(values))
    ax.set_xticks(range(matrix.shape[1]))
    ax.set_xticklabels(matrix.columns, rotation=rotate, ha="right" if rotate else "center")
    ax.set_yticks(range(matrix.shape[0]))
    ax.set_yticklabels(matrix.index)
    ax.grid(False)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    norm_mid = (image.norm.vmin + image.norm.vmax) / 2
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            value = values[i, j]
            if np.isnan(value) or abs(value) < min_label:
                continue
            dark = (value - image.norm.vmin) / max(image.norm.vmax - image.norm.vmin, 1e-12) > 0.55
            ax.text(j, i, fmt.format(value), ha="center", va="center", fontsize=8, color="white" if dark else INK)
    if cbar_label:
        cbar = plt.colorbar(image, ax=ax, fraction=0.025, pad=0.02)
        cbar.set_label(cbar_label, fontsize=8.5)
        cbar.outline.set_visible(False)
    del norm_mid
    return image


def dumbbell(
    ax: Any,
    df: pd.DataFrame,
    *,
    label_col: str,
    start_col: str,
    end_col: str,
    start_label: str,
    end_label: str,
    slug_col: str | None = "channel_slug",
    value_fmt: str = "{:.2f}",
) -> None:
    frame = df.reset_index(drop=True)
    ypos = np.arange(len(frame))[::-1]
    for y, row in zip(ypos, frame.itertuples(index=False)):
        slug = getattr(row, slug_col) if slug_col else None
        color = CHANNEL_COLORS.get(slug, INK)
        a, b = getattr(row, start_col), getattr(row, end_col)
        ax.plot([a, b], [y, y], color=color, lw=2.4, alpha=0.55, zorder=2)
        ax.scatter([a], [y], s=70, facecolor="white", edgecolor=color, linewidth=1.8, zorder=3)
        ax.scatter([b], [y], s=70, facecolor=color, edgecolor=color, linewidth=1.8, zorder=3)
        ax.annotate(value_fmt.format(a), (a, y), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=7.5, color=MUTED)
        ax.annotate(value_fmt.format(b), (b, y), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=7.5, color=MUTED)
    ax.set_yticks(ypos)
    ax.set_yticklabels(frame[label_col])
    ax.grid(axis="y", visible=False)
    ax.set_ylim(-0.7, len(frame) - 0.2)
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor=INK, markersize=8, label=start_label),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=INK, markeredgecolor=INK, markersize=8, label=end_label),
    ]
    ax.legend(handles=handles, loc="lower right")
    color_channel_ticklabels(ax)


def stacked_share_bars(
    ax: Any,
    shares: pd.DataFrame,
    *,
    colors: Mapping[str, str],
    label_min: float = 0.04,
    order: Sequence[str] | None = None,
) -> None:
    """Horizontal 100% stacked bars. ``shares`` rows = channel slugs, columns = categories (rows sum to 1)."""
    order = list(order or shares.index)
    left = np.zeros(len(order))
    ypos = np.arange(len(order))[::-1]
    for category in shares.columns:
        widths = shares.loc[order, category].to_numpy(dtype=float)
        ax.barh(ypos, widths, left=left, color=colors[category], edgecolor="white", linewidth=1.2, label=category, height=0.68)
        for y, width, start in zip(ypos, widths, left):
            if width >= label_min:
                ax.text(start + width / 2, y, f"{width:.0%}", ha="center", va="center", fontsize=8.3, color="white", fontweight="bold")
        left += widths
    ax.set_yticks(ypos)
    ax.set_yticklabels([SHORT_NAMES.get(s, s) for s in order])
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.grid(axis="y", visible=False)
    color_channel_ticklabels(ax)
    ax.legend(ncol=len(shares.columns), loc="upper center", bbox_to_anchor=(0.5, 1.12), handlelength=1.2)


def umap_map(
    ax: Any,
    coords: np.ndarray,
    slugs: Sequence[str],
    *,
    labels: Mapping[int, tuple[float, float, str]] | None = None,
    point_size: float = 4.0,
    alpha: float = 0.45,
) -> None:
    """Scatter of every post in 2-D, coloured by channel (state hollow-ish, private filled lighter)."""
    slugs = np.asarray(slugs)
    order = [s for s in CHANNEL_ORDER[::-1] if (slugs == s).any()]  # draw Press TV (largest) first
    big_first = sorted(order, key=lambda s: -(slugs == s).sum())
    for slug in big_first:
        mask = slugs == slug
        ax.scatter(coords[mask, 0], coords[mask, 1], s=point_size, color=CHANNEL_COLORS[slug], alpha=alpha, linewidths=0, rasterized=True)
    if labels:
        for _, (x, y, text) in labels.items():
            ax.annotate(
                text,
                (x, y),
                fontsize=7.2,
                color=INK,
                ha="center",
                va="center",
                bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.8},
            )
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)


def circular_network(
    ax: Any,
    nodes: Sequence[str],
    weights: Mapping[tuple[str, str], float],
    *,
    node_size: Mapping[str, float] | None = None,
    node_color: Mapping[str, str] | None = None,
    edge_label_min: float | None = None,
    label_fmt: str = "{:.1%}",
) -> None:
    """Chord-style circular network: node area ~ ``node_size``, edge width ~ ``weights``."""
    n = len(nodes)
    angles = np.linspace(np.pi / 2, np.pi / 2 + 2 * np.pi, n, endpoint=False)
    pos = {node: (np.cos(a), np.sin(a)) for node, a in zip(nodes, angles)}
    max_w = max(weights.values()) if weights else 1.0
    from matplotlib.patches import FancyArrowPatch

    for (a, b), weight in sorted(weights.items(), key=lambda kv: kv[1]):
        if weight <= 0:
            continue
        patch = FancyArrowPatch(
            pos[a],
            pos[b],
            connectionstyle="arc3,rad=0.22",
            arrowstyle="-",
            linewidth=0.8 + 11 * weight / max_w,
            color=INK,
            alpha=0.22 + 0.4 * weight / max_w,
            zorder=1,
        )
        ax.add_patch(patch)
        if edge_label_min is not None and weight >= edge_label_min:
            mx, my = (pos[a][0] + pos[b][0]) / 2 * 0.78, (pos[a][1] + pos[b][1]) / 2 * 0.78
            ax.text(mx, my, label_fmt.format(weight), fontsize=7.5, ha="center", va="center", color=INK, bbox={"fc": "white", "ec": "none", "alpha": 0.8, "pad": 1})
    sizes = node_size or {node: 1.0 for node in nodes}
    max_size = max(sizes.values())
    for node in nodes:
        x, y = pos[node]
        ax.scatter([x], [y], s=250 + 1400 * sizes[node] / max_size, color=(node_color or {}).get(node, INK), zorder=3, edgecolor="white", linewidth=1.5)
        ax.annotate(node, (x, y), xytext=(x * 1.28 - x, y * 1.28 - y), textcoords="offset points", ha="center", va="center", fontsize=9.5, fontweight="bold", color=INK)
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.45, 1.45)
    ax.set_aspect("equal")
    ax.axis("off")


def quadrant_panel(
    fig: Any,
    cells: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    row_labels: Sequence[str] = ("state", "private"),
    col_labels: Sequence[str] = ("Iran", "Israel"),
    metrics: Sequence[tuple[str, str, str]] = (),
) -> None:
    """2 x 2 ownership x country summary. ``cells[(ownership, country)]`` is a dict with ``channels``
    (list of slugs) and one value per metric key; ``metrics`` is ``(key, caption, format)``."""
    gs = fig.add_gridspec(len(row_labels), len(col_labels), hspace=0.08, wspace=0.05)
    for i, own in enumerate(row_labels):
        for j, country in enumerate(col_labels):
            ax = fig.add_subplot(gs[i, j])
            ax.set_xticks([])
            ax.set_yticks([])
            ax.grid(False)
            info = cells.get((own, country), {})
            base = COUNTRY_COLORS[country]
            ax.set_facecolor(to_rgb(base) + (0.07,) if own == "state" else (1, 1, 1, 1))
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_color(base)
                spine.set_linewidth(2.2 if own == "state" else 1.2)
                spine.set_linestyle("-" if own == "state" else (0, (4, 2)))
            names = ", ".join(SHORT_NAMES[s] for s in info.get("channels", []))
            ax.text(0.04, 0.93, f"{country} / {own}", fontsize=10.5, fontweight="bold", color=base, transform=ax.transAxes, va="top")
            if not info:
                ax.text(0.5, 0.45, "no channel in this cell", fontsize=10, color=MUTED, transform=ax.transAxes, ha="center", style="italic")
                continue
            ax.text(0.04, 0.82, names, fontsize=8.5, color=MUTED, transform=ax.transAxes, va="top")
            for k, (key, caption, fmt) in enumerate(metrics):
                value = info.get(key)
                top = 0.64 - 0.28 * k
                ax.text(0.04, top, fmt.format(value) if value is not None else "n/a", fontsize=16, fontweight="bold", color=INK, transform=ax.transAxes, va="top")
                ax.text(0.04, top - 0.12, caption, fontsize=8, color=MUTED, transform=ax.transAxes, va="top")


# ---------------------------------------------------------------------------
# Plotly
# ---------------------------------------------------------------------------


def _register_plotly_template() -> Any:
    import plotly.graph_objects as go
    import plotly.io as pio

    template = go.layout.Template()
    template.layout = go.Layout(
        font={"family": ", ".join(FONT_STACK), "size": 13, "color": INK},
        paper_bgcolor=PAPER,
        plot_bgcolor=PAPER,
        colorway=[CHANNEL_COLORS[s] for s in CHANNEL_ORDER],
        title={"x": 0.0, "xanchor": "left", "font": {"size": 18}},
        xaxis={"gridcolor": GRID, "zeroline": False, "linecolor": "#B8BEC6", "showline": True},
        yaxis={"gridcolor": GRID, "zeroline": False, "linecolor": "#B8BEC6", "showline": True},
        legend={"bgcolor": "rgba(0,0,0,0)"},
        hoverlabel={"font": {"family": ", ".join(FONT_STACK)}},
        margin={"l": 70, "r": 30, "t": 80, "b": 80},
    )
    pio.templates["telegram_study"] = template
    return template


PLOTLY_TEMPLATE = _register_plotly_template()


def plotly_base(title: str, subtitle: str | None = None, **layout: Any) -> Any:
    """Empty Plotly figure with the house template, a finding title and the source line."""
    import plotly.graph_objects as go

    fig = go.Figure()
    full_title = title if not subtitle else f"{title}<br><sup>{subtitle}</sup>"
    fig.update_layout(template="telegram_study", title=full_title, **layout)
    fig.add_annotation(
        text=SOURCE_LINE, xref="paper", yref="paper", x=0, y=-0.16, showarrow=False, xanchor="left", font={"size": 10, "color": MUTED}
    )
    return fig


def plotly_dot_whisker(
    df: pd.DataFrame,
    *,
    label_col: str,
    est_col: str,
    lo_col: str,
    hi_col: str,
    slug_col: str = "channel_slug",
    title: str,
    subtitle: str | None = None,
    log: bool = False,
    xlabel: str = "",
) -> Any:
    fig = plotly_base(title, subtitle, height=420)
    frame = df.reset_index(drop=True)
    for row in frame.itertuples(index=False):
        slug = getattr(row, slug_col)
        st = style(slug)
        state = CHANNELS[slug]["ownership"] == STATE_OWNERSHIP
        fig.add_scatter(
            x=[getattr(row, est_col)],
            y=[getattr(row, label_col)],
            mode="markers",
            marker={"size": 13, "color": st["color"] if state else "white", "line": {"color": st["color"], "width": 2.5}},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": [getattr(row, hi_col) - getattr(row, est_col)],
                "arrayminus": [getattr(row, est_col) - getattr(row, lo_col)],
                "color": st["color"],
                "thickness": 2.2,
            },
            name=getattr(row, label_col),
            hovertemplate=f"{getattr(row, label_col)}: %{{x:.2f}} [{getattr(row, lo_col):.2f}, {getattr(row, hi_col):.2f}]<extra></extra>",
            showlegend=False,
        )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title=xlabel, type="log" if log else "linear")
    return fig


def plotly_umap(
    coords: np.ndarray,
    frame: pd.DataFrame,
    *,
    title: str,
    subtitle: str | None = None,
    hover_col: str = "preview",
) -> Any:
    """Interactive map of all posts: one trace per channel, hover shows channel, time and a text preview."""
    fig = plotly_base(title, subtitle, height=700)
    for slug in CHANNEL_ORDER:
        mask = (frame["channel_slug"] == slug).to_numpy()
        if not mask.any():
            continue
        sub = frame.loc[mask]
        fig.add_scattergl(
            x=coords[mask, 0],
            y=coords[mask, 1],
            mode="markers",
            name=f"{SHORT_NAMES[slug]} ({CHANNELS[slug]['ownership']})",
            marker={"size": 4, "color": CHANNEL_COLORS[slug], "opacity": 0.55},
            text=sub[hover_col].tolist(),
            hovertemplate="%{text}<extra>" + SHORT_NAMES[slug] + "</extra>",
        )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def plotly_heatmap(matrix: pd.DataFrame, *, title: str, subtitle: str | None = None, fmt: str = ".0%", zlabel: str = "share") -> Any:
    fig = plotly_base(title, subtitle, height=max(380, 28 * len(matrix) + 160))
    fig.add_heatmap(
        z=matrix.to_numpy(dtype=float),
        x=list(matrix.columns),
        y=list(matrix.index),
        colorscale=[[0, "#F7F4EE"], [0.35, "#F2D7A6"], [0.65, "#E39A55"], [0.85, "#B8473A"], [1, "#5B1A2B"]],
        hovertemplate="%{y} / %{x}: %{z:" + fmt + "}<extra></extra>",
        colorbar={"title": zlabel},
    )
    fig.update_yaxes(autorange="reversed")
    return fig


def plotly_lines(
    daily: pd.DataFrame,
    *,
    title: str,
    subtitle: str | None = None,
    events: Iterable[Mapping[str, Any]] = (),
    ylabel: str = "",
) -> Any:
    """Daily line chart per channel (state solid, private dashed) with dotted event lines."""
    fig = plotly_base(title, subtitle, height=480)
    for slug in CHANNEL_ORDER:
        if slug not in daily.columns:
            continue
        state = CHANNELS[slug]["ownership"] == STATE_OWNERSHIP
        fig.add_scatter(
            x=daily.index,
            y=daily[slug],
            mode="lines",
            name=f"{SHORT_NAMES[slug]} ({CHANNELS[slug]['ownership']})",
            line={"color": CHANNEL_COLORS[slug], "width": 2.4, "dash": "solid" if state else "dash"},
        )
    for event in events:
        fig.add_vline(x=pd.Timestamp(event["date"]).timestamp() * 1000, line_dash="dot", line_color=MUTED, annotation_text=event["short"], annotation_font_size=10)
    fig.update_yaxes(title=ylabel)
    return fig
