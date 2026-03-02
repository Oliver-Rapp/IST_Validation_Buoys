#!/usr/bin/env python3
"""
buoys_stats.py — Dataset statistics and track plots for the OSI SAF IST
validation dataset.

Reads all BUOYS_*.txt output files, counts unique buoys per type / year /
hemisphere, and saves polar-projection track plots for each hemisphere.

Usage (from inside the Nix shell):
    python buoys_stats.py
"""

import os
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = str(Path(__file__).resolve().parent.parent / "data" / "validation_output" / "ist_txt")

# Column names matching the 18-field SvalMIZ ASCII output
COL_NAMES = [
    "ID", "TYPE", "LAT", "LON",
    "YYYY", "MON", "DAY", "HH", "MIN",
    "Ts", "T2m", "Td", "Press", "FF", "DD_wind", "Cloud",
    "Ts_Q", "T2m_Q",
]

# One colour per buoy type (TYPE field in output files)
TYPE_COLORS = {
    "SIMB3": "#e41a1c",   # red
    "SIMBA": "#ff7f00",   # orange
    "SNOW":  "#4daf4a",   # green
    "METEO": "#984ea3",   # purple
    "CALIB": "#377eb8",   # blue
    "SVP":   "#a65628",   # brown
    "OMB":   "#f781bf",   # pink
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_data(data_dir: str) -> pd.DataFrame:
    """Read every BUOYS_*.txt file and return a single concatenated DataFrame."""
    files = sorted(
        glob.glob(os.path.join(data_dir, "**", "BUOYS_*.txt"), recursive=True)
    )
    if not files:
        raise FileNotFoundError(f"No BUOYS_*.txt files found under: {data_dir}")

    print(f"Found {len(files)} output files — loading ...")
    chunks = []
    for f in files:
        try:
            df = pd.read_csv(
                f,
                sep=r"\s+",
                header=None,
                names=COL_NAMES,
                dtype={"ID": str, "TYPE": str},
                on_bad_lines="warn",
            )
            chunks.append(df)
        except Exception as exc:
            print(f"  Warning: skipping {f}: {exc}")

    data = pd.concat(chunks, ignore_index=True)

    # Coerce numeric fields
    for col in ("LAT", "LON"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["YYYY"] = pd.to_numeric(data["YYYY"], errors="coerce").astype("Int64")

    # Strip whitespace from string fields
    data["ID"]   = data["ID"].str.strip()
    data["TYPE"] = data["TYPE"].str.strip()

    # Drop rows with missing position or year
    data = data.dropna(subset=["LAT", "LON", "YYYY"])

    # Remove duplicate records (same buoy, same timestamp)
    data = data.drop_duplicates(subset=["ID", "YYYY", "MON", "DAY", "HH"])

    print(
        f"Loaded {len(data):,} records — "
        f"{data['ID'].nunique()} unique buoys."
    )
    return data


# ---------------------------------------------------------------------------
# Hemisphere assignment
# ---------------------------------------------------------------------------

def assign_hemisphere(data: pd.DataFrame) -> pd.DataFrame:
    """
    Assign each buoy to 'Northern' or 'Southern' based on its mean latitude
    across all observations. Result is stored in a new HEMISPHERE column.
    """
    mean_lat = data.groupby("ID")["LAT"].mean()
    hemi_map = mean_lat.apply(
        lambda lat: "Northern" if lat >= 0 else "Southern"
    )
    data = data.copy()
    data["HEMISPHERE"] = data["ID"].map(hemi_map)
    return data


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def compute_and_print_stats(data: pd.DataFrame) -> pd.DataFrame:
    """
    Count distinct buoys per (HEMISPHERE, TYPE, YEAR) and print a pivot table.
    Returns the raw counts DataFrame.
    """
    stats = (
        data.groupby(["HEMISPHERE", "TYPE", "YYYY"])["ID"]
        .nunique()
        .reset_index()
        .rename(columns={"ID": "N_BUOYS", "YYYY": "YEAR"})
    )

    # Print overall totals first
    total_nh = data[data["HEMISPHERE"] == "Northern"]["ID"].nunique()
    total_sh = data[data["HEMISPHERE"] == "Southern"]["ID"].nunique()
    print(f"\nTotal unique buoys — Northern: {total_nh},  Southern: {total_sh}")

    print("\n" + "=" * 65)
    print("  Unique buoys per type and year")
    print("=" * 65)

    for hemi in ("Northern", "Southern"):
        sub  = stats[stats["HEMISPHERE"] == hemi]
        hdat = data[data["HEMISPHERE"] == hemi]
        if sub.empty:
            print(f"\n--- {hemi} Hemisphere: no data ---")
            continue

        pivot = sub.pivot_table(
            index="TYPE", columns="YEAR", values="N_BUOYS", fill_value=0
        )
        pivot.index.name   = "Type"
        pivot.columns.name = "Year"

        # Column total per type (across all years)
        pivot["TOTAL"] = pivot.sum(axis=1).astype(int)

        # Row total: unique buoys per year regardless of type
        # (computed independently to avoid double-counting)
        year_totals = hdat.groupby("YYYY")["ID"].nunique()
        total_row = {yr: int(year_totals.get(yr, 0)) for yr in pivot.columns}
        total_row["TOTAL"] = hdat["ID"].nunique()
        pivot.loc["TOTAL"] = total_row

        # Format all values as integers (no decimal places)
        pivot = pivot.astype(int)

        print(f"\n--- {hemi} Hemisphere ---")
        print(pivot.to_string())

    print()
    return stats


# ---------------------------------------------------------------------------
# Track plots
# ---------------------------------------------------------------------------

def _plot_track(ax, lons: np.ndarray, lats: np.ndarray, color: str, **kw) -> None:
    """
    Plot a buoy track as connected segments, splitting at dateline crossings.

    When using ax.plot() with transform=PlateCarree(), a buoy track that crosses
    the dateline (lon jumps from ~180 to ~-180) makes cartopy draw a straight
    line clean across the interior of the polar projection — the characteristic
    'spoke' artifact. Splitting the arrays wherever |Δlon| > 180° prevents this.
    """
    crossings = np.where(np.abs(np.diff(lons)) > 180)[0] + 1
    for lon_seg, lat_seg in zip(np.split(lons, crossings), np.split(lats, crossings)):
        if len(lon_seg) >= 2:
            ax.plot(lon_seg, lat_seg, "-",
                    color=color, transform=ccrs.PlateCarree(), **kw)
        else:
            ax.plot(lon_seg, lat_seg, "o",
                    color=color, markersize=2.0,
                    transform=ccrs.PlateCarree(), zorder=kw.get("zorder", 5))


def _plot_hemisphere(
    data: pd.DataFrame,
    hemisphere: str,
    projection,
    extent: list,
    title: str,
    out_file: str,
) -> None:
    """
    Draw buoy tracks for one hemisphere on a polar stereographic map and save
    the figure to *out_file*.
    """
    hdata = data[data["HEMISPHERE"] == hemisphere]
    if hdata.empty:
        print(f"No data for {hemisphere} hemisphere — skipping plot.")
        return

    fig = plt.figure(figsize=(9, 9))
    ax  = fig.add_subplot(1, 1, 1, projection=projection)
    ax.set_extent(extent, crs=ccrs.PlateCarree())

    # Background
    ax.add_feature(cfeature.LAND,       facecolor="#d4cfbf", zorder=2)
    ax.add_feature(cfeature.OCEAN,      facecolor="#cce4f6", zorder=1)
    ax.add_feature(cfeature.COASTLINE,  linewidth=0.4,       zorder=3)
    ax.add_feature(cfeature.BORDERS,    linewidth=0.3,       zorder=3, alpha=0.5)
    ax.gridlines(color="gray", alpha=0.35, linestyle="--", zorder=4)

    # Plot each buoy track
    for buoy_id, grp in hdata.groupby("ID"):
        grp   = grp.sort_values(["YYYY", "MON", "DAY", "HH"])
        btype = grp["TYPE"].iloc[0]
        color = TYPE_COLORS.get(btype, "gray")
        lats  = grp["LAT"].values
        lons  = grp["LON"].values

        _plot_track(ax, lons, lats, color, linewidth=0.7, alpha=0.75, zorder=5)
        # Mark last known position
        ax.plot(lons[-1], lats[-1], "o", markersize=2.0,
                color=color, transform=ccrs.PlateCarree(), zorder=5)

    # Legend (one entry per type present in this hemisphere)
    present_types = sorted(hdata["TYPE"].unique())
    handles = [
        plt.Line2D(
            [0], [0],
            color=TYPE_COLORS.get(t, "gray"),
            linewidth=1.8,
            label=f"{t}  (n={hdata[hdata['TYPE']==t]['ID'].nunique()})",
        )
        for t in present_types
    ]
    ax.legend(
        handles=handles,
        loc="lower left",
        fontsize=8,
        framealpha=0.85,
        title="Buoy type",
        title_fontsize=8,
    )
    ax.set_title(title, fontsize=13, pad=10)

    fig.tight_layout()
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    print(f"Saved {out_file}")


def make_track_plots(data: pd.DataFrame) -> None:
    """Generate and save NH and SH track plots."""
    _plot_hemisphere(
        data,
        hemisphere  = "Northern",
        projection  = ccrs.NorthPolarStereo(central_longitude=0),
        extent      = [-180, 180, 50, 90],
        title       = "Northern Hemisphere — Buoy Tracks",
        out_file    = "nh_buoy_tracks.png",
    )
    _plot_hemisphere(
        data,
        hemisphere  = "Southern",
        projection  = ccrs.SouthPolarStereo(central_longitude=0),
        extent      = [-180, 180, -90, -50],
        title       = "Southern Hemisphere — Buoy Tracks",
        out_file    = "sh_buoy_tracks.png",
    )
    plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    data = load_all_data(DATA_DIR)
    data = assign_hemisphere(data)
    compute_and_print_stats(data)
    make_track_plots(data)


if __name__ == "__main__":
    main()
