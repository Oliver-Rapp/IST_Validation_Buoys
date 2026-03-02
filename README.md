# OSI SAF IST Validation Dataset

Processes Arctic and Antarctic drifting buoy data into fixed-width ASCII files for validation of the OSI SAF sea ice surface temperature (IST) satellite product.

**Input:** AWI Meereisportal CSV archives (downloaded automatically) and SvalMIZ NetCDF files (provided separately).
**Output:** Fixed width format ASCII files, one per observation hour, containing skin temperature, air temperature, position, and QC flags for each buoy.

For full documentation see the [`docs/`](docs/) directory.

---

## Quick Start

```bash
# 1. Enter the environment
nix-shell          # Nix users
# or
pip install -r requirements.txt

# 2. Place the SvalMIZ NetCDF file in data/raw/ (if available)

# 3. Run the pipeline
python ist_buoy_validation_data.py
```

The pipeline will download the AWI buoy archives, process all buoy types, and write output to `data/validation_output/ist_txt/`.

To re-run without re-downloading (e.g. after changing QC settings):

```bash
python ist_buoy_validation_data.py --skip-download
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `numpy`, `pandas` | Core data handling |
| `scipy` | Interface-detection algorithm |
| `matplotlib` | Visualizations |
| `cartopy`, `shapely` | Map projections (optional, only needed by visualization scripts) |
| `xarray`, `netcdf4` | Reading SvalMIZ NetCDF files |
| `pyyaml` | Configuration file parsing |
| `requests`, `tqdm` | Downloading AWI data |

A `requirements.txt` and a `shell.nix` are provided.

---

## Configuration

All settings — date range, QC thresholds, buoy type definitions, download URLs — are in `buoy_config.yaml`. Key CLI flags:

| Flag | Description |
|---|---|
| `--skip-download` | Skip AWI download, process existing files |
| `--start YYYY-MM-DD` | Override start date |
| `--end YYYY-MM-DD` | Override end date |
| `--config PATH` | Use a different config file |

See [`docs/chapter_05_using_the_pipeline.md`](docs/chapter_05_using_the_pipeline.md) for the full CLI reference and config file documentation.

---

## Documentation

| Chapter | Contents |
|---|---|
| [`01 — Introduction`](docs/chapter_01_introduction.md) | Project purpose and measurement objectives |
| [`02 — Data Sources`](docs/chapter_02_data_sources.md) | Instrument types, sensor specs, file formats |
| [`03 — Thermistor String Buoys`](docs/chapter_03_thermistor_string_buoys.md) | Interface detection algorithms |
| [`04 — Quality Control`](docs/chapter_04_quality_control.md) | QC checks, flag definitions, known limitations |
| [`05 — Using the Pipeline`](docs/chapter_05_using_the_pipeline.md) | Setup, configuration, output format |
