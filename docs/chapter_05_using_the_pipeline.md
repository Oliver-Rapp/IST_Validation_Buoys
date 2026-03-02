# 5. Using the Pipeline

This chapter is a practical guide to running the pipeline. It covers environment setup, the directory layout the scripts expect, the command-line interface of the main processing script, the configuration file, and the output format.

---

## 5.1 Environment Setup

The pipeline requires Python 3 with the following packages:

| Package | Purpose |
|---|---|
| `numpy`, `pandas` | Core numerical and tabular data handling |
| `scipy` | Signal processing in the interface-detection algorithm |
| `matplotlib` | All visualizations |
| `cartopy`, `shapely` | Map projections in the viewers (optional — only needed by the visualization scripts) |
| `xarray`, `netcdf4` | Reading SvalMIZ NetCDF files |
| `pyyaml` | Parsing the configuration file |
| `requests`, `tqdm` | Downloading AWI data |

A `requirements.txt` is provided for pip installation:

```bash
pip install -r requirements.txt
```


A `shell.nix` is also provided for Nix users, which handles all dependencies including system libraries:

```bash
nix-shell
```

---

## 5.2 Repository and Data Layout

The pipeline assumes the following directory structure. Items marked `[created automatically]` are generated on first run.

```
Interfacer/
├── ist_buoy_validation_data.py      # Main processing script
├── buoy_config.yaml                 # Configuration file
├── lib/                             # Processing library
├── visualization/                   # Diagnostic and comparison scripts (see Section 5.6)
├── shell.nix                        # Nix environment (optional)
│
└── data/
    ├── raw/                         # Input data root [created automatically]
    │   ├── 2024I15_TEMP_proc.csv    # AWI CSV files (extracted automatically)
    │   ├── 2024I15_AUX_proc.csv
    │   ├── ...
    │   └── 2025_KVS_deployment_hourly_MIP.nc   # SvalMIZ NetCDF (manual)
    │
    └── validation_output/
        └── ist_txt/                 # Output files [created automatically]
            ├── 2024/
            │   ├── BUOYS_202401010000.txt
            │   └── ...
            └── 2025/
                └── ...
```

The AWI CSV files are downloaded and extracted automatically into `data/raw/` at the start of each run (unless `--skip-download` is set). The SvalMIZ NetCDF file must be placed manually into `data/raw/` because it is distributed separately by MET Norway. The script searches for any file matching `*hourly_MIP.nc` recursively under the input directory, so it will be found wherever it is placed within that tree.

---

## 5.3 Running the Main Script

The entry point is `ist_buoy_validation_data.py`. In its simplest form:

```bash
python ist_buoy_validation_data.py
```

This will:
1. Download the full Arctic and Antarctic AWI datasets from Meereisportal.
2. Process all buoy types found in `data/raw/`.
3. Write output files to `data/validation_output/ist_txt/`.

The date range and other settings are read from `buoy_config.yaml` (see Section 5.4).

### 5.3.1 Command-Line Arguments

All arguments are optional. CLI arguments override their corresponding values in the configuration file where both exist.

| Argument | Default | Description |
|---|---|---|
| `--config PATH` | `buoy_config.yaml` | Path to the YAML configuration file. |
| `--input DIR` | `./data/raw/` | Directory containing the raw buoy data. Can also be set via the `BUOY_DATA_DIR` environment variable. |
| `--output DIR` | `./data/validation_output/ist_txt/` | Directory where output `.txt` files are written. Wiped clean at the start of each run. |
| `--start YYYY-MM-DD` | Value in config | Start of the date filter. Observations before this date are excluded. |
| `--end YYYY-MM-DD` | Value in config | End of the date filter. |
| `--skip-download` | *(flag)* | Skip the AWI download step entirely and process whatever is already in the input directory. Useful for re-running the pipeline after changing QC parameters. |
| `--verbose` | *(flag)* | Enable debug-level logging. |

### 5.3.2 Common Usage Patterns

**Re-run without re-downloading (fastest, e.g. after tuning QC thresholds):**

```bash
python ist_buoy_validation_data.py --skip-download
```

**Process a specific time window, overriding the config:**

```bash
python ist_buoy_validation_data.py --skip-download --start 2024-10-01 --end 2025-04-30
```


**Use a custom config file (e.g. for Antarctic-only processing with different QC settings):**

```bash
python ist_buoy_validation_data.py --config my_custom_config.yaml --skip-download
```

---

## 5.4 The Configuration File

`buoy_config.yaml` has two top-level sections: `defaults`, which contains settings that apply to the whole run, and `buoy_types`, which defines how each instrument type is processed.

### 5.4.1 The `defaults` Section

```yaml
defaults:
  output_dir: "./data/validation_output/ist_txt/"
  output_prefix: "BUOYS_"
  undef_float: -99.9
  undef_int: -9
  undef_dd: -99

  always_download: true       # Set to false to never auto-download
  start_date: "2024-01-01"
  end_date: "2026-01-01"
  year_buffer: 3              # Keep buoys deployed up to 3 years before start_date

  export_flags: [-9, 0, 1, 2] # Which QC flags to include in the output

  awi_urls:
    Arctic: "https://..."
    Antarctic: "https://..."
```

**Key settings:**

- **`always_download`**: When `true`, the AWI archives are re-downloaded and the raw data directory is wiped on every run. Set to `false` if you want to preserve a specific downloaded snapshot or avoid repeated network traffic. The `--skip-download` CLI flag overrides this and always disables the download regardless of the YAML value.

- **`start_date` / `end_date`**: The time window for output. Observations outside this window are discarded after loading. CLI arguments `--start` and `--end` override these values.

- **`year_buffer`**: When downloading, buoys deployed in years earlier than `start_date.year - year_buffer` are discarded during extraction. This keeps disk usage manageable without risking loss of active buoys that were deployed in prior years. The default value of 3 means that for a `start_date` of 2024, buoys deployed as far back as 2021 are retained.

- **`export_flags`**: Controls which QC flag values are written to the output files. The flag meanings are described in Section 5.5.3. The default `[-9, 0, 1, 2]` exports everything. To exclude invalid measurements, remove `2`. To produce a conservative dataset of only the best data, use `[0]`. Measurements that are filtered out are replaced with the fill value (`-99.9`); an observation record is omitted entirely only if both the skin temperature and air temperature are filtered.

- **`awi_urls`**: The download URLs for the Arctic and Antarctic bulk zip archives. These should only need to change if Meereisportal reorganises its file layout.

### 5.4.2 The `buoy_types` Section

Each buoy type has its own entry under `buoy_types`. The key fields within each type are:

- **`match_pattern`**: The substring in the buoy ID (or filename for NetCDF) that identifies this buoy type. For example, `"I"` matches IDs like `2024I15`.
- **`station_type`**: The 5-character station type code written to the output files.
- **`files`**: Glob patterns for the primary data file and (for thermistor buoys) the auxiliary metadata file.
- **`columns`**: Maps raw CSV column names to the standardised internal names (`lat`, `lon`, `air_temp`, `pressure`, etc.).
- **`algorithm`**: Specifies whether interface detection is run (`leading_edge` for SIMB3/SIMBA, `none` for all others) and its parameters.
- **`qc`**: Enables or disables automated QC and contains the thresholds used by the QC routines. These thresholds can be tuned here without touching the source code. See Chapter 4 for the meaning of each parameter.

---

## 5.5 Output Format

### 5.5.1 File Organisation

Output is written as fixed-width whitespace-delimited ASCII files organised into per-year subdirectories under the output root. The filename format is `BUOYS_YYYYMMDDHHOO.txt`, where the timestamp identifies the observation hour. All buoy observations from that hour are appended to the same file, regardless of buoy type or location.

```
data/validation_output/ist_txt/
├── 2024/
│   ├── BUOYS_202401010000.txt
│   ├── BUOYS_202401010100.txt
│   └── ...
└── 2025/
    ├── BUOYS_202501010000.txt
    └── ...
```

The output directory is wiped and recreated at the start of each run, so the output always represents a complete and consistent dataset for the configured time window.

### 5.5.2 Record Format

Each line in an output file is one observation from one buoy at one time. The 18 whitespace-delimited fields are:

| # | Field | Format | Units | Notes |
|---|---|---|---|---|
| 1 | `ID` | 8-char string | — | Buoy identifier, right-padded with spaces. See ID shortening note below. |
| 2 | `TYPE` | 5-char string | — | Station type code. See type codes below. |
| 3 | `LAT` | `%8.4f` | degrees N | |
| 4 | `LON` | `%9.4f` | degrees E | |
| 5 | `YYYY` | `%Y` | — | Year |
| 6 | `MM` | `%m` | — | Month |
| 7 | `DD` | `%d` | — | Day |
| 8 | `HH` | `%H` | — | Hour (UTC) |
| 9 | `MM` | `%M` | — | Minute (always 00 for hourly data) |
| 10 | `Ts` | `%6.2f` | K | Skin (surface) temperature. Fill value if not available or filtered. |
| 11 | `T2m` | `%6.2f` | K | Air temperature (≈2 m). Fill value if not available or filtered. |
| 12 | `Td` | `%6.2f` | K | Dew point temperature. Always fill value (not measured). |
| 13 | `Press` | `%6.2f` | hPa | Barometric pressure. Fill value if not available. |
| 14 | `FF` | `%2d` | m/s (integer) | Wind speed. Fill value if not available. |
| 15 | `DD` | `%3d` | degrees (integer) | Wind direction. Fill value if not available. |
| 16 | `Cloud` | `%5.2f` | — | Cloud fraction. Always fill value (not measured). |
| 17 | `Ts_Q` | `%3d` | — | QC flag for skin temperature. |
| 18 | `T2m_Q` | `%3d` | — | QC flag for air temperature. |

**Fill values** (from the `defaults` section of the config):

| Type | Value | Fields |
|---|---|---|
| Float | `-99.9` | Ts, T2m, Td, Press, Cloud |
| Integer | `-9` | FF, Ts_Q, T2m_Q |
| Integer | `-99` | DD |

**Station type codes:**

| Code | Instrument |
|---|---|
| `SIMB3` | SIMB3 thermistor string buoy |
| `SIMBA` | SIMBA thermistor string buoy |
| `SNOW ` | Snow buoy |
| `METEO` | Automatic Weather Station (AWS) |
| `OMB  ` | OpenMetBuoy |
| `CALIB` | CALIB buoy |
| `SVP  ` | SVP buoy |

**A concrete example** (two records from the same hour file, one SIMB3 with skin and air temperature, one SVP with air temperature only):

```
2024I15  SIMB3   82.3412   14.2310 2024 11 15 06 00 263.45 258.12 -99.90 1012.80  -9  -99 -99.90   0   0
2024P22  SVP     79.1205    8.4501 2024 11 15 06 00 -99.90 261.34 -99.90 1011.40  -9  -99 -99.90  -9  -9
```

In the second record, `Ts` is `-99.90` and `Ts_Q` is `-9` because SVP buoys have no skin temperature sensor; `T2m_Q` is `-9` because SVP air temperature readings pass hardware sanity checks but are not assessed for representativeness (see Section 4.3.1).

### 5.5.3 QC Flags

Each temperature field has an associated quality flag following the scheme defined in Chapter 4 (0 = Good, 1 = Suspect, 2 = Invalid, −9 = no QC or measurement not available). METEO buoys receive the same automated QC as snow buoys via `SnowQualityControl` (Flag 0 or 2 only; see Section 4.5). SvalMIZ OMB records are assigned the static flag configured in the YAML.

A record is omitted from the output entirely (no line written) only when *both* `Ts` and `T2m` would be filled. If only one temperature is available or passes the export filter, the line is still written with a fill value for the missing field.

### 5.5.4 Buoy ID Shortening

The output format reserves 8 characters for the buoy ID. Standard AWI IDs (e.g. `2024I15`, `2023T82`) fit within this limit as-is. SvalMIZ OMB IDs are longer (e.g. `2025_04_KVS_SvalMIZ_01`) and are shortened automatically using the following rule: the two-digit year and the trailing index number are extracted and combined into a compact form such as `25OMB_01`. This ensures uniqueness within the 8-character constraint while remaining human-readable.

---

## 5.6 Visualization and Diagnostic Scripts

The `visualization/` directory contains a collection of scripts for inspecting pipeline output and comparing results against external references. These were primarily developed as internal diagnostic tools and are not part of the main processing chain. These scripts have varying levels of quality and bugs.


| Script | Purpose |
|---|---|
| `viewer.py` | Scrollable per-buoy QC browser (map + temperature time series) |
| `group_viewer.py` | Groups co-located buoys and displays them together |
| `deployment.py` | Gantt-style data availability timeline |
| `inspect_modular.py` | Low-level SIMB3/SIMBA thermistor string inspector (reads raw data) |
| `compare_awi.py` | Compares automated interface detection against AWI manual classification |
| `validate_simba.py` | Formal validation report generator (figures, tables, PDF) |
| `buoys_stats.py` | Dataset statistics and polar track plots |

All scripts locate the data directory and project configuration automatically based on their position in the repository. Settings such as the target buoy ID or date range can be adjusted in the `--- CONFIGURATION ---` block near the top of each file.
