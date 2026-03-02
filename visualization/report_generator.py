#!/usr/bin/env python3
"""
report_generator.py — Comprehensive PDF statistics report for the OSI SAF IST
validation dataset.

Reads all BUOYS_*.txt output files and produces a multi-page PDF containing:
  • Title / metadata page
  • Observation-count histograms (raw + 1-hour-normalised) per hemisphere
  • Polar scatter maps (NH + SH)
  • QC-flag pie charts per buoy type
  • Air-temperature and skin-temperature time-series per hemisphere

Usage (from inside the Nix shell, run from any directory):
    python visualization/report_generator.py
"""

import os
import glob
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")           # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
DATA_DIR = _HERE.parent / "data" / "validation_output" / "ist_txt"
OUT_PDF  = DATA_DIR.parent / f"buoys_report_{date.today():%Y%m%d}.pdf"

COL_NAMES = [
    "ID", "TYPE", "LAT", "LON",
    "YYYY", "MON", "DAY", "HH", "MIN",
    "Ts", "T2m", "Td", "Press", "FF", "DD_wind", "Cloud",
    "Ts_Q", "T2m_Q",
]

FILL_FLOAT = -99.9   # sentinel for missing float values in the output files

TYPE_COLORS = {
    "SIMB3": "#e41a1c",
    "SIMBA": "#ff7f00",
    "SNOW":  "#4daf4a",
    "METEO": "#984ea3",
    "CALIB": "#377eb8",
    "SVP":   "#a65628",
    "OMB":   "#f781bf",
}
FLAG_COLORS = {-9: "#aaaaaa", 0: "#4daf4a", 1: "#ff7f00", 2: "#e41a1c"}
FLAG_LABELS = {-9: "−9 (no QC)", 0: "0 (good)", 1: "1 (suspect)", 2: "2 (invalid)"}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_data(data_dir: Path) -> pd.DataFrame:
    files = sorted(glob.glob(str(data_dir / "**" / "BUOYS_*.txt"), recursive=True))
    if not files:
        raise FileNotFoundError(f"No BUOYS_*.txt files found under: {data_dir}")
    print(f"Found {len(files):,} output files — loading …")

    chunks = []
    for f in files:
        try:
            df = pd.read_csv(
                f, sep=r"\s+", header=None, names=COL_NAMES,
                dtype={"ID": str, "TYPE": str}, on_bad_lines="warn",
            )
            chunks.append(df)
        except Exception as exc:
            print(f"  Warning: skipping {f}: {exc}")

    data = pd.concat(chunks, ignore_index=True)

    # Coerce numeric columns
    for col in ("LAT", "LON", "Ts", "T2m", "Press", "YYYY", "MON", "DAY", "HH", "MIN"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    for col in ("Ts_Q", "T2m_Q", "FF", "DD_wind"):
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data["YYYY"] = data["YYYY"].astype("Int64")
    data["ID"]   = data["ID"].str.strip()
    data["TYPE"] = data["TYPE"].str.strip()

    data = data.dropna(subset=["LAT", "LON", "YYYY"])
    # Remove exact duplicates only (keep sub-hourly records; MIN is included)
    data = data.drop_duplicates(subset=["ID", "YYYY", "MON", "DAY", "HH", "MIN"])

    # Sentinel → NaN for temperatures
    data["Ts_plot"]  = data["Ts"].where(data["Ts"]  > FILL_FLOAT + 1)
    data["T2m_plot"] = data["T2m"].where(data["T2m"] > FILL_FLOAT + 1)

    # Datetime column (includes minutes)
    df_dt = data[["YYYY", "MON", "DAY", "HH", "MIN"]].copy()
    df_dt.columns = ["year", "month", "day", "hour", "minute"]
    df_dt = df_dt.apply(lambda s: pd.to_numeric(s, errors="coerce")).dropna()
    data["datetime"] = pd.NaT
    data.loc[df_dt.index, "datetime"] = pd.to_datetime(df_dt.astype(int), errors="coerce")

    print(
        f"Loaded {len(data):,} records — "
        f"{data['ID'].nunique()} unique buoys."
    )
    return data


def assign_hemisphere(data: pd.DataFrame) -> pd.DataFrame:
    mean_lat = data.groupby("ID")["LAT"].mean()
    hemi_map = mean_lat.apply(lambda lat: "Northern" if lat >= 0 else "Southern")
    data = data.copy()
    data["HEMISPHERE"] = data["ID"].map(hemi_map)
    return data


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

def _title_page(pdf: PdfPages, data: pd.DataFrame) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))   # A4
    fig.patch.set_facecolor("#f5f5f5")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    # Decorative header bar
    ax.add_patch(plt.Rectangle((0, 0.82), 1, 0.18,
                                transform=ax.transAxes, facecolor="#1a3a5c"))

    ax.text(0.5, 0.91, "OSI SAF IST Validation Dataset",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=22, fontweight="bold", color="white")
    ax.text(0.5, 0.85, "Dataset Statistics Report",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=16, color="#cce4f6")

    # Metadata block
    years   = sorted(data["YYYY"].dropna().unique().astype(int).tolist())
    dt_min  = data["datetime"].dropna().min()
    dt_max  = data["datetime"].dropna().max()
    n_total = len(data)
    n_buoys = data["ID"].nunique()
    nh      = data[data["HEMISPHERE"] == "Northern"]["ID"].nunique()
    sh      = data[data["HEMISPHERE"] == "Southern"]["ID"].nunique()
    types   = sorted(data["TYPE"].unique().tolist())

    lines = [
        ("Generated",          date.today().strftime("%Y-%m-%d")),
        ("Data directory",     str(DATA_DIR)),
        ("Years covered",      ", ".join(str(y) for y in years)),
        ("Earliest record",    dt_min.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(dt_min) else "n/a"),
        ("Latest record",      dt_max.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(dt_max) else "n/a"),
        ("Total records",      f"{n_total:,}"),
        ("Unique buoys",       f"{n_buoys}  (NH: {nh}, SH: {sh})"),
        ("Buoy types present", ", ".join(types)),
    ]

    y0 = 0.74
    for label, value in lines:
        ax.text(0.12, y0, f"{label}:", ha="left", va="top",
                transform=ax.transAxes, fontsize=11, fontweight="bold", color="#333")
        ax.text(0.42, y0, value, ha="left", va="top",
                transform=ax.transAxes, fontsize=11, color="#222")
        y0 -= 0.06

    ax.plot([0.08, 0.92], [0.06, 0.06],
            color="#aaaaaa", linewidth=0.8, transform=ax.transAxes)
    ax.text(0.5, 0.03,
            "QC flags: −9 = no QC / no measurement   0 = Good   1 = Suspect   2 = Invalid",
            ha="center", va="bottom", transform=ax.transAxes,
            fontsize=9, color="#666")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print("  Page 1: title done")


# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

def _histogram_page(pdf: PdfPages, data: pd.DataFrame, hemisphere: str) -> None:
    """One page: raw obs count (top) + 1-hour-normalised count (bottom)."""
    hdata = data[data["HEMISPHERE"] == hemisphere].copy()
    if hdata.empty:
        return

    # Filter: at least one QC flag in {0, −9}
    good = hdata[hdata["Ts_Q"].isin([0, -9]) | hdata["T2m_Q"].isin([0, -9])]

    years  = sorted(good["YYYY"].dropna().unique().astype(int).tolist())
    types  = sorted(good["TYPE"].unique().tolist())

    # Hourly-normalised version (deduplicate per buoy-hour)
    normd = good.drop_duplicates(subset=["ID", "YYYY", "MON", "DAY", "HH"])

    fig, axes = plt.subplots(2, 1, figsize=(11, 8.5))
    fig.suptitle(
        f"{hemisphere} Hemisphere — Observation Counts by Buoy Type",
        fontsize=14, fontweight="bold", y=0.99,
    )

    datasets = [
        (good,  axes[0], "Raw observation count\n(QC flags 0 or −9 only)"),
        (normd, axes[1], "1-hour-normalised count\n(one buoy-hour counted once, QC flags 0 or −9 only)"),
    ]

    for df, ax, ylabel in datasets:
        # Build pivot: rows=TYPE, cols=YYYY
        pivot = (
            df.groupby(["TYPE", "YYYY"])
            .size()
            .unstack(fill_value=0)
            .reindex(index=types, columns=years, fill_value=0)
        )

        n_types = len(types)
        n_years = len(years)
        x = np.arange(n_types)
        width = 0.7 / max(n_years, 1)

        # Year totals (across all types) for annotation
        year_totals = pivot.sum(axis=0)
        grand_total = int(pivot.values.sum())

        for i, yr in enumerate(years):
            offset = (i - (n_years - 1) / 2) * width
            vals = pivot[yr].values
            bars = ax.bar(
                x + offset, vals, width=width * 0.9,
                color=plt.cm.tab10(i / max(n_years, 1)),
                label=str(yr), zorder=3,
            )
            # Value labels on bars that are tall enough
            for bar in bars:
                h = bar.get_height()
                if h > grand_total * 0.003:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        h, f"{int(h):,}", ha="center", va="bottom",
                        fontsize=6.5, color="#333",
                    )

        # Per-year total annotation above each cluster
        for i, yr in enumerate(years):
            offset = (i - (n_years - 1) / 2) * width
            cluster_x = x + offset          # positions of bars for this year
            # max height in each type for this year
            max_y = pivot[yr].values
            # draw one small italic label above the max bar per cluster
        # Instead: draw year totals as a note in the legend
        year_total_str = "  |  ".join(f"{yr}: {int(year_totals[yr]):,}" for yr in years)

        ax.set_xticks(x)
        ax.set_xticklabels(types, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_xlabel("Buoy type", fontsize=9)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax.legend(title="Year", fontsize=8, title_fontsize=9)
        ax.grid(axis="y", alpha=0.3, zorder=0)
        ax.set_axisbelow(True)

        # Totals text box
        ax.text(
            0.98, 0.97,
            f"Grand total: {grand_total:,}\n{year_total_str}",
            ha="right", va="top", transform=ax.transAxes,
            fontsize=8, color="#333",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="#cccccc", alpha=0.9),
        )

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"  Histogram page: {hemisphere} done")


# ---------------------------------------------------------------------------
# Scatter maps
# ---------------------------------------------------------------------------

def _scatter_map_page(pdf: PdfPages, data: pd.DataFrame, hemisphere: str) -> None:
    hdata = data[data["HEMISPHERE"] == hemisphere]
    if hdata.empty:
        return

    if hemisphere == "Northern":
        proj   = ccrs.NorthPolarStereo(central_longitude=0)
        extent = [-180, 180, 55, 90]
        title  = "Northern Hemisphere — Buoy Positions"
    else:
        proj   = ccrs.SouthPolarStereo(central_longitude=0)
        extent = [-180, 180, -90, -50]
        title  = "Southern Hemisphere — Buoy Positions"

    fig = plt.figure(figsize=(9, 9))
    ax  = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent(extent, crs=ccrs.PlateCarree())

    ax.add_feature(cfeature.LAND,      facecolor="#d4cfbf", zorder=2)
    ax.add_feature(cfeature.OCEAN,     facecolor="#cce4f6", zorder=1)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.4,       zorder=3)
    ax.add_feature(cfeature.BORDERS,   linewidth=0.3,       zorder=3, alpha=0.5)
    ax.gridlines(color="gray", alpha=0.35, linestyle="--", zorder=4)

    # Thin data to limit render time (keep at most ~80 000 points per type)
    MAX_PTS = 80_000
    handles = []
    for btype in sorted(hdata["TYPE"].unique()):
        sub = hdata[hdata["TYPE"] == btype]
        if len(sub) > MAX_PTS:
            sub = sub.sample(MAX_PTS, random_state=42)
        color = TYPE_COLORS.get(btype, "gray")
        n_buoys = hdata[hdata["TYPE"] == btype]["ID"].nunique()
        ax.scatter(
            sub["LON"].values, sub["LAT"].values,
            s=1, alpha=0.25, color=color, linewidths=0,
            transform=ccrs.PlateCarree(), zorder=5,
        )
        handles.append(
            plt.scatter([], [], s=20, color=color, alpha=0.8,
                        label=f"{btype}  (n={n_buoys} buoys)")
        )

    ax.legend(
        handles=handles, loc="lower left", fontsize=8,
        framealpha=0.85, title="Buoy type", title_fontsize=8,
    )
    ax.set_title(title, fontsize=13, pad=10)

    fig.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"  Scatter map: {hemisphere} done")


# ---------------------------------------------------------------------------
# QC flag pie charts
# ---------------------------------------------------------------------------

def _qc_pie_page(pdf: PdfPages, data: pd.DataFrame, hemisphere: str) -> None:
    hdata = data[data["HEMISPHERE"] == hemisphere]
    if hdata.empty:
        return

    # Only show thermistor buoys that have meaningful QC variation
    types = [t for t in ("SIMB3", "SIMBA") if t in hdata["TYPE"].unique()]
    n_types = len(types)
    if n_types == 0:
        return

    # 2 columns (Ts_Q left, T2m_Q right), n_types rows
    fig, axes = plt.subplots(n_types, 2,
                             figsize=(8, max(3.5 * n_types, 4)))
    if n_types == 1:
        axes = np.array([axes])   # ensure 2-D

    fig.suptitle(
        f"{hemisphere} Hemisphere — QC Flag Distribution by Buoy Type",
        fontsize=13, fontweight="bold",
    )

    all_flags = [-9, 0, 1, 2]

    for row, btype in enumerate(types):
        sub = hdata[hdata["TYPE"] == btype]
        for col, qfield in enumerate(("Ts_Q", "T2m_Q")):
            ax = axes[row, col]
            counts = sub[qfield].value_counts().reindex(all_flags, fill_value=0)
            total  = counts.sum()

            labels  = []
            sizes   = []
            colors  = []
            explode = []

            for flag in all_flags:
                n = counts[flag]
                if total > 0:
                    pct = 100 * n / total
                else:
                    pct = 0
                if n > 0:
                    labels.append(f"{FLAG_LABELS[flag]}\n{pct:.1f}%")
                    sizes.append(n)
                    colors.append(FLAG_COLORS[flag])
                    explode.append(0.03 if flag == 0 else 0)

            if sizes:
                ax.pie(sizes, labels=labels, colors=colors,
                       explode=explode, startangle=90,
                       textprops={"fontsize": 7},
                       wedgeprops={"linewidth": 0.5, "edgecolor": "white"})
            else:
                ax.text(0.5, 0.5, "No data", ha="center", va="center",
                        transform=ax.transAxes, fontsize=9, color="gray")

            field_name = "Skin temp (Ts)" if qfield == "Ts_Q" else "Air temp (T2m)"
            ax.set_title(f"{btype} — {field_name}\n(N={total:,})", fontsize=9)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"  QC pie charts: {hemisphere} done")


# ---------------------------------------------------------------------------
# Temperature time series
# ---------------------------------------------------------------------------

def _temp_timeseries_page(
    pdf: PdfPages,
    data: pd.DataFrame,
    hemisphere: str,
    field: str,           # "Ts_plot" or "T2m_plot"
    field_label: str,     # e.g. "Skin temperature Ts"
) -> None:
    # Derive the corresponding QC column and filter to flags 0 or -9
    qc_col = "Ts_Q" if field == "Ts_plot" else "T2m_Q"
    hdata = data[data["HEMISPHERE"] == hemisphere].copy()
    hdata = hdata[hdata[qc_col].isin([0, -9])]
    hdata = hdata.dropna(subset=["datetime", field])
    if hdata.empty:
        return

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.set_title(
        f"{hemisphere} Hemisphere — {field_label} vs Time"
        f"\nShowing QC flags: 0 (good) and −9 (no QC)",
        fontsize=13, fontweight="bold",
    )

    # Plot high-density buoy types first (background), thermistor buoys last (foreground)
    THERMISTOR = {"SIMB3", "SIMBA"}
    bg_types = [t for t in sorted(hdata["TYPE"].unique()) if t not in THERMISTOR]
    fg_types = [t for t in ("SIMB3", "SIMBA") if t in hdata["TYPE"].unique()]

    handles = []
    for btype in bg_types + fg_types:
        sub = hdata[hdata["TYPE"] == btype].sort_values("datetime")
        color = TYPE_COLORS.get(btype, "gray")
        n_obs = len(sub)
        is_thermistor = btype in THERMISTOR
        ax.scatter(
            sub["datetime"], sub[field],
            s=5 if is_thermistor else 1,
            alpha=0.7 if is_thermistor else 0.25,
            color=color, linewidths=0,
            zorder=5 if is_thermistor else 3,
        )
        handles.append(
            plt.scatter([], [], s=30 if is_thermistor else 20,
                        color=color, alpha=0.9,
                        label=f"{btype}  (n={n_obs:,})")
        )

    ax.set_xlabel("Date (UTC)", fontsize=10)
    ax.set_ylabel(f"{field_label} [K]", fontsize=10)
    ax.grid(alpha=0.3, zorder=0)
    ax.legend(handles=handles, loc="upper right", fontsize=8,
              title="Buoy type", title_fontsize=9, framealpha=0.85)

    # Secondary Celsius axis (right side)
    ax2 = ax.twinx()
    ax2.set_ylabel("Temperature [°C]", fontsize=10)

    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()

    # Sync Celsius axis to Kelvin limits after layout is finalised
    y1, y2 = ax.get_ylim()
    ax2.set_ylim(y1 - 273.15, y2 - 273.15)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}"))

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"  Time series: {hemisphere} — {field_label} done")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\nOSI SAF IST Validation — Report Generator")
    print(f"  Data dir : {DATA_DIR}")
    print(f"  Output   : {OUT_PDF}\n")

    data = load_all_data(DATA_DIR)
    data = assign_hemisphere(data)

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(str(OUT_PDF)) as pdf:
        # Set PDF metadata
        d = pdf.infodict()
        d["Title"]   = "OSI SAF IST Validation Dataset — Statistics Report"
        d["Author"]  = "report_generator.py"
        d["Subject"] = f"Generated {date.today()}"

        print("Generating pages …")
        _title_page(pdf, data)

        for hemi in ("Northern", "Southern"):
            _histogram_page(pdf, data, hemi)

        for hemi in ("Northern", "Southern"):
            _scatter_map_page(pdf, data, hemi)

        for hemi in ("Northern", "Southern"):
            _qc_pie_page(pdf, data, hemi)

        for hemi in ("Northern", "Southern"):
            _temp_timeseries_page(pdf, data, hemi, "T2m_plot", "Air temperature T2m")

        for hemi in ("Northern", "Southern"):
            _temp_timeseries_page(pdf, data, hemi, "Ts_plot", "Skin temperature Ts")

    print(f"\nDone. Saved: {OUT_PDF}")


if __name__ == "__main__":
    main()
