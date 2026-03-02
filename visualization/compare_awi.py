"""
compare_awi.py — Compare our automated SIMBA interface detection against
the AWI manual classification (Preußer et al., 2025, PANGAEA).

Usage:
    python compare_awi.py                   # use current config edge_ratio (0.2)
    python compare_awi.py --edge-ratio 0.15 # override single value
    python compare_awi.py --sweep           # sweep edge_ratio, save sweep figure

Output saved to data/AWI_comparison/

What is compared:
    - Thermistor index at the atmosphere/snow interface (ours 1-indexed vs AWI 1-indexed)
    - Temperature at that interface (°C)
    - Detection agreement (both detected, our-only, AWI-only)
    - Correlation of our QC flags with detection disagreement

Notes on methodology:
    - AWI used manual classification combining SIMBA-ET gradient and SIMBA-HT
      heat pulse signals. Our algorithm uses only SIMBA-ET (leading_edge method).
    - AWI thermistor numbers are 1-indexed, matching our edge_idx convention.
    - Our Ts is extracted at sensor edge_idx-1 (0-indexed), which is the sensor
      one step above the leading edge — same as the pipeline output.
    - The algorithm masks sensors T1–T5 (grads[:,:5]=0), so our minimum
      detectable interface is at thermistor 5 (1-indexed). AWI has no such
      constraint, so cases where AWI detects at thermistors 1–4 will show a
      systematic positive delta_idx.
"""

import argparse
import copy
import os
import sys
import glob
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from pathlib import Path

# --- Project library imports ---
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.simba_algo import SimbaInterfaceDetector
from lib.simba_qc import SimbaQC
from lib.data_loader import load_buoy_data
from lib.config_manager import BuoyConfig

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).resolve().parent.parent
RAW_DIR     = BASE_DIR / "data" / "raw"
AWI_DIR     = BASE_DIR / "data" / "AWI_official" / "SIMBA_icethick_all" / "datasets"
OUT_DIR     = BASE_DIR / "data" / "AWI_comparison"
CONFIG_PATH = BASE_DIR / "buoy_config.yaml"

# ---------------------------------------------------------------------------
# Discover which buoys to compare (intersection of AWI tab files and raw data)
# ---------------------------------------------------------------------------
def find_comparison_buoys():
    """Return sorted list of buoy IDs that have both an AWI tab file and raw TEMP data."""
    awi_buoys = set()
    for tab in AWI_DIR.glob("*_icethick.tab"):
        awi_buoys.add(tab.name.replace("_icethick.tab", ""))

    raw_buoys = set()
    for f in RAW_DIR.glob("*_TEMP_proc.csv"):
        raw_buoys.add(f.name.split("_")[0])
    # Also accept raw+filterflag versions (older buoys may only have those)
    for f in RAW_DIR.glob("*_TEMP_raw+filterflag.csv"):
        raw_buoys.add(f.name.split("_")[0])

    intersection = sorted(awi_buoys & raw_buoys)
    return intersection

# ---------------------------------------------------------------------------
# AWI tab file loader
# ---------------------------------------------------------------------------
def load_awi_tab(buoy_id):
    """Load one AWI PANGAEA .tab file, return DataFrame indexed by datetime."""
    path = AWI_DIR / f"{buoy_id}_icethick.tab"
    with open(path) as fh:
        lines = fh.readlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "*/") + 1
    df = pd.read_csv(path, sep="\t", skiprows=start, header=0, na_values=[""])
    df["Date/Time"] = pd.to_datetime(df["Date/Time"])
    df = df.set_index("Date/Time").sort_index()
    return df

# ---------------------------------------------------------------------------
# Per-buoy data loading: raw thermistor + AWI reference
# ---------------------------------------------------------------------------
def load_buoy_pair(buoy_id, cfg_mgr):
    """
    Load raw thermistor string data and AWI reference for a given buoy.
    Returns (df_string, awi_df) or raises FileNotFoundError.
    """
    # Build a config with buoy-specific file patterns (same logic as pipeline)
    base_conf = cfg_mgr.get_config_for_id(buoy_id)
    conf = copy.deepcopy(base_conf)
    conf["files"]["primary"] = f"{buoy_id}_{base_conf['files']['primary']}"
    if "aux" in conf["files"]:
        conf["files"]["aux"] = f"{buoy_id}_{base_conf['files']['aux']}"

    _df_meta, df_string = load_buoy_data(str(RAW_DIR), conf)

    if df_string is None or df_string.empty:
        raise ValueError(f"{buoy_id}: no thermistor string data loaded")

    awi_df = load_awi_tab(buoy_id)
    return df_string, awi_df

# ---------------------------------------------------------------------------
# Run detection + QC for one buoy at a given edge_ratio and threshold
# ---------------------------------------------------------------------------
def run_detection(df_string, cfg_mgr, buoy_id, edge_ratio, threshold=0.4375):
    """
    Run detect_leading_edge and SimbaQC on df_string.
    Returns (s_interface, qc_df).
    """
    detector = SimbaInterfaceDetector(df_string)
    s_interface = detector.detect_leading_edge(edge_ratio=edge_ratio, threshold=threshold)

    base_conf  = cfg_mgr.get_config_for_id(buoy_id)
    qc_params  = base_conf.get("qc", {}).get("params", {})
    qc         = SimbaQC(df_string, s_interface, qc_params=qc_params)
    qc_df      = qc.compute_flags()
    return s_interface, qc_df

# ---------------------------------------------------------------------------
# Extract our surface temperature from raw string at a given edge_idx
# ---------------------------------------------------------------------------
def _extract_surface_temps(df_string, s_interface):
    """
    Vectorised extraction of temperature at sensor edge_idx - 1 (0-indexed)
    for every timestamp in s_interface. Returns a pd.Series aligned to s_interface.
    """
    vals = np.full(len(s_interface), np.nan)
    str_arr = df_string.values
    str_idx = df_string.index
    n_sensors = str_arr.shape[1]

    for i, (ts, edge_idx) in enumerate(s_interface.items()):
        if pd.isna(edge_idx):
            continue
        col = int(edge_idx) - 1  # 0-indexed sensor
        if col < 0 or col >= n_sensors:
            continue
        if ts not in str_idx:
            continue
        row = str_idx.get_loc(ts)
        vals[i] = str_arr[row, col]

    return pd.Series(vals, index=s_interface.index)

# ---------------------------------------------------------------------------
# Build matched DataFrame for one buoy
# ---------------------------------------------------------------------------
def compute_matched_df(buoy_id, df_string, awi_df, s_interface, qc_df):
    """
    Align our results with AWI on matching timestamps.
    Returns a DataFrame with all aligned observations (NaN where one side didn't detect).
    """
    our_ts = _extract_surface_temps(df_string, s_interface)

    our_df = pd.DataFrame({
        "our_edge_idx": s_interface,       # 1-indexed
        "our_Ts_degC":  our_ts,
        "our_flag":     qc_df["quality_flag"],
    })

    awi_cols = ["T atm/snow IF [°C]", "Thermistor atm/snow IF",
                "EsEs [m]", "Snow thick [m]"]
    merged = our_df.join(awi_df[awi_cols], how="inner")
    merged["buoy_id"] = buoy_id
    return merged

# ---------------------------------------------------------------------------
# Filter to observations where BOTH sides detected the interface
# ---------------------------------------------------------------------------
def both_detected(merged):
    return merged.dropna(subset=["our_edge_idx", "Thermistor atm/snow IF"]).copy()

# ---------------------------------------------------------------------------
# Aggregate statistics
# ---------------------------------------------------------------------------
def compute_stats(both_df, merged_df=None):
    """
    Compute bias, RMSE, MAE for thermistor index and temperature.
    If merged_df is supplied also compute detection counts.
    """
    n_both = len(both_df)

    delta_idx  = both_df["our_edge_idx"] - both_df["Thermistor atm/snow IF"]
    delta_temp = both_df["our_Ts_degC"]  - both_df["T atm/snow IF [°C]"]

    def safe(fn, arr):
        a = arr.dropna()
        return fn(a) if len(a) > 0 else np.nan

    stats = {
        "n_both":       n_both,
        "idx_bias":     safe(np.mean,     delta_idx),
        "idx_mae":      safe(lambda x: np.mean(np.abs(x)), delta_idx),
        "idx_rmse":     safe(lambda x: np.sqrt(np.mean(x**2)), delta_idx),
        "idx_std":      safe(np.std,      delta_idx),
        "temp_bias":    safe(np.mean,     delta_temp),
        "temp_mae":     safe(lambda x: np.mean(np.abs(x)), delta_temp),
        "temp_rmse":    safe(lambda x: np.sqrt(np.mean(x**2)), delta_temp),
    }

    if merged_df is not None:
        awi_has  = merged_df["Thermistor atm/snow IF"].notna()
        our_has  = merged_df["our_edge_idx"].notna()
        stats["n_matched"]   = len(merged_df)
        stats["n_awi_only"]  = int((awi_has & ~our_has).sum())
        stats["n_our_only"]  = int((our_has & ~awi_has).sum())

    return stats

# ---------------------------------------------------------------------------
# Flag-stratified statistics
# ---------------------------------------------------------------------------
def flag_stratified_stats(both_df):
    rows = []
    for flag in [0, 1, 2]:
        sub = both_df[both_df["our_flag"] == flag]
        if len(sub) == 0:
            continue
        s = compute_stats(sub)
        s["flag"] = flag
        rows.append(s)
    return rows

# ---------------------------------------------------------------------------
# Print summary table
# ---------------------------------------------------------------------------
def print_summary(stats, flag_stats, buoy_stats=None, edge_ratio=None, max_flag=1):
    flag_desc = {0: "Flag 0 (Good) only",
                 1: "Flag 0+1 (Good+Suspect)",
                 2: "all flags (0+1+2)"}
    sep = "-" * 72
    print(sep)
    print(f"  AWI Comparison Summary   (edge_ratio = {edge_ratio})")
    print(f"  Aggregate filter         : our_flag <= {max_flag}  [{flag_desc.get(max_flag, str(max_flag))}]")
    print(sep)
    print(f"  Total matched timestamps : {stats.get('n_matched', '?'):>8}")
    print(f"  Both detected (filtered) : {stats['n_both']:>8}")
    print(f"  Our-only detections      : {stats.get('n_our_only', '?'):>8}")
    print(f"  AWI-only detections      : {stats.get('n_awi_only', '?'):>8}")
    print()
    agg_col = f"≤F{max_flag}"
    print(f"  {'Metric':<30}  {agg_col:>8}  {'Flag 0':>8}  {'Flag 1':>8}  {'Flag 2':>8}")
    print(f"  {'-'*66}")

    fmap = {r["flag"]: r for r in flag_stats}

    def fv(key, f):
        v = fmap.get(f, {}).get(key, np.nan)
        return f"{v:8.3f}" if not np.isnan(v) else "     ---"

    metrics = [
        ("idx_bias",  "Index bias (sensors)"),
        ("idx_mae",   "Index MAE  (sensors)"),
        ("idx_rmse",  "Index RMSE (sensors)"),
        ("idx_std",   "Index σ    (sensors)"),
        ("temp_bias", "Temp bias  (°C)"),
        ("temp_mae",  "Temp MAE   (°C)"),
        ("temp_rmse", "Temp RMSE  (°C)"),
    ]
    for key, label in metrics:
        av = stats.get(key, np.nan)
        avs = f"{av:8.3f}" if (av is not None and not np.isnan(av)) else "     ---"
        print(f"  {label:<30}  {avs}  {fv(key,0)}  {fv(key,1)}  {fv(key,2)}")

    print()
    print(f"  Note: delta_idx = our_edge_idx − AWI_thermistor. Positive = our detection")
    print(f"  is deeper in the string (more sensors from top) than AWI.")
    print(f"  Min detectable by our algo: thermistor 5 (sensors 1–4 are masked).")
    print(sep)

    if buoy_stats:
        print(f"\n  Per-buoy breakdown (n_both / idx_bias / temp_bias):")
        for bstat in sorted(buoy_stats, key=lambda x: x["buoy_id"]):
            b = bstat["buoy_id"]
            n = bstat["n_both"]
            ib = bstat.get("idx_bias", np.nan)
            tb = bstat.get("temp_bias", np.nan)
            ibs = f"{ib:+.2f}" if not np.isnan(ib) else "  ---"
            tbs = f"{tb:+.2f}" if not np.isnan(tb) else "  ---"
            print(f"    {b:<10}  {n:>5} obs   idx_bias={ibs}  temp_bias={tbs} °C")
        print(sep)

# ---------------------------------------------------------------------------
# Per-year statistics
# ---------------------------------------------------------------------------
def print_per_year_stats(all_both_df, max_flag=1):
    """Print index bias, temp bias, RMSE, and N grouped by deployment year."""
    df = all_both_df.copy()
    df["year"] = df["buoy_id"].str[:4].astype(int)

    sep = "-" * 72
    print(sep)
    print(f"  Per-year breakdown  (our_flag <= {max_flag})")
    print(f"  {'Year':<6}  {'N':>6}  {'idx_bias':>10}  {'idx_RMSE':>10}  {'temp_bias':>10}  {'temp_RMSE':>10}")
    print(f"  {'-'*64}")

    for year in sorted(df["year"].unique()):
        sub = df[(df["year"] == year) & (df["our_flag"] <= max_flag)]
        n = len(sub)
        if n == 0:
            continue
        di = sub["our_edge_idx"] - sub["Thermistor atm/snow IF"]
        dt = sub["our_Ts_degC"]  - sub["T atm/snow IF [°C]"]
        ib   = di.mean()
        irmse= np.sqrt((di**2).mean())
        tb   = dt.dropna().mean()
        trmse= np.sqrt((dt.dropna()**2).mean())
        print(f"  {year:<6}  {n:>6}  {ib:>+10.3f}  {irmse:>10.3f}  {tb:>+10.3f}  {trmse:>10.3f}")

    print(sep)

# ---------------------------------------------------------------------------
# Figure 1: Index delta distribution, stratified by QC flag
# ---------------------------------------------------------------------------
def fig_index_distribution(both_df, edge_ratio, outdir):
    fig, ax = plt.subplots(figsize=(9, 5))

    flag_colors = {0: "#2ca02c", 1: "#ff7f0e", 2: "#d62728"}
    flag_labels = {0: "Flag 0 (Good)", 1: "Flag 1 (Suspect)", 2: "Flag 2 (Invalid)"}

    bins = np.arange(
        both_df["our_edge_idx"].sub(both_df["Thermistor atm/snow IF"]).min() - 0.5,
        both_df["our_edge_idx"].sub(both_df["Thermistor atm/snow IF"]).max() + 1.5,
        1.0,
    )
    # Fallback if delta is constant
    if len(bins) < 3:
        bins = np.arange(-10.5, 11.5, 1.0)

    delta = both_df["our_edge_idx"] - both_df["Thermistor atm/snow IF"]
    stacked_data = []
    stacked_cols = []
    for flag in [0, 1, 2]:
        sub = delta[both_df["our_flag"] == flag]
        if len(sub) > 0:
            stacked_data.append(sub)
            stacked_cols.append(flag)

    bottom = np.zeros(len(bins) - 1)
    for flag, data in zip(stacked_cols, stacked_data):
        counts, _ = np.histogram(data, bins=bins)
        ax.bar(
            0.5 * (bins[:-1] + bins[1:]), counts,
            width=0.9, bottom=bottom,
            color=flag_colors[flag], alpha=0.85,
            label=f"{flag_labels[flag]} (n={len(data)})",
        )
        bottom += counts

    ax.axvline(0, color="black", lw=1.5, ls="--", label="Zero (perfect agreement)")
    mean_d = delta.mean()
    med_d  = delta.median()
    ax.axvline(mean_d, color="navy", lw=1.2, ls=":", label=f"Mean = {mean_d:+.2f} sensors")
    ax.axvline(med_d,  color="teal", lw=1.2, ls="-.", label=f"Median = {med_d:+.2f} sensors")

    # Secondary x-axis in cm
    ax2 = ax.twiny()
    ax2.set_xlim(np.array(ax.get_xlim()) * 2)  # 2 cm per sensor
    ax2.set_xlabel("Position difference (cm)")

    ax.set_xlabel("Thermistor index difference  (ours − AWI,  sensors)")
    ax.set_ylabel("Count")
    ax.set_title(
        f"Interface detection: thermistor index difference\n"
        f"edge_ratio = {edge_ratio},  N = {len(both_df):,} matched observations"
    )
    ax.legend(fontsize=9)
    fig.tight_layout()
    out = outdir / f"fig1_index_dist_er{edge_ratio:.2f}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out.name}")

# ---------------------------------------------------------------------------
# Figure 2: Temperature scatter (our Ts vs AWI T_atm/snow)
# ---------------------------------------------------------------------------
def fig_temperature_scatter(both_df, edge_ratio, outdir):
    valid = both_df.dropna(subset=["our_Ts_degC", "T atm/snow IF [°C]"])
    if len(valid) < 5:
        print("  Fig 2 skipped — insufficient temperature data.")
        return

    abs_delta = (valid["our_edge_idx"] - valid["Thermistor atm/snow IF"]).abs()
    norm  = mcolors.Normalize(vmin=0, vmax=min(10, abs_delta.quantile(0.95)))
    cmap  = plt.cm.plasma_r

    fig, ax = plt.subplots(figsize=(7, 7))
    sc = ax.scatter(
        valid["T atm/snow IF [°C]"], valid["our_Ts_degC"],
        c=abs_delta, cmap=cmap, norm=norm,
        s=8, alpha=0.5, linewidths=0,
    )
    plt.colorbar(sc, ax=ax, label="|delta_idx| (sensors)")

    lims = [
        min(valid["T atm/snow IF [°C]"].min(), valid["our_Ts_degC"].min()) - 2,
        max(valid["T atm/snow IF [°C]"].max(), valid["our_Ts_degC"].max()) + 2,
    ]
    ax.plot(lims, lims, "k--", lw=1, label="1:1")
    ax.set_xlim(lims)
    ax.set_ylim(lims)

    bias = (valid["our_Ts_degC"] - valid["T atm/snow IF [°C]"]).mean()
    rmse = np.sqrt(((valid["our_Ts_degC"] - valid["T atm/snow IF [°C]"])**2).mean())
    ax.text(
        0.04, 0.96,
        f"Bias = {bias:+.2f} °C\nRMSE = {rmse:.2f} °C\nN = {len(valid):,}",
        transform=ax.transAxes, va="top", fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8),
    )
    ax.set_xlabel("AWI T_atm/snow interface (°C)")
    ax.set_ylabel("Our Ts at edge_idx−1 (°C)")
    ax.set_title(
        f"Interface temperature comparison\nedge_ratio = {edge_ratio}"
    )
    ax.legend(fontsize=9)
    fig.tight_layout()
    out = outdir / f"fig2_temp_scatter_er{edge_ratio:.2f}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out.name}")

# ---------------------------------------------------------------------------
# Figure 3: Flag correlation
# ---------------------------------------------------------------------------
def fig_flag_correlation(both_df, merged_df, edge_ratio, outdir):
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    # Panel A: Mean |delta_idx| ± 1σ per flag
    ax = axes[0]
    flags = [0, 1, 2]
    flag_colors = ["#2ca02c", "#ff7f0e", "#d62728"]
    flag_labels = ["Flag 0\n(Good)", "Flag 1\n(Suspect)", "Flag 2\n(Invalid)"]
    means, stds, ns = [], [], []
    for f in flags:
        sub = (both_df[both_df["our_flag"] == f]["our_edge_idx"]
               - both_df[both_df["our_flag"] == f]["Thermistor atm/snow IF"]).abs()
        means.append(sub.mean() if len(sub) > 0 else 0)
        stds.append(sub.std() if len(sub) > 0 else 0)
        ns.append(len(sub))
    bars = ax.bar(flag_labels, means, yerr=stds, color=flag_colors, alpha=0.8,
                  capsize=5, error_kw={"ecolor": "black", "elinewidth": 1.5})
    for bar, n in zip(bars, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"n={n}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("|delta_idx| (sensors, mean ± 1σ)")
    ax.set_title("Index disagreement by our QC flag")

    # Panel B: Detection agreement fractions per flag
    ax = axes[1]
    awi_has = merged_df["Thermistor atm/snow IF"].notna()
    our_has = merged_df["our_edge_idx"].notna()

    fracs = []
    for f in flags:
        our_f = merged_df["our_flag"] == f
        n_total = our_f.sum()
        if n_total == 0:
            fracs.append((0, 0, 0))
            continue
        n_both_f    = (our_f & awi_has & our_has).sum() / n_total
        n_our_only  = (our_f & our_has & ~awi_has).sum() / n_total
        n_awi_only  = (our_f & ~our_has & awi_has).sum() / n_total
        fracs.append((n_both_f, n_our_only, n_awi_only))

    x = np.arange(len(flags))
    w = 0.6
    b1 = ax.bar(x, [f[0] for f in fracs], w, label="Both detected", color="#1f77b4")
    b2 = ax.bar(x, [f[1] for f in fracs], w, bottom=[f[0] for f in fracs],
                label="Our-only", color="#aec7e8")
    b3 = ax.bar(x, [f[2] for f in fracs], w,
                bottom=[f[0]+f[1] for f in fracs],
                label="AWI-only (our=NaN)", color="#ffbb78")
    ax.set_xticks(x)
    ax.set_xticklabels(flag_labels)
    ax.set_ylabel("Fraction of observations")
    ax.set_ylim(0, 1)
    ax.set_title("Detection agreement by our QC flag")
    ax.legend(fontsize=9)

    fig.suptitle(f"Flag correlation analysis  (edge_ratio = {edge_ratio})", fontsize=12)
    fig.tight_layout()
    out = outdir / f"fig3_flag_corr_er{edge_ratio:.2f}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out.name}")

# ---------------------------------------------------------------------------
# Figure 4: edge_ratio sweep
# ---------------------------------------------------------------------------
def fig_sweep(sweep_results, current_ratio, outdir):
    """
    sweep_results: list of (edge_ratio, stats_dict)
    """
    ratios  = [r for r, _ in sweep_results]
    t_bias  = [s["temp_bias"]  for _, s in sweep_results]
    t_rmse  = [s["temp_rmse"]  for _, s in sweep_results]
    idx_bias = [s["idx_bias"]  for _, s in sweep_results]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))

    for ax, vals, ylabel, title in zip(
        axes,
        [t_bias, t_rmse, idx_bias],
        ["Temperature bias (°C)", "Temperature RMSE (°C)", "Index bias (sensors)"],
        ["Temp bias vs edge_ratio", "Temp RMSE vs edge_ratio", "Index bias vs edge_ratio"],
    ):
        ax.plot(ratios, vals, "o-", color="#1f77b4", lw=2)
        ax.axvline(current_ratio, color="gray", ls="--", lw=1,
                   label=f"Current config ({current_ratio})")
        if "RMSE" in title:
            best_r = ratios[int(np.nanargmin(vals))]
            ax.axvline(best_r, color="red", ls=":", lw=1,
                       label=f"Min RMSE at {best_r}")
        ax.set_xlabel("edge_ratio")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Sensitivity of interface detection to edge_ratio", fontsize=12)
    fig.tight_layout()
    out = outdir / "fig4_sweep.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out.name}")

# ---------------------------------------------------------------------------
# Main comparison logic
# ---------------------------------------------------------------------------
def run_comparison(edge_ratio, buoy_list, cfg_mgr, verbose=True, threshold=0.4375):
    """
    Run comparison for all buoys at the given edge_ratio and threshold.

    Returns (all_both_df, all_merged_df, per_buoy_stats).

    all_both_df contains ALL observations where both sides detected, regardless
    of QC flag. Apply flag filtering downstream, e.g.:
        agg_df = all_both_df[all_both_df["our_flag"] <= max_flag]
    """
    all_both   = []
    all_merged = []
    per_buoy   = []

    n_skip = 0
    for buoy_id in buoy_list:
        try:
            df_string, awi_df = load_buoy_pair(buoy_id, cfg_mgr)
        except Exception as e:
            if verbose:
                print(f"  SKIP {buoy_id}: {e}")
            n_skip += 1
            continue

        try:
            s_interface, qc_df = run_detection(df_string, cfg_mgr, buoy_id, edge_ratio, threshold=threshold)
            merged = compute_matched_df(buoy_id, df_string, awi_df, s_interface, qc_df)
            both   = both_detected(merged)  # unfiltered — all flags retained

            all_both.append(both)
            all_merged.append(merged)

            bs = compute_stats(both, merged)
            bs["buoy_id"] = buoy_id
            per_buoy.append(bs)

            if verbose:
                n = bs["n_both"]
                ib = bs.get("idx_bias", np.nan)
                ibs = f"{ib:+.2f}" if not np.isnan(ib) else "  ---"
                print(f"  {buoy_id:<12}  {n:>5} matched obs   idx_bias={ibs} sensors")
        except Exception as e:
            if verbose:
                print(f"  ERROR {buoy_id}: {e}")
            n_skip += 1
            continue

    if not all_both:
        raise RuntimeError("No valid buoy data found for comparison.")

    all_both_df   = pd.concat(all_both,   ignore_index=True)
    all_merged_df = pd.concat(all_merged, ignore_index=True)

    if verbose and n_skip > 0:
        print(f"  ({n_skip} buoy(s) skipped due to load/processing errors)")

    return all_both_df, all_merged_df, per_buoy

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Compare SIMBA interface detection vs AWI")
    p.add_argument("--edge-ratio", type=float, default=None,
                   help="Override edge_ratio (default: read from buoy_config.yaml)")
    p.add_argument("--threshold", type=float, default=0.4375,
                   help="Peak gradient threshold for detection (default: 0.4375, Liao 2019)")
    p.add_argument("--sweep", action="store_true",
                   help="Sweep edge_ratio over [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]")
    p.add_argument("--sweep-2d", action="store_true",
                   help="2D sweep: edge_ratio x threshold grid, print table of temp_RMSE")
    p.add_argument("--buoy", nargs="+", default=None,
                   help="Restrict comparison to specific buoy IDs")
    p.add_argument("--max-flag", type=int, default=1,
                   help="Aggregate stats include observations with our_flag <= this value "
                        "(0=Good only, 1=Good+Suspect, 2=all). Default=1.")
    return p.parse_args()

def main():
    args = parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cfg_mgr = BuoyConfig(str(CONFIG_PATH))

    # Read current config edge_ratio
    t_conf = cfg_mgr.get_config_for_id("2021T86")
    config_edge_ratio = t_conf.get("algorithm", {}).get("params", {}).get("edge_ratio", 0.2)
    edge_ratio = args.edge_ratio if args.edge_ratio is not None else config_edge_ratio
    threshold  = args.threshold   # default 0.4375
    max_flag   = args.max_flag    # default 1

    # Discover buoys
    if args.buoy:
        buoy_list = args.buoy
        print(f"Comparing {len(buoy_list)} user-specified buoys at edge_ratio={edge_ratio}, threshold={threshold}")
    else:
        buoy_list = find_comparison_buoys()
        print(f"Discovered {len(buoy_list)} buoys with both AWI reference and raw TEMP data.")

    # --- Single run ---
    print(f"\nRunning comparison at edge_ratio = {edge_ratio}, threshold = {threshold}, max_flag = {max_flag} ...\n")
    all_both_df, all_merged_df, per_buoy_stats = run_comparison(
        edge_ratio, buoy_list, cfg_mgr, verbose=True, threshold=threshold
    )

    # Aggregate stats apply the QC filter; flag-stratified stats use the full unfiltered pool
    agg_df = all_both_df[all_both_df["our_flag"] <= max_flag]
    agg    = compute_stats(agg_df, all_merged_df)
    fstats = flag_stratified_stats(all_both_df)
    print_summary(agg, fstats, per_buoy_stats, edge_ratio=edge_ratio, max_flag=max_flag)
    print()
    print_per_year_stats(all_both_df, max_flag=max_flag)

    print("\nGenerating figures ...")
    fig_index_distribution(all_both_df, edge_ratio, OUT_DIR)
    fig_temperature_scatter(all_both_df, edge_ratio, OUT_DIR)
    fig_flag_correlation(all_both_df, all_merged_df, edge_ratio, OUT_DIR)

    # --- 1D edge_ratio sweep ---
    if args.sweep:
        sweep_ratios = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
        sweep_results = []
        print(f"\nRunning sweep over edge_ratio = {sweep_ratios} (threshold={threshold}) ...\n")
        for er in sweep_ratios:
            print(f"  edge_ratio = {er}")
            b_df, _m_df, _ = run_comparison(er, buoy_list, cfg_mgr, verbose=False, threshold=threshold)
            s = compute_stats(b_df[b_df["our_flag"] <= max_flag])
            sweep_results.append((er, s))
            ib = s.get("idx_bias", np.nan)
            tb = s.get("temp_bias", np.nan)
            tr = s.get("temp_rmse", np.nan)
            print(f"    idx_bias={ib:+.3f}  temp_bias={tb:+.3f}  temp_rmse={tr:.3f}")

        fig_sweep(sweep_results, config_edge_ratio, OUT_DIR)

    # --- 2D sweep: edge_ratio x threshold ---
    if args.sweep_2d:
        sweep_ratios     = [0.05, 0.10, 0.20, 0.30, 0.50]
        sweep_thresholds = [0.10, 0.20, 0.30, 0.4375, 0.60, 0.80, 1.00]
        print(f"\nRunning 2D sweep: edge_ratio x threshold ...\n")

        # Header
        hdr = f"{'':>8s}" + "".join(f"  er={er:.2f}" for er in sweep_ratios)
        print(f"  {'thr \\ er':<10}" + "".join(f"  er={er:.2f}" for er in sweep_ratios))
        print("  " + "-" * (10 + 9 * len(sweep_ratios)))

        grid_rmse  = {}
        grid_ibias = {}
        grid_tbias = {}

        for thr in sweep_thresholds:
            row_rmse = []
            row_ib   = []
            row_tb   = []
            for er in sweep_ratios:
                b_df, _m_df, _ = run_comparison(er, buoy_list, cfg_mgr, verbose=False, threshold=thr)
                s = compute_stats(b_df[b_df["our_flag"] <= max_flag])
                row_rmse.append(s.get("temp_rmse",  np.nan))
                row_ib.append(  s.get("idx_bias",   np.nan))
                row_tb.append(  s.get("temp_bias",  np.nan))
            grid_rmse[thr]  = row_rmse
            grid_ibias[thr] = row_ib
            grid_tbias[thr] = row_tb
            cells = "".join(f"  {v:>7.2f}" for v in row_rmse)
            print(f"  thr={thr:.4f}  {cells}")

        print("\n  (values above are temp_RMSE °C)")
        print("\n  Index bias (sensors):")
        print(f"  {'thr \\ er':<10}" + "".join(f"  er={er:.2f}" for er in sweep_ratios))
        print("  " + "-" * (10 + 9 * len(sweep_ratios)))
        for thr in sweep_thresholds:
            cells = "".join(f"  {v:>+7.2f}" for v in grid_ibias[thr])
            print(f"  thr={thr:.4f}  {cells}")

        print("\n  Temp bias (°C):")
        print(f"  {'thr \\ er':<10}" + "".join(f"  er={er:.2f}" for er in sweep_ratios))
        print("  " + "-" * (10 + 9 * len(sweep_ratios)))
        for thr in sweep_thresholds:
            cells = "".join(f"  {v:>+7.2f}" for v in grid_tbias[thr])
            print(f"  thr={thr:.4f}  {cells}")

    print(f"\nAll output saved to {OUT_DIR}/")


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
        main()
