"""
validate_simba.py — Formal validation of SIMBA interface detection against AWI
manual reference (Preußer et al., 2025, PANGAEA).

Produces publication-ready figures, statistical tables, and a PDF report
characterising algorithm performance for use as IST validation reference data.

Usage:
    python validate_simba.py                       # defaults: Flag 0, focus 2020-2023
    python validate_simba.py --max-flag 1          # include Suspect observations
    python validate_simba.py --sweep               # edge_ratio sensitivity analysis
    python validate_simba.py --sweep-2d            # 2D parameter grid
    python validate_simba.py --edge-ratio 0.15     # test alternative config

Output saved to data/AWI_comparison/validation_report/
"""

import argparse
import copy
import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.backends.backend_pdf import PdfPages
from scipy import stats as scipy_stats

# --- Project library imports ---
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.simba_algo import SimbaInterfaceDetector
from lib.simba_qc import SimbaQC
from lib.data_loader import load_buoy_data
from lib.config_manager import BuoyConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).resolve().parent.parent
RAW_DIR     = BASE_DIR / "data" / "raw"
AWI_DIR     = BASE_DIR / "data" / "AWI_official" / "SIMBA_icethick_all" / "datasets"
CONFIG_PATH = BASE_DIR / "buoy_config.yaml"
DEFAULT_OUT = BASE_DIR / "data" / "AWI_comparison" / "validation_report"

SENSOR_SPACING_CM = 2  # cm per thermistor index

# OSI SAF IST product requirements (buoy validation, PRD v3.4 Table 1)
# std and bias in K (equivalent to °C for difference metrics)
PRODUCT_REQUIREMENTS = {
    "threshold": {"std": 4.0, "bias": 4.5},
    "target":    {"std": 3.0, "bias": 3.5},
    "optimal":   {"std": 1.0, "bias": 0.8},
}

# Matplotlib style for publication
plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9,
    "figure.dpi": 100,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,
})

FLAG_COLORS = {0: "#2ca02c", 1: "#ff7f0e", 2: "#d62728"}
FLAG_LABELS = {0: "Flag 0 (Good)", 1: "Flag 1 (Suspect)", 2: "Flag 2 (Invalid)"}
HEMISPHERE_COLORS = {"arctic": "#1b9e77", "antarctic": "#7570b3", "unknown": "#888888"}

# ---------------------------------------------------------------------------
# Data loading (self-contained, adapted from compare_awi.py)
# ---------------------------------------------------------------------------
def find_comparison_buoys():
    """Return sorted list of buoy IDs with both AWI tab file and raw TEMP data."""
    awi_buoys = set()
    for tab in AWI_DIR.glob("*_icethick.tab"):
        awi_buoys.add(tab.name.replace("_icethick.tab", ""))

    raw_buoys = set()
    for f in RAW_DIR.glob("*_TEMP_proc.csv"):
        raw_buoys.add(f.name.split("_")[0])
    for f in RAW_DIR.glob("*_TEMP_raw+filterflag.csv"):
        raw_buoys.add(f.name.split("_")[0])

    return sorted(awi_buoys & raw_buoys)


def load_awi_tab(buoy_id):
    """Load AWI PANGAEA .tab file, return DataFrame indexed by datetime."""
    path = AWI_DIR / f"{buoy_id}_icethick.tab"
    with open(path) as fh:
        lines = fh.readlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "*/") + 1
    df = pd.read_csv(path, sep="\t", skiprows=start, header=0, na_values=[""])
    df["Date/Time"] = pd.to_datetime(df["Date/Time"])
    df = df.set_index("Date/Time").sort_index()
    return df


def load_buoy_pair(buoy_id, cfg_mgr):
    """Load raw thermistor data and AWI reference for a given buoy."""
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


def run_detection(df_string, cfg_mgr, buoy_id, edge_ratio, threshold=0.4375):
    """Run detect_leading_edge and SimbaQC on df_string."""
    detector = SimbaInterfaceDetector(df_string)
    s_interface = detector.detect_leading_edge(edge_ratio=edge_ratio, threshold=threshold)

    base_conf = cfg_mgr.get_config_for_id(buoy_id)
    qc_params = base_conf.get("qc", {}).get("params", {})
    qc = SimbaQC(df_string, s_interface, qc_params=qc_params)
    qc_df = qc.compute_flags()
    return s_interface, qc_df


def extract_surface_temps(df_string, s_interface):
    """Extract temperature at sensor edge_idx - 1 (0-indexed) for each timestamp."""
    vals = np.full(len(s_interface), np.nan)
    str_arr = df_string.values
    str_idx = df_string.index
    n_sensors = str_arr.shape[1]

    for i, (ts, edge_idx) in enumerate(s_interface.items()):
        if pd.isna(edge_idx):
            continue
        col = int(edge_idx) - 1
        if col < 0 or col >= n_sensors:
            continue
        if ts not in str_idx:
            continue
        row = str_idx.get_loc(ts)
        vals[i] = str_arr[row, col]

    return pd.Series(vals, index=s_interface.index)


# ---------------------------------------------------------------------------
# Collect and enrich data
# ---------------------------------------------------------------------------
def collect_all_data(buoy_list, cfg_mgr, edge_ratio, threshold, verbose=True):
    """
    Run comparison for all buoys. Returns enriched DataFrames:
    (all_both_df, all_merged_df, per_buoy_stats)

    all_both_df contains only observations where both sides detected the interface.
    """
    all_both = []
    all_merged = []
    per_buoy = []
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
            s_interface, qc_df = run_detection(
                df_string, cfg_mgr, buoy_id, edge_ratio, threshold
            )
            our_ts = extract_surface_temps(df_string, s_interface)

            our_df = pd.DataFrame({
                "our_edge_idx": s_interface,
                "our_Ts_degC": our_ts,
                "our_flag": qc_df["quality_flag"],
            })

            awi_cols = ["T atm/snow IF [°C]", "Thermistor atm/snow IF",
                        "EsEs [m]", "Snow thick [m]", "Latitude"]
            available_cols = [c for c in awi_cols if c in awi_df.columns]
            merged = our_df.join(awi_df[available_cols], how="inner")
            merged["buoy_id"] = buoy_id

            # Preserve datetime as a column before concat loses the index
            merged["obs_datetime"] = merged.index

            both = merged.dropna(
                subset=["our_edge_idx", "Thermistor atm/snow IF"]
            ).copy()

            all_both.append(both)
            all_merged.append(merged)

            bs = _compute_basic_stats(both)
            bs["buoy_id"] = buoy_id
            bs["n_matched"] = len(merged)
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

    all_both_df = pd.concat(all_both, ignore_index=True)
    all_merged_df = pd.concat(all_merged, ignore_index=True)

    # Enrich with derived columns
    _enrich(all_both_df)
    _enrich(all_merged_df)

    if verbose and n_skip > 0:
        print(f"  ({n_skip} buoy(s) skipped due to load/processing errors)")

    return all_both_df, all_merged_df, per_buoy


def _enrich(df):
    """Add derived columns in-place."""
    df["year"] = df["buoy_id"].str[:4].astype(int)
    if "obs_datetime" in df.columns:
        df["month"] = pd.to_datetime(df["obs_datetime"]).dt.month
    elif df.index.dtype == "datetime64[ns]" or hasattr(df.index, "month"):
        df["month"] = df.index.month
    else:
        df["month"] = np.nan
    if "Latitude" in df.columns:
        df["hemisphere"] = np.where(df["Latitude"] >= 0, "arctic", "antarctic")
    else:
        df["hemisphere"] = "unknown"
    df["delta_idx"] = df["our_edge_idx"] - df["Thermistor atm/snow IF"]
    df["delta_temp"] = df["our_Ts_degC"] - df["T atm/snow IF [°C]"]
    df["abs_delta_idx"] = df["delta_idx"].abs()

    # Temperature regime bins
    awi_t = df["T atm/snow IF [°C]"]
    bins = [-np.inf, -40, -30, -20, -10, 0, np.inf]
    labels = ["< -40", "-40 to -30", "-30 to -20", "-20 to -10", "-10 to 0", "> 0"]
    df["temp_regime"] = pd.cut(awi_t, bins=bins, labels=labels, right=False)


def _compute_basic_stats(both_df):
    """Basic stats for a subset of matched observations."""
    n = len(both_df)
    if n == 0:
        return {"n_both": 0, "idx_bias": np.nan, "idx_mae": np.nan,
                "idx_rmse": np.nan, "idx_std": np.nan,
                "temp_bias": np.nan, "temp_mae": np.nan,
                "temp_rmse": np.nan, "temp_std": np.nan}

    di = both_df["our_edge_idx"] - both_df["Thermistor atm/snow IF"]
    dt = both_df["our_Ts_degC"] - both_df["T atm/snow IF [°C]"]

    def safe(fn, arr):
        a = arr.dropna()
        return fn(a) if len(a) > 0 else np.nan

    return {
        "n_both": n,
        "idx_bias": safe(np.mean, di),
        "idx_mae": safe(lambda x: np.mean(np.abs(x)), di),
        "idx_rmse": safe(lambda x: np.sqrt(np.mean(x**2)), di),
        "idx_std": safe(lambda x: np.std(x, ddof=1), di),
        "temp_bias": safe(np.mean, dt),
        "temp_mae": safe(lambda x: np.mean(np.abs(x)), dt),
        "temp_rmse": safe(lambda x: np.sqrt(np.mean(x**2)), dt),
        "temp_std": safe(lambda x: np.std(x, ddof=1), dt),
    }


# ---------------------------------------------------------------------------
# ValidationStats — full statistical analysis
# ---------------------------------------------------------------------------
class ValidationStats:
    """Compute all validation statistics from matched DataFrames."""

    def __init__(self, both_df, merged_df, focus_years=(2020, 2023)):
        self.both_df = both_df
        self.merged_df = merged_df
        self.focus_years = focus_years

    @staticmethod
    def detailed_stats(df_subset, idx_col="delta_idx", temp_col="delta_temp"):
        """Compute comprehensive stats with 95% confidence intervals."""
        result = {}

        for prefix, col in [("idx", idx_col), ("temp", temp_col)]:
            vals = df_subset[col].dropna()
            n = len(vals)
            result[f"{prefix}_n"] = n

            if n < 2:
                for k in ["bias", "std", "rmse", "mae", "median", "iqr",
                          "bias_ci_lo", "bias_ci_hi", "std_ci_lo", "std_ci_hi",
                          "r", "r2", "r_pvalue"]:
                    result[f"{prefix}_{k}"] = np.nan
                continue

            bias = vals.mean()
            std = vals.std(ddof=1)
            rmse = np.sqrt((vals**2).mean())
            mae = vals.abs().mean()
            median = vals.median()
            q25, q75 = vals.quantile(0.25), vals.quantile(0.75)
            iqr = q75 - q25

            # 95% CI on bias (t-distribution)
            t_crit = scipy_stats.t.ppf(0.975, n - 1)
            bias_ci_half = t_crit * std / np.sqrt(n)
            bias_ci_lo = bias - bias_ci_half
            bias_ci_hi = bias + bias_ci_half

            # 95% CI on std (chi-squared)
            chi2_lo = scipy_stats.chi2.ppf(0.025, n - 1)
            chi2_hi = scipy_stats.chi2.ppf(0.975, n - 1)
            std_ci_lo = np.sqrt((n - 1) * std**2 / chi2_hi)
            std_ci_hi = np.sqrt((n - 1) * std**2 / chi2_lo)

            result.update({
                f"{prefix}_bias": bias,
                f"{prefix}_std": std,
                f"{prefix}_rmse": rmse,
                f"{prefix}_mae": mae,
                f"{prefix}_median": median,
                f"{prefix}_iqr": iqr,
                f"{prefix}_bias_ci_lo": bias_ci_lo,
                f"{prefix}_bias_ci_hi": bias_ci_hi,
                f"{prefix}_std_ci_lo": std_ci_lo,
                f"{prefix}_std_ci_hi": std_ci_hi,
            })

        # Pearson correlation (temperature only)
        our_t = df_subset["our_Ts_degC"].dropna()
        awi_t = df_subset["T atm/snow IF [°C]"].dropna()
        common = our_t.index.intersection(awi_t.index)
        if len(common) > 2:
            r, p = scipy_stats.pearsonr(
                df_subset.loc[common, "our_Ts_degC"],
                df_subset.loc[common, "T atm/snow IF [°C]"]
            )
            result["temp_r"] = r
            result["temp_r2"] = r**2
            result["temp_r_pvalue"] = p
        else:
            result["temp_r"] = np.nan
            result["temp_r2"] = np.nan
            result["temp_r_pvalue"] = np.nan

        return result

    def aggregate(self, max_flag=0):
        """Aggregate stats filtered by max_flag."""
        sub = self.both_df[self.both_df["our_flag"] <= max_flag]
        s = self.detailed_stats(sub)
        s["max_flag"] = max_flag
        s["n_total_matched"] = len(self.merged_df)
        return s

    def per_flag(self):
        """Stats per QC flag."""
        rows = []
        for flag in [0, 1, 2]:
            sub = self.both_df[self.both_df["our_flag"] == flag]
            if len(sub) == 0:
                continue
            s = self.detailed_stats(sub)
            s["flag"] = flag
            rows.append(s)
        return pd.DataFrame(rows)

    def per_buoy(self, max_flag=0):
        """Stats per buoy_id."""
        rows = []
        sub = self.both_df[self.both_df["our_flag"] <= max_flag]
        for bid, grp in sub.groupby("buoy_id"):
            s = self.detailed_stats(grp)
            s["buoy_id"] = bid
            s["year"] = int(bid[:4])
            if "hemisphere" in grp.columns:
                s["hemisphere"] = grp["hemisphere"].mode().iloc[0]
            rows.append(s)
        return pd.DataFrame(rows).sort_values("buoy_id")

    def per_year(self, max_flag=0):
        """Stats per deployment year."""
        rows = []
        sub = self.both_df[self.both_df["our_flag"] <= max_flag]
        for year, grp in sub.groupby("year"):
            s = self.detailed_stats(grp)
            s["year"] = year
            rows.append(s)
        return pd.DataFrame(rows).sort_values("year")

    def per_month(self, max_flag=0):
        """Stats per calendar month."""
        rows = []
        sub = self.both_df[self.both_df["our_flag"] <= max_flag]
        if "month" not in sub.columns or sub["month"].isna().all():
            return pd.DataFrame()
        for month, grp in sub.groupby("month"):
            if pd.isna(month):
                continue
            s = self.detailed_stats(grp)
            s["month"] = int(month)
            rows.append(s)
        return pd.DataFrame(rows).sort_values("month")

    def per_hemisphere(self, max_flag=0):
        """Stats for arctic vs antarctic buoys."""
        rows = []
        sub = self.both_df[self.both_df["our_flag"] <= max_flag]
        if "hemisphere" not in sub.columns:
            return pd.DataFrame()
        for hemi, grp in sub.groupby("hemisphere"):
            s = self.detailed_stats(grp)
            s["hemisphere"] = hemi
            rows.append(s)
        return pd.DataFrame(rows)

    def per_temp_regime(self, max_flag=0):
        """Stats binned by AWI reference temperature."""
        rows = []
        sub = self.both_df[self.both_df["our_flag"] <= max_flag]
        for regime, grp in sub.groupby("temp_regime", observed=True):
            if len(grp) < 5:
                continue
            s = self.detailed_stats(grp)
            s["temp_regime"] = str(regime)
            rows.append(s)
        return pd.DataFrame(rows)

    def normality_test(self, max_flag=0):
        """D'Agostino-Pearson normality test on temperature errors."""
        sub = self.both_df[self.both_df["our_flag"] <= max_flag]
        dt = sub["delta_temp"].dropna()
        if len(dt) < 20:
            return {"statistic": np.nan, "p_value": np.nan, "is_normal": None,
                    "n": len(dt)}
        stat, p = scipy_stats.normaltest(dt)
        return {"statistic": stat, "p_value": p, "is_normal": p > 0.05,
                "n": len(dt)}

    def outlier_analysis(self, max_flag=0, sigma=3):
        """Identify observations with |delta_temp| > sigma*std."""
        sub = self.both_df[self.both_df["our_flag"] <= max_flag].copy()
        dt = sub["delta_temp"]
        std = dt.std(ddof=1)
        mean = dt.mean()
        threshold = sigma * std
        outliers = sub[dt.abs() > threshold].copy()
        outliers["deviation_sigma"] = (outliers["delta_temp"] - mean) / std

        # Also stats without outliers
        clean = sub[dt.abs() <= threshold]
        clean_stats = self.detailed_stats(clean) if len(clean) > 2 else {}

        return outliers, clean_stats

    def product_compliance(self, max_flag=0):
        """Check compliance with OSI SAF product requirements."""
        agg = self.aggregate(max_flag)
        results = {}
        for level, reqs in PRODUCT_REQUIREMENTS.items():
            meets_std = abs(agg["temp_std"]) <= reqs["std"] if not np.isnan(agg["temp_std"]) else False
            meets_bias = abs(agg["temp_bias"]) <= reqs["bias"] if not np.isnan(agg["temp_bias"]) else False
            # Check if CI upper bound still meets requirement
            std_ci_hi = agg.get("temp_std_ci_hi", np.nan)
            bias_ci_hi = max(abs(agg.get("temp_bias_ci_lo", np.nan)),
                            abs(agg.get("temp_bias_ci_hi", np.nan)))
            results[level] = {
                "req_std": reqs["std"],
                "req_bias": reqs["bias"],
                "actual_std": agg["temp_std"],
                "actual_bias": agg["temp_bias"],
                "meets_std": bool(meets_std),
                "meets_bias": bool(meets_bias),
                "meets_both": bool(meets_std and meets_bias),
                "std_ci_upper_meets": bool(std_ci_hi <= reqs["std"]) if not np.isnan(std_ci_hi) else False,
                "bias_ci_upper_meets": bool(bias_ci_hi <= reqs["bias"]) if not np.isnan(bias_ci_hi) else False,
            }
        return results


# ---------------------------------------------------------------------------
# Table writers
# ---------------------------------------------------------------------------
def write_csv(df_or_dict, path):
    """Write DataFrame or dict to CSV."""
    if isinstance(df_or_dict, dict):
        df_or_dict = pd.DataFrame([df_or_dict])
    df_or_dict.to_csv(path, index=False, float_format="%.4f")


def write_latex(df_or_dict, path):
    """Write DataFrame to LaTeX table."""
    if isinstance(df_or_dict, dict):
        df_or_dict = pd.DataFrame([df_or_dict])
    with open(path, "w") as f:
        f.write(df_or_dict.to_latex(index=False, float_format="%.3f",
                                     na_rep="---"))


def save_tables(vstats, outdir, max_flag, write_tex=False):
    """Save all statistical tables."""
    tables_dir = outdir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Aggregate
    agg = vstats.aggregate(max_flag)
    write_csv(agg, tables_dir / "aggregate_stats.csv")

    # Per-flag
    pf = vstats.per_flag()
    if len(pf) > 0:
        write_csv(pf, tables_dir / "per_flag_stats.csv")

    # Per-buoy
    pb = vstats.per_buoy(max_flag)
    if len(pb) > 0:
        write_csv(pb, tables_dir / "per_buoy_stats.csv")

    # Per-year
    py = vstats.per_year(max_flag)
    if len(py) > 0:
        write_csv(py, tables_dir / "per_year_stats.csv")

    # Per-month
    pm = vstats.per_month(max_flag)
    if len(pm) > 0:
        write_csv(pm, tables_dir / "per_month_stats.csv")

    # Per-hemisphere
    pe = vstats.per_hemisphere(max_flag)
    if len(pe) > 0:
        write_csv(pe, tables_dir / "per_hemisphere_stats.csv")

    # Per-temp-regime
    pt = vstats.per_temp_regime(max_flag)
    if len(pt) > 0:
        write_csv(pt, tables_dir / "per_temp_regime_stats.csv")

    # Outliers
    outliers, clean_stats = vstats.outlier_analysis(max_flag)
    if len(outliers) > 0:
        write_csv(outliers[["buoy_id", "our_edge_idx", "Thermistor atm/snow IF",
                            "our_Ts_degC", "T atm/snow IF [°C]", "our_flag",
                            "delta_idx", "delta_temp", "deviation_sigma"]],
                  tables_dir / "outliers.csv")
    if clean_stats:
        write_csv(clean_stats, tables_dir / "stats_without_outliers.csv")

    # Product compliance
    compliance = vstats.product_compliance(max_flag)
    comp_rows = []
    for level, info in compliance.items():
        row = {"level": level}
        row.update(info)
        comp_rows.append(row)
    write_csv(pd.DataFrame(comp_rows), tables_dir / "product_compliance.csv")

    # LaTeX
    if write_tex:
        tex_dir = outdir / "tables_latex"
        tex_dir.mkdir(parents=True, exist_ok=True)
        write_latex(agg, tex_dir / "aggregate_stats.tex")
        if len(py) > 0:
            write_latex(py, tex_dir / "per_year_stats.tex")
        write_latex(pd.DataFrame(comp_rows), tex_dir / "product_compliance.tex")

    print(f"  Tables saved to {tables_dir}/")


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def _savefig(fig, outdir, name, fmt="pdf", dpi=300):
    """Save figure in requested format(s)."""
    figs_dir = outdir / "figures"
    figs_dir.mkdir(parents=True, exist_ok=True)
    if fmt in ("pdf", "both"):
        fig.savefig(figs_dir / f"{name}.pdf", dpi=dpi)
    if fmt in ("png", "both"):
        fig.savefig(figs_dir / f"{name}.png", dpi=dpi)
    plt.close(fig)
    print(f"    {name}")


def fig01_index_distribution(both_df, max_flag, edge_ratio, outdir, fmt, dpi):
    """Histogram of delta_idx by QC flag with fitted normal overlay."""
    sub = both_df[both_df["our_flag"] <= max_flag]
    delta = sub["delta_idx"].dropna()

    if len(delta) < 5:
        print("    fig01 skipped — insufficient data")
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    d_min = max(delta.min() - 1, -30)
    d_max = min(delta.max() + 1, 30)
    bins = np.arange(d_min - 0.5, d_max + 1.5, 1.0)

    # Stacked by flag
    stacked_data = []
    stacked_flags = []
    for flag in [0, 1, 2]:
        if flag > max_flag:
            continue
        s = both_df[both_df["our_flag"] == flag]["delta_idx"].dropna()
        if len(s) > 0:
            stacked_data.append(s)
            stacked_flags.append(flag)

    bottom = np.zeros(len(bins) - 1)
    for flag, data in zip(stacked_flags, stacked_data):
        counts, _ = np.histogram(data, bins=bins)
        ax.bar(0.5 * (bins[:-1] + bins[1:]), counts, width=0.9, bottom=bottom,
               color=FLAG_COLORS[flag], alpha=0.85,
               label=f"{FLAG_LABELS[flag]} (n={len(data)})")
        bottom += counts

    # Normal fit overlay
    mu, sigma = delta.mean(), delta.std(ddof=1)
    x_fit = np.linspace(bins[0], bins[-1], 200)
    y_fit = scipy_stats.norm.pdf(x_fit, mu, sigma) * len(delta) * 1.0  # bin width = 1
    ax.plot(x_fit, y_fit, "k-", lw=1.5, alpha=0.6, label="Normal fit")

    ax.axvline(0, color="black", lw=1.5, ls="--", alpha=0.5)
    ax.axvline(mu, color="navy", lw=1.2, ls=":",
               label=f"Mean = {mu:+.2f} sensors")

    # Secondary x-axis in cm
    ax2 = ax.twiny()
    ax2.set_xlim(np.array(ax.get_xlim()) * SENSOR_SPACING_CM)
    ax2.set_xlabel("Position difference (cm)")

    # Annotation box
    med = delta.median()
    iqr = delta.quantile(0.75) - delta.quantile(0.25)
    ax.text(0.97, 0.95,
            f"Bias = {mu:+.2f} sensors\n"
            f"Std = {sigma:.2f} sensors\n"
            f"Median = {med:+.2f}\n"
            f"IQR = {iqr:.2f}\n"
            f"N = {len(delta):,}",
            transform=ax.transAxes, va="top", ha="right", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))

    ax.set_xlabel("Thermistor index difference (ours − AWI, sensors)")
    ax.set_ylabel("Count")
    ax.set_title(f"Interface detection: index difference\n"
                 f"edge_ratio = {edge_ratio}, flag ≤ {max_flag}")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    _savefig(fig, outdir, "fig01_index_distribution", fmt, dpi)


def _scatter_panel(ax, panel_data, max_flag, lims):
    """Draw a single temperature scatter panel; return (bias, std, rmse, r, n)."""
    sub = panel_data.dropna(subset=["our_Ts_degC", "T atm/snow IF [°C]"])
    for flag in [2, 1, 0]:  # plot Good on top
        if flag > max_flag:
            continue
        fsub = sub[sub["our_flag"] == flag]
        if len(fsub) == 0:
            continue
        ax.scatter(fsub["T atm/snow IF [°C]"], fsub["our_Ts_degC"],
                   c=FLAG_COLORS[flag], s=8, alpha=0.4, linewidths=0,
                   label=f"{FLAG_LABELS[flag]} (n={len(fsub)})")

    ax.plot(lims, lims, "k--", lw=1, label="1:1")
    for level, style, color in [("optimal", "-.", "#2ca02c"),
                                 ("target", ":", "#ff7f0e"),
                                 ("threshold", "--", "#d62728")]:
        b = PRODUCT_REQUIREMENTS[level]["bias"]
        ax.plot(lims, [l + b for l in lims], ls=style, color=color, lw=0.8, alpha=0.6)
        ax.plot(lims, [l - b for l in lims], ls=style, color=color, lw=0.8, alpha=0.6,
                label=f"±{level} ({b} K)")

    ax.set_xlim(lims)
    ax.set_ylim(lims)

    fsub = sub[sub["our_flag"] <= max_flag]
    if len(fsub) < 3:
        return np.nan, np.nan, np.nan, np.nan, 0

    dt = fsub["our_Ts_degC"] - fsub["T atm/snow IF [°C]"]
    bias = dt.mean()
    std = dt.std(ddof=1)
    rmse = np.sqrt((dt**2).mean())
    r, _ = scipy_stats.pearsonr(fsub["T atm/snow IF [°C]"].dropna(),
                                 fsub["our_Ts_degC"].dropna()) if len(fsub) > 2 else (np.nan, None)
    n_outside = len(sub) - len(sub[
        (sub["T atm/snow IF [°C]"].between(lims[0], lims[1])) &
        (sub["our_Ts_degC"].between(lims[0], lims[1]))
    ])
    if n_outside > 0:
        ax.text(0.96, 0.04, f"({n_outside} pts outside range)",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=7, color="red", alpha=0.7)
    return bias, std, rmse, r, len(fsub)


def fig02_temperature_scatter(both_df, max_flag, edge_ratio, focus_years, outdir, fmt, dpi):
    """Temperature scatter: two panels — focus years vs other years."""
    sub = both_df.dropna(subset=["our_Ts_degC", "T atm/snow IF [°C]"])
    if len(sub) < 5:
        print("    fig02 skipped — insufficient data")
        return

    # Common axis limits from all data
    all_temps = pd.concat([sub["T atm/snow IF [°C]"], sub["our_Ts_degC"]]).dropna()
    p01, p99 = all_temps.quantile(0.01), all_temps.quantile(0.99)
    lims = [max(p01 - 5, -70), min(p99 + 5, 10)]

    # Split by focus years
    if focus_years and len(focus_years) == 2:
        fy_lo, fy_hi = focus_years[0], focus_years[1]
        mask_focus = sub["year"].between(fy_lo, fy_hi)
        focus_label = f"{fy_lo}–{fy_hi}"
        other_label = f"Other years (before {fy_lo} or after {fy_hi})"
    else:
        mask_focus = pd.Series(True, index=sub.index)
        focus_label = "All years"
        other_label = ""

    sub_focus = sub[mask_focus]
    sub_other = sub[~mask_focus]

    # Only draw two panels if there is data in both groups
    has_other = len(sub_other) >= 5

    if has_other:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6.5), sharey=True)
    else:
        fig, ax1 = plt.subplots(1, 1, figsize=(7, 7))
        ax2 = None

    bias1, std1, rmse1, r1, n1 = _scatter_panel(ax1, sub_focus, max_flag, lims)
    ax1.set_xlabel("AWI T atm/snow interface (°C)")
    ax1.set_ylabel("Our Ts at edge_idx−1 (°C)")
    ax1.set_title(f"Focus period: {focus_label}")
    ax1.legend(fontsize=7, loc="lower right")
    if not np.isnan(bias1):
        ax1.text(0.04, 0.96,
                 f"Flag ≤ {max_flag}:\n"
                 f"Bias = {bias1:+.2f} °C\n"
                 f"Std = {std1:.2f} °C\n"
                 f"RMSE = {rmse1:.2f} °C\n"
                 f"R² = {r1**2:.3f}\n"
                 f"N = {n1:,}",
                 transform=ax1.transAxes, va="top", fontsize=9,
                 bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))

    if ax2 is not None:
        bias2, std2, rmse2, r2, n2 = _scatter_panel(ax2, sub_other, max_flag, lims)
        ax2.set_xlabel("AWI T atm/snow interface (°C)")
        ax2.set_title(f"Other years")
        ax2.legend(fontsize=7, loc="lower right")
        if not np.isnan(bias2):
            ax2.text(0.04, 0.96,
                     f"Flag ≤ {max_flag}:\n"
                     f"Bias = {bias2:+.2f} °C\n"
                     f"Std = {std2:.2f} °C\n"
                     f"RMSE = {rmse2:.2f} °C\n"
                     f"R² = {r2**2:.3f}\n"
                     f"N = {n2:,}",
                     transform=ax2.transAxes, va="top", fontsize=9,
                     bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))

    fig.suptitle(f"Interface temperature: ours vs AWI  (edge_ratio = {edge_ratio})",
                 fontsize=12)
    fig.tight_layout()
    _savefig(fig, outdir, "fig02_temperature_scatter", fmt, dpi)


def _seasonal_stats(sub_h, months_all):
    """Compute monthly bias/std/CIs for a hemisphere subset."""
    biases, stds, ns = [], [], []
    bias_ci_los, bias_ci_his = [], []
    std_ci_los, std_ci_his = [], []
    for m in months_all:
        msub = sub_h[sub_h["month"] == m]
        dt = msub["delta_temp"].dropna()
        n = len(dt)
        ns.append(n)
        if n < 5:
            biases.append(np.nan); stds.append(np.nan)
            bias_ci_los.append(np.nan); bias_ci_his.append(np.nan)
            std_ci_los.append(np.nan); std_ci_his.append(np.nan)
            continue
        b = dt.mean()
        s = dt.std(ddof=1)
        biases.append(b); stds.append(s)
        t_crit = scipy_stats.t.ppf(0.975, n - 1)
        ci_half = t_crit * s / np.sqrt(n)
        bias_ci_los.append(b - ci_half); bias_ci_his.append(b + ci_half)
        chi2_lo = scipy_stats.chi2.ppf(0.025, n - 1)
        chi2_hi = scipy_stats.chi2.ppf(0.975, n - 1)
        std_ci_los.append(np.sqrt((n - 1) * s**2 / chi2_hi))
        std_ci_his.append(np.sqrt((n - 1) * s**2 / chi2_lo))
    return (np.array(biases), np.array(stds), ns,
            np.array(bias_ci_los), np.array(bias_ci_his),
            np.array(std_ci_los), np.array(std_ci_his))


def _draw_seasonal_panel(ax1, ax2, biases_arr, stds_arr, ns, bias_ci_los,
                          bias_ci_his, std_ci_los, std_ci_his, months_all, title):
    """Draw bias and std panels for one hemisphere."""
    months_arr = np.array(months_all)
    valid = ~np.isnan(biases_arr)
    if valid.any():
        yerr_bias = np.array([biases_arr[valid] - bias_ci_los[valid],
                              bias_ci_his[valid] - biases_arr[valid]])
        ax1.errorbar(months_arr[valid], biases_arr[valid], yerr=yerr_bias,
                     fmt="o-", color="#1f77b4", capsize=4, lw=2, markersize=6)
    ax1.axhline(0, color="black", ls="--", lw=0.8)
    for level, style, color in [("optimal", "-.", "#2ca02c"),
                                 ("target", ":", "#ff7f0e")]:
        b = PRODUCT_REQUIREMENTS[level]["bias"]
        ax1.axhline(b, ls=style, color=color, lw=0.8, alpha=0.7)
        ax1.axhline(-b, ls=style, color=color, lw=0.8, alpha=0.7,
                    label=f"±{level} ({b} K)")
    ax1.set_ylabel("Bias (°C)")
    ax1.set_title(title)
    ax1.legend(fontsize=7)
    for m_val, n_val in zip(months_all, ns):
        ax1.text(m_val, ax1.get_ylim()[0], f"n={n_val}", ha="center",
                 va="bottom", fontsize=6, alpha=0.6)

    if valid.any():
        yerr_std = np.array([stds_arr[valid] - std_ci_los[valid],
                             std_ci_his[valid] - stds_arr[valid]])
        ax2.errorbar(months_arr[valid], stds_arr[valid], yerr=yerr_std,
                     fmt="s-", color="#d62728", capsize=4, lw=2, markersize=6)
    for level, style, color in [("optimal", "-.", "#2ca02c"),
                                 ("target", ":", "#ff7f0e"),
                                 ("threshold", "--", "#d62728")]:
        s_val = PRODUCT_REQUIREMENTS[level]["std"]
        ax2.axhline(s_val, ls=style, color=color, lw=0.8, alpha=0.7,
                    label=f"{level} ({s_val} K)")
    ax2.set_ylabel("Std (°C)")
    ax2.set_xlabel("Month")
    ax2.set_xticks(range(1, 13))
    ax2.set_xticklabels(["J", "F", "M", "A", "M", "J",
                          "J", "A", "S", "O", "N", "D"])
    ax2.legend(fontsize=7)


def fig03_seasonal_cycle(both_df, max_flag, outdir, fmt, dpi):
    """Monthly bias and std split by hemisphere with CI whiskers."""
    sub = both_df[both_df["our_flag"] <= max_flag]
    if "month" not in sub.columns or sub["month"].isna().all():
        print("    fig03 skipped — no month data")
        return

    months_all = list(range(1, 13))

    hemispheres = []
    if "hemisphere" in sub.columns:
        for h in ["arctic", "antarctic"]:
            sh = sub[sub["hemisphere"] == h]
            present_months = sh["month"].dropna().unique()
            if len(present_months) >= 3:
                hemispheres.append((h, sh))
    if not hemispheres:
        # Fallback: treat all data as one group
        hemispheres = [("all", sub)]

    n_hemi = len(hemispheres)
    fig, axes = plt.subplots(2, n_hemi, figsize=(9 * n_hemi, 7), sharex=True,
                             squeeze=False)

    for col, (hemi, sh) in enumerate(hemispheres):
        (biases_arr, stds_arr, ns,
         bias_ci_los, bias_ci_his,
         std_ci_los, std_ci_his) = _seasonal_stats(sh, months_all)
        title = (f"Seasonal cycle — {hemi.capitalize()}\n"
                 f"(flag ≤ {max_flag})")
        _draw_seasonal_panel(axes[0, col], axes[1, col],
                             biases_arr, stds_arr, ns,
                             bias_ci_los, bias_ci_his,
                             std_ci_los, std_ci_his,
                             months_all, title)

    fig.suptitle(f"Seasonal performance by hemisphere (flag ≤ {max_flag})",
                 fontsize=12)
    fig.tight_layout()
    _savefig(fig, outdir, "fig03_seasonal_cycle", fmt, dpi)


def fig04_yearly_trend(both_df, max_flag, focus_years, outdir, fmt, dpi):
    """Year-by-year performance with focus-year highlighting."""
    sub = both_df[both_df["our_flag"] <= max_flag]
    years = sorted(sub["year"].unique())

    if len(years) < 2:
        print("    fig04 skipped — insufficient year coverage")
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    biases, stds, ns = [], [], []
    bias_cis, std_cis = [], []

    for y in years:
        ysub = sub[sub["year"] == y]
        dt = ysub["delta_temp"].dropna()
        n = len(dt)
        ns.append(n)
        if n < 5:
            biases.append(np.nan)
            stds.append(np.nan)
            bias_cis.append(np.nan)
            std_cis.append(np.nan)
            continue
        b = dt.mean()
        s = dt.std(ddof=1)
        biases.append(b)
        stds.append(s)
        t_crit = scipy_stats.t.ppf(0.975, n - 1)
        bias_cis.append(t_crit * s / np.sqrt(n))
        chi2_lo = scipy_stats.chi2.ppf(0.025, n - 1)
        chi2_hi = scipy_stats.chi2.ppf(0.975, n - 1)
        std_cis.append((np.sqrt((n-1)*s**2/chi2_lo) - np.sqrt((n-1)*s**2/chi2_hi)) / 2)

    years_arr = np.array(years)
    biases_arr = np.array(biases)
    stds_arr = np.array(stds)
    valid = ~np.isnan(biases_arr)

    # Highlight focus years
    if focus_years:
        ax1.axvspan(focus_years[0] - 0.5, focus_years[1] + 0.5,
                    alpha=0.1, color="blue", label=f"Focus: {focus_years[0]}-{focus_years[1]}")
        ax2.axvspan(focus_years[0] - 0.5, focus_years[1] + 0.5,
                    alpha=0.1, color="blue")

    # Hemisphere coloring: dominant hemisphere per year
    hemi_by_year = {}
    if "hemisphere" in sub.columns:
        for y, grp in sub.groupby("year"):
            hemi_by_year[y] = grp["hemisphere"].mode().iloc[0]
    colors = [HEMISPHERE_COLORS.get(hemi_by_year.get(y, "unknown"), "#888888")
              for y in years_arr[valid]]

    # Bias
    ax1.errorbar(years_arr[valid], biases_arr[valid],
                 yerr=np.array(bias_cis)[valid],
                 fmt="o", capsize=4, lw=0, elinewidth=1.5, markersize=7,
                 color="gray", ecolor="gray")
    ax1.scatter(years_arr[valid], biases_arr[valid], c=colors, s=50, zorder=5)
    ax1.axhline(0, color="black", ls="--", lw=0.8)
    for level, style, color in [("optimal", "-.", "#2ca02c"),
                                ("target", ":", "#ff7f0e")]:
        b = PRODUCT_REQUIREMENTS[level]["bias"]
        ax1.axhline(b, ls=style, color=color, lw=0.8, alpha=0.7)
        ax1.axhline(-b, ls=style, color=color, lw=0.8, alpha=0.7,
                    label=f"±{level} ({b} K)")
    # Hemisphere legend
    from matplotlib.patches import Patch
    hemi_patches = [Patch(facecolor=HEMISPHERE_COLORS["arctic"], label="Arctic"),
                    Patch(facecolor=HEMISPHERE_COLORS["antarctic"], label="Antarctic")]
    ax1.set_ylabel("Temperature bias (°C)")
    ax1.set_title(f"Year-by-year performance (flag ≤ {max_flag})")
    handles, labels = ax1.get_legend_handles_labels()
    ax1.legend(handles + hemi_patches, labels + ["Arctic", "Antarctic"], fontsize=8)

    # Std
    ax2.errorbar(years_arr[valid], stds_arr[valid],
                 yerr=np.array(std_cis)[valid],
                 fmt="o", capsize=4, lw=0, elinewidth=1.5, markersize=7,
                 color="gray", ecolor="gray")
    ax2.scatter(years_arr[valid], stds_arr[valid], c=colors, s=50, zorder=5)
    for level, style, color in [("optimal", "-.", "#2ca02c"),
                                ("target", ":", "#ff7f0e"),
                                ("threshold", "--", "#d62728")]:
        s_val = PRODUCT_REQUIREMENTS[level]["std"]
        ax2.axhline(s_val, ls=style, color=color, lw=0.8, alpha=0.7,
                    label=f"{level} ({s_val} K)")
    ax2.set_ylabel("Temperature std (°C)")
    ax2.set_xlabel("Deployment year")
    ax2.legend(fontsize=8)

    # N annotations along bottom of bias panel
    for y, n_val in zip(years, ns):
        ax1.text(y, ax1.get_ylim()[0], f"n={n_val}", ha="center",
                 va="bottom", fontsize=7, alpha=0.6, rotation=45)

    ax2.set_xticks(years)
    ax2.set_xticklabels([str(y) for y in years], rotation=45)
    fig.tight_layout()
    _savefig(fig, outdir, "fig04_yearly_trend", fmt, dpi)


def fig05_hemisphere_comparison(both_df, max_flag, outdir, fmt, dpi):
    """Violin plots comparing Arctic vs Antarctic error distributions."""
    sub = both_df[both_df["our_flag"] <= max_flag]
    if "hemisphere" not in sub.columns:
        print("    fig05 skipped — no hemisphere column")
        return

    arctic = sub[sub["hemisphere"] == "arctic"]["delta_temp"].dropna()
    antarctic = sub[sub["hemisphere"] == "antarctic"]["delta_temp"].dropna()

    groups = [(arctic, "Arctic"), (antarctic, "Antarctic")]
    groups = [(d, lbl) for d, lbl in groups if len(d) >= 5]

    if len(groups) < 1:
        print("    fig05 skipped — insufficient hemisphere data")
        return

    fig, ax = plt.subplots(figsize=(7, 5))

    data_vals = [g[0].values for g in groups]
    positions = list(range(1, len(groups) + 1))
    parts = ax.violinplot(data_vals, positions=positions,
                          showmeans=True, showmedians=True, showextrema=False)

    hemi_keys = [lbl.lower() for _, lbl in groups]
    for pc, hkey in zip(parts["bodies"], hemi_keys):
        pc.set_facecolor(HEMISPHERE_COLORS.get(hkey, "#888888"))
        pc.set_alpha(0.6)

    parts["cmeans"].set_color("black")
    parts["cmedians"].set_color("red")

    ax.set_xticks(positions)
    ax.set_xticklabels([lbl for _, lbl in groups])
    ax.set_ylabel("Temperature difference, ours − AWI (°C)")
    ax.set_title(f"Hemisphere comparison (flag ≤ {max_flag})")
    ax.axhline(0, color="black", ls="--", lw=0.8)

    # Annotate after setting xticks so ylim is stable
    for pos, (data, lbl) in zip(positions, groups):
        b = data.mean()
        s = data.std(ddof=1)
        ax.text(pos, ax.get_ylim()[0],
                f"n={len(data)}\nbias={b:+.2f}\nstd={s:.2f}",
                ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    _savefig(fig, outdir, "fig05_hemisphere_comparison", fmt, dpi)


def fig06_temp_regime(both_df, max_flag, outdir, fmt, dpi):
    """Error metrics by AWI reference temperature regime."""
    sub = both_df[both_df["our_flag"] <= max_flag]
    if "temp_regime" not in sub.columns:
        print("    fig06 skipped — no temp_regime column")
        return

    regimes = sub.groupby("temp_regime", observed=True)
    regime_names = []
    biases, stds, ns = [], [], []

    for regime, grp in regimes:
        dt = grp["delta_temp"].dropna()
        if len(dt) < 5:
            continue
        regime_names.append(str(regime))
        biases.append(dt.mean())
        stds.append(dt.std(ddof=1))
        ns.append(len(dt))

    if len(regime_names) < 2:
        print("    fig06 skipped — insufficient temperature regimes")
        return

    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax2 = ax1.twinx()

    x = np.arange(len(regime_names))
    w = 0.35

    ax1.bar(x - w/2, biases, w, color="#1f77b4", alpha=0.8, label="Bias")
    ax1.bar(x + w/2, stds, w, color="#d62728", alpha=0.8, label="Std")
    ax2.bar(x, ns, 2*w, color="gray", alpha=0.15, label="N")

    ax1.axhline(0, color="black", ls="--", lw=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(regime_names, rotation=30, ha="right")
    ax1.set_xlabel("AWI reference temperature regime (°C)")
    ax1.set_ylabel("Bias / Std (°C)")
    ax2.set_ylabel("Number of observations")
    ax1.set_title(f"Performance by temperature regime (flag ≤ {max_flag})")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8)

    fig.tight_layout()
    _savefig(fig, outdir, "fig06_temp_regime", fmt, dpi)


def fig07_parameter_sensitivity(buoy_list, cfg_mgr, max_flag, outdir, fmt, dpi,
                                 current_ratio, sweep_1d=False, sweep_2d=False):
    """Parameter sensitivity with OSI SAF requirement context."""
    if not sweep_1d and not sweep_2d:
        return None

    sweep_results = None

    if sweep_1d:
        sweep_ratios = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
        sweep_results = []
        print("\n  Running 1D edge_ratio sweep ...")
        for er in sweep_ratios:
            print(f"    edge_ratio = {er}")
            b_df, _m_df, _ = collect_all_data(
                buoy_list, cfg_mgr, er, 0.4375, verbose=False
            )
            _enrich(b_df)
            fsub = b_df[b_df["our_flag"] <= max_flag]
            dt = fsub["delta_temp"].dropna()
            di = fsub["delta_idx"].dropna()
            sweep_results.append({
                "edge_ratio": er,
                "temp_bias": dt.mean() if len(dt) > 0 else np.nan,
                "temp_std": dt.std(ddof=1) if len(dt) > 1 else np.nan,
                "temp_rmse": np.sqrt((dt**2).mean()) if len(dt) > 0 else np.nan,
                "idx_bias": di.mean() if len(di) > 0 else np.nan,
                "n": len(dt),
            })

        fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
        ratios = [s["edge_ratio"] for s in sweep_results]

        for ax, key, ylabel, title in zip(
            axes,
            ["temp_bias", "temp_std", "temp_rmse"],
            ["Temperature bias (°C)", "Temperature std (°C)", "Temperature RMSE (°C)"],
            ["Bias vs edge_ratio", "Std vs edge_ratio", "RMSE vs edge_ratio"],
        ):
            vals = [s[key] for s in sweep_results]
            ax.plot(ratios, vals, "o-", color="#1f77b4", lw=2, markersize=6)
            ax.axvline(current_ratio, color="gray", ls="--", lw=1,
                       label=f"Current ({current_ratio})")

            # OSI SAF requirement lines
            req_key = "bias" if "bias" in key else "std"
            for level, style, color in [("optimal", "-.", "#2ca02c"),
                                        ("target", ":", "#ff7f0e"),
                                        ("threshold", "--", "#d62728")]:
                req_val = PRODUCT_REQUIREMENTS[level][req_key]
                ax.axhline(req_val, ls=style, color=color, lw=0.8, alpha=0.7,
                           label=f"{level} ({req_val})")
                if "bias" in key:
                    ax.axhline(-req_val, ls=style, color=color, lw=0.8, alpha=0.7)

            ax.set_xlabel("edge_ratio")
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            ax.legend(fontsize=7)
            ax.grid(True, alpha=0.3)

        fig.suptitle(f"Parameter sensitivity (flag ≤ {max_flag})", fontsize=12)
        fig.tight_layout()
        _savefig(fig, outdir, "fig07_parameter_sensitivity", fmt, dpi)

        # Save sweep table
        tables_dir = outdir / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        write_csv(pd.DataFrame(sweep_results), tables_dir / "sweep_1d.csv")

    if sweep_2d:
        sweep_ratios = [0.05, 0.10, 0.20, 0.30, 0.50]
        sweep_thresholds = [0.10, 0.20, 0.30, 0.4375, 0.60, 0.80, 1.00]
        print("\n  Running 2D edge_ratio × threshold sweep ...")

        grid = np.full((len(sweep_thresholds), len(sweep_ratios)), np.nan)
        grid_bias = np.full_like(grid, np.nan)
        all_2d_results = []

        for i, thr in enumerate(sweep_thresholds):
            for j, er in enumerate(sweep_ratios):
                print(f"    thr={thr:.4f}  er={er:.2f}")
                b_df, _, _ = collect_all_data(
                    buoy_list, cfg_mgr, er, thr, verbose=False
                )
                _enrich(b_df)
                fsub = b_df[b_df["our_flag"] <= max_flag]
                dt = fsub["delta_temp"].dropna()
                rmse = np.sqrt((dt**2).mean()) if len(dt) > 0 else np.nan
                bias = dt.mean() if len(dt) > 0 else np.nan
                grid[i, j] = rmse
                grid_bias[i, j] = bias
                all_2d_results.append({
                    "threshold": thr, "edge_ratio": er,
                    "temp_rmse": rmse, "temp_bias": bias, "n": len(dt),
                })

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

        for ax, data, title, cmap in [(ax1, grid, "Temp RMSE (°C)", "YlOrRd"),
                                       (ax2, grid_bias, "Temp Bias (°C)", "RdBu_r")]:
            im = ax.imshow(data, aspect="auto", origin="lower",
                          extent=[sweep_ratios[0], sweep_ratios[-1],
                                  sweep_thresholds[0], sweep_thresholds[-1]],
                          cmap=cmap)
            plt.colorbar(im, ax=ax)
            ax.set_xlabel("edge_ratio")
            ax.set_ylabel("threshold (°C)")
            ax.set_title(title)
            ax.plot(current_ratio, 0.4375, "w*", markersize=15, markeredgecolor="black")

        fig.suptitle(f"2D parameter sensitivity (flag ≤ {max_flag})", fontsize=12)
        fig.tight_layout()
        _savefig(fig, outdir, "fig07b_2d_sensitivity", fmt, dpi)

        tables_dir = outdir / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        write_csv(pd.DataFrame(all_2d_results), tables_dir / "sweep_2d.csv")

    return sweep_results


def fig08_per_buoy(both_df, max_flag, outdir, fmt, dpi):
    """Per-buoy dot plot showing bias ± std, color-coded by hemisphere."""
    sub = both_df[both_df["our_flag"] <= max_flag]

    buoy_stats = []
    for bid, grp in sub.groupby("buoy_id"):
        dt = grp["delta_temp"].dropna()
        if len(dt) < 3:
            continue
        hemi = grp["hemisphere"].mode().iloc[0] if "hemisphere" in grp.columns else "unknown"
        buoy_stats.append({
            "buoy_id": bid,
            "bias": dt.mean(),
            "std": dt.std(ddof=1),
            "n": len(dt),
            "year": int(bid[:4]),
            "hemisphere": hemi,
        })

    if len(buoy_stats) < 2:
        print("    fig08 skipped — insufficient buoys")
        return

    bdf = pd.DataFrame(buoy_stats).sort_values("year")

    fig_height = max(5, len(bdf) * 0.3)
    fig, ax = plt.subplots(figsize=(8, fig_height))

    y_pos = np.arange(len(bdf))
    colors = [HEMISPHERE_COLORS.get(row["hemisphere"], "#888888") for _, row in bdf.iterrows()]

    ax.errorbar(bdf["bias"], y_pos, xerr=bdf["std"],
                fmt="none", ecolor="gray", elinewidth=1, capsize=2, alpha=0.5)
    ax.scatter(bdf["bias"], y_pos, c=colors, s=40, zorder=5)

    ax.axvline(0, color="black", ls="--", lw=0.8)

    # OSI SAF lines
    for level, style, color in [("optimal", "-.", "#2ca02c"),
                                ("target", ":", "#ff7f0e")]:
        b = PRODUCT_REQUIREMENTS[level]["bias"]
        ax.axvline(b, ls=style, color=color, lw=0.8, alpha=0.5)
        ax.axvline(-b, ls=style, color=color, lw=0.8, alpha=0.5)

    ax.set_yticks(y_pos)
    ax.set_yticklabels([f"{row['buoy_id']} (n={row['n']})"
                        for _, row in bdf.iterrows()], fontsize=8)
    ax.set_xlabel("Temperature bias ± std (°C)")
    ax.set_title(f"Per-buoy performance (flag ≤ {max_flag})")

    # Hemisphere legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=HEMISPHERE_COLORS["arctic"], label="Arctic"),
        Patch(facecolor=HEMISPHERE_COLORS["antarctic"], label="Antarctic"),
    ]
    ax.legend(handles=legend_elements, fontsize=8, loc="lower right")

    fig.tight_layout()
    _savefig(fig, outdir, "fig08_per_buoy", fmt, dpi)


# ---------------------------------------------------------------------------
# Summary text and run config
# ---------------------------------------------------------------------------
def write_summary(vstats, agg, compliance, norm_test, outliers, clean_stats,
                  max_flag, edge_ratio, threshold, n_buoys, outdir):
    """Write human-readable validation summary."""
    summary_dir = outdir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("=" * 72)
    lines.append("  SIMBA Interface Detection — Validation Summary")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"  Algorithm:        Leading edge (simba_algo.detect_leading_edge)")
    lines.append(f"  edge_ratio:       {edge_ratio}")
    lines.append(f"  threshold:        {threshold} °C")
    lines.append(f"  Primary QC filter: flag ≤ {max_flag}")
    lines.append(f"  Buoys processed:  {n_buoys}")
    lines.append(f"  Reference:        AWI Preußer et al. 2025 (PANGAEA)")
    lines.append("")

    lines.append("  --- Aggregate Statistics (Flag ≤ {}) ---".format(max_flag))
    lines.append(f"  N (matched, both detected):  {agg['temp_n']}")
    lines.append(f"  Temperature bias:  {agg['temp_bias']:+.3f} °C  "
                 f"(95% CI: [{agg['temp_bias_ci_lo']:+.3f}, {agg['temp_bias_ci_hi']:+.3f}])")
    lines.append(f"  Temperature std:   {agg['temp_std']:.3f} °C  "
                 f"(95% CI: [{agg['temp_std_ci_lo']:.3f}, {agg['temp_std_ci_hi']:.3f}])")
    lines.append(f"  Temperature RMSE:  {agg['temp_rmse']:.3f} °C")
    lines.append(f"  Temperature MAE:   {agg['temp_mae']:.3f} °C")
    lines.append(f"  Pearson R:         {agg['temp_r']:.4f}  (R² = {agg['temp_r2']:.4f})")
    lines.append(f"  Median error:      {agg['temp_median']:+.3f} °C")
    lines.append(f"  IQR:               {agg['temp_iqr']:.3f} °C")
    lines.append("")

    lines.append(f"  Index bias:        {agg['idx_bias']:+.3f} sensors "
                 f"({agg['idx_bias']*SENSOR_SPACING_CM:+.1f} cm)")
    lines.append(f"  Index std:         {agg['idx_std']:.3f} sensors "
                 f"({agg['idx_std']*SENSOR_SPACING_CM:.1f} cm)")
    lines.append(f"  Index RMSE:        {agg['idx_rmse']:.3f} sensors")
    lines.append("")

    lines.append("  --- Normality Test (D'Agostino-Pearson) ---")
    if norm_test["p_value"] is not None and not np.isnan(norm_test["p_value"]):
        normal_str = "YES" if norm_test["is_normal"] else "NO"
        lines.append(f"  p-value:   {norm_test['p_value']:.4e}  → Normal: {normal_str}")
        if not norm_test["is_normal"]:
            lines.append("  Note: Error distribution is non-Gaussian. "
                        "IQR may be more appropriate than std.")
    else:
        lines.append("  Insufficient data for normality test.")
    lines.append("")

    lines.append(f"  --- Outlier Analysis (|delta_temp| > 3σ) ---")
    lines.append(f"  Outliers found: {len(outliers)}")
    if clean_stats:
        lines.append(f"  Stats without outliers: bias={clean_stats.get('temp_bias', np.nan):+.3f}, "
                     f"std={clean_stats.get('temp_std', np.nan):.3f}, "
                     f"RMSE={clean_stats.get('temp_rmse', np.nan):.3f}")
    lines.append("")

    lines.append("  --- OSI SAF Product Compliance ---")
    lines.append("  (Requirements are for satellite-vs-buoy validation;")
    lines.append("   these algorithm-vs-reference numbers are a lower bound)")
    lines.append("")
    lines.append(f"  {'Level':<12}  {'Req std':>8}  {'Our std':>8}  {'Pass':>5}  "
                 f"{'Req bias':>9}  {'Our |bias|':>10}  {'Pass':>5}")
    lines.append(f"  {'-'*60}")
    for level, info in compliance.items():
        s_pass = "YES" if info["meets_std"] else "NO"
        b_pass = "YES" if info["meets_bias"] else "NO"
        lines.append(f"  {level:<12}  {info['req_std']:>8.1f}  {info['actual_std']:>8.3f}  "
                     f"{s_pass:>5}  {info['req_bias']:>9.1f}  "
                     f"{abs(info['actual_bias']):>10.3f}  {b_pass:>5}")
    lines.append("")

    lines.append("  Note: Temperature differences in °C are equivalent to K")
    lines.append("  since they are difference metrics (ΔT).")
    lines.append("=" * 72)

    text = "\n".join(lines)
    with open(summary_dir / "validation_summary.txt", "w") as f:
        f.write(text)

    print(f"\n{text}\n")


def write_run_config(args, buoy_list, outdir):
    """Save run configuration for reproducibility."""
    summary_dir = outdir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "timestamp": datetime.now().isoformat(),
        "edge_ratio": args.edge_ratio,
        "threshold": args.threshold,
        "max_flag": args.max_flag,
        "focus_years": args.focus_years,
        "buoy_list": buoy_list,
        "n_buoys": len(buoy_list),
        "sweep_1d": args.sweep,
        "sweep_2d": args.sweep_2d,
        "format": args.format,
        "dpi": args.dpi,
    }

    # Try to add git hash
    try:
        import subprocess
        result = subprocess.run(["git", "rev-parse", "HEAD"],
                                capture_output=True, text=True, cwd=str(BASE_DIR))
        if result.returncode == 0:
            config["git_hash"] = result.stdout.strip()
    except Exception:
        pass

    with open(summary_dir / "run_config.json", "w") as f:
        json.dump(config, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# PDF report assembly
# ---------------------------------------------------------------------------
def assemble_pdf_report(outdir, vstats, agg, compliance, max_flag, edge_ratio, threshold):
    """Combine all figures and summary into a single PDF report."""
    report_path = outdir / "validation_report.pdf"
    figs_dir = outdir / "figures"

    with PdfPages(str(report_path)) as pdf:
        # Title page
        fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4
        ax.axis("off")

        title_text = (
            "SIMBA Interface Detection\n"
            "Validation Report\n"
            "\n"
            f"Algorithm: Leading Edge (edge_ratio={edge_ratio}, threshold={threshold})\n"
            f"Reference: AWI Preußer et al. 2025 (PANGAEA)\n"
            f"Primary QC filter: Flag ≤ {max_flag}\n"
            f"\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d')}\n"
        )
        ax.text(0.5, 0.7, title_text, transform=ax.transAxes,
                ha="center", va="center", fontsize=16,
                fontfamily="serif", linespacing=1.8)

        # Summary stats on title page
        summary_text = (
            f"N = {agg['temp_n']:,} matched observations\n"
            f"Temperature bias = {agg['temp_bias']:+.3f} °C\n"
            f"Temperature std = {agg['temp_std']:.3f} °C\n"
            f"Temperature RMSE = {agg['temp_rmse']:.3f} °C\n"
            f"Pearson R² = {agg['temp_r2']:.4f}\n"
        )
        ax.text(0.5, 0.35, summary_text, transform=ax.transAxes,
                ha="center", va="center", fontsize=12,
                fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.5", fc="#f0f0f0", ec="gray"))

        # Compliance summary
        comp_lines = ["OSI SAF Product Compliance:"]
        for level, info in compliance.items():
            status = "PASS" if info["meets_both"] else "FAIL"
            comp_lines.append(f"  {level:<12}: {status}  "
                            f"(std={info['actual_std']:.2f}/{info['req_std']:.1f}, "
                            f"|bias|={abs(info['actual_bias']):.2f}/{info['req_bias']:.1f})")
        ax.text(0.5, 0.12, "\n".join(comp_lines), transform=ax.transAxes,
                ha="center", va="center", fontsize=10, fontfamily="monospace")

        pdf.savefig(fig)
        plt.close(fig)

        # Include each figure — use PNG versions for embedding
        figure_files = sorted(figs_dir.glob("fig*.png"))

        captions = {
            "fig01": "Figure 1: Distribution of thermistor index differences between our "
                     "automated detection and AWI manual classification.",
            "fig02": "Figure 2: Scatter plot of surface temperatures split by time period "
                     "(focus years vs other years). Dashed lines show OSI SAF accuracy "
                     "requirement bands.",
            "fig03": "Figure 3: Seasonal performance cycle showing monthly bias and "
                     "standard deviation with 95% confidence intervals, split by hemisphere "
                     "(Arctic / Antarctic).",
            "fig04": "Figure 4: Year-by-year performance trend. Marker colour indicates "
                     "hemisphere (green = Arctic, purple = Antarctic).",
            "fig05": "Figure 5: Comparison of error distributions between Arctic and "
                     "Antarctic buoys.",
            "fig06": "Figure 6: Algorithm performance stratified by AWI reference "
                     "temperature regime.",
            "fig07": "Figure 7: Sensitivity of validation metrics to the edge_ratio "
                     "parameter, with OSI SAF requirement levels.",
            "fig07b": "Figure 7b: 2D sensitivity of RMSE and bias across edge_ratio "
                      "and threshold parameter space.",
            "fig08": "Figure 8: Per-buoy performance overview showing bias ± standard "
                     "deviation for each buoy. Colour indicates hemisphere.",
        }

        for fig_file in figure_files:
            stem = fig_file.stem
            fig_key = stem.split("_")[0]
            caption = captions.get(fig_key, f"Figure: {stem}")

            img = plt.imread(str(fig_file))
            h, w = img.shape[:2]
            # Scale to fit A4 width (8.27 inches) with margins
            fig_w = 7.5
            fig_h = fig_w * h / w
            # Add space for caption
            page_h = fig_h + 1.5

            fig_page = plt.figure(figsize=(8.27, max(page_h, 5)))
            # Image axes (leave room for caption below)
            margin = 1.2 / page_h
            img_ax = fig_page.add_axes([0.05, margin, 0.9, 1.0 - margin - 0.02])
            img_ax.imshow(img)
            img_ax.axis("off")

            # Caption at bottom
            fig_page.text(0.5, 0.02, caption, ha="center", va="bottom",
                         fontsize=10, wrap=True,
                         fontfamily="serif", style="italic",
                         transform=fig_page.transFigure)

            pdf.savefig(fig_page)
            plt.close(fig_page)

    print(f"\n  PDF report saved to: {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="SIMBA interface detection validation report generator"
    )
    p.add_argument("--edge-ratio", type=float, default=None,
                   help="Override edge_ratio (default: from buoy_config.yaml)")
    p.add_argument("--threshold", type=float, default=0.4375,
                   help="Peak gradient threshold (default: 0.4375)")
    p.add_argument("--max-flag", type=int, default=0,
                   help="Primary stats include flag ≤ this (default: 0 = Good only)")
    p.add_argument("--buoy", nargs="+", default=None,
                   help="Restrict to specific buoy IDs")
    p.add_argument("--focus-years", type=int, nargs=2, default=[2020, 2023],
                   help="Focus year range for highlighted analysis (default: 2020 2023)")
    p.add_argument("--sweep", action="store_true",
                   help="Run 1D edge_ratio sensitivity sweep")
    p.add_argument("--sweep-2d", action="store_true",
                   help="Run 2D edge_ratio × threshold grid")
    p.add_argument("--format", choices=["png", "pdf", "both"], default="pdf",
                   help="Figure output format (default: pdf)")
    p.add_argument("--dpi", type=int, default=300,
                   help="Figure resolution (default: 300)")
    p.add_argument("--latex", action="store_true",
                   help="Also produce LaTeX table files")
    p.add_argument("--outdir", type=str, default=None,
                   help="Override output directory")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()

    outdir = Path(args.outdir) if args.outdir else DEFAULT_OUT
    outdir.mkdir(parents=True, exist_ok=True)

    cfg_mgr = BuoyConfig(str(CONFIG_PATH))

    # Resolve edge_ratio
    t_conf = cfg_mgr.get_config_for_id("2021T86")
    config_edge_ratio = t_conf.get("algorithm", {}).get("params", {}).get("edge_ratio", 0.2)
    edge_ratio = args.edge_ratio if args.edge_ratio is not None else config_edge_ratio
    # Store resolved value back for run_config
    args.edge_ratio = edge_ratio
    threshold = args.threshold
    max_flag = args.max_flag
    focus_years = tuple(args.focus_years)

    # Discover buoys
    if args.buoy:
        buoy_list = args.buoy
    else:
        buoy_list = find_comparison_buoys()
    print(f"Discovered {len(buoy_list)} buoys for comparison.")
    print(f"Config: edge_ratio={edge_ratio}, threshold={threshold}, "
          f"max_flag={max_flag}, focus_years={focus_years}")

    # --- Collect data ---
    print(f"\nLoading data and running detection ...\n")
    all_both_df, all_merged_df, per_buoy_raw = collect_all_data(
        buoy_list, cfg_mgr, edge_ratio, threshold, verbose=True
    )

    n_buoys_processed = len(per_buoy_raw)
    print(f"\n  {n_buoys_processed} buoys processed, "
          f"{len(all_both_df)} matched observations (both detected)")

    # --- Statistics ---
    print("\nComputing statistics ...")
    vstats = ValidationStats(all_both_df, all_merged_df, focus_years)
    agg = vstats.aggregate(max_flag)
    compliance = vstats.product_compliance(max_flag)
    norm_test = vstats.normality_test(max_flag)
    outliers, clean_stats = vstats.outlier_analysis(max_flag)

    # --- Tables ---
    print("\nSaving tables ...")
    save_tables(vstats, outdir, max_flag, write_tex=args.latex)

    # --- Figures ---
    print("\nGenerating figures ...")
    fig01_index_distribution(all_both_df, max_flag, edge_ratio, outdir,
                             args.format, args.dpi)
    fig02_temperature_scatter(all_both_df, max_flag, edge_ratio, focus_years, outdir,
                              args.format, args.dpi)
    fig03_seasonal_cycle(all_both_df, max_flag, outdir, args.format, args.dpi)
    fig04_yearly_trend(all_both_df, max_flag, focus_years, outdir,
                       args.format, args.dpi)
    fig05_hemisphere_comparison(all_both_df, max_flag, outdir, args.format, args.dpi)
    fig06_temp_regime(all_both_df, max_flag, outdir, args.format, args.dpi)
    fig07_parameter_sensitivity(buoy_list, cfg_mgr, max_flag, outdir,
                                 args.format, args.dpi, edge_ratio,
                                 sweep_1d=args.sweep, sweep_2d=args.sweep_2d)
    fig08_per_buoy(all_both_df, max_flag, outdir, args.format, args.dpi)

    # --- Summary ---
    write_summary(vstats, agg, compliance, norm_test, outliers, clean_stats,
                  max_flag, edge_ratio, threshold, n_buoys_processed, outdir)
    write_run_config(args, buoy_list, outdir)

    # --- PDF report ---
    print("\nAssembling PDF report ...")
    # Always generate PNG versions for embedding in the combined PDF
    if args.format != "both" and args.format != "png":
        print("  (generating PNG copies for PDF embedding)")
        fig01_index_distribution(all_both_df, max_flag, edge_ratio, outdir, "png", args.dpi)
        fig02_temperature_scatter(all_both_df, max_flag, edge_ratio, focus_years, outdir, "png", args.dpi)
        fig03_seasonal_cycle(all_both_df, max_flag, outdir, "png", args.dpi)
        fig04_yearly_trend(all_both_df, max_flag, focus_years, outdir, "png", args.dpi)
        fig05_hemisphere_comparison(all_both_df, max_flag, outdir, "png", args.dpi)
        fig06_temp_regime(all_both_df, max_flag, outdir, "png", args.dpi)
        fig08_per_buoy(all_both_df, max_flag, outdir, "png", args.dpi)

    assemble_pdf_report(outdir, vstats, agg, compliance, max_flag,
                        edge_ratio, threshold)

    print(f"\nAll output saved to {outdir}/")


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
        main()
