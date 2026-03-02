#!/usr/bin/env python3
"""
IST Buoy Validation Data Generator
----------------------------------
Orchestrates the download, processing, quality control, and export of 
Arctic/Antarctic buoy data into SvalMIZ-compliant ASCII files for 
satellite validation.
"""

import os
import argparse
import logging
import shutil
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import copy

# --- CUSTOM LIBRARY IMPORTS ---
try:
    from lib.config_manager import BuoyConfig
    from lib import data_loader
    from lib import netcdf_loader
    from lib import simba_algo
    from lib import simba_qc
    from lib import svp_qc
    from lib import snow_qc
    from lib import ingest_awi_buoys 
except ImportError as e:
    sys.exit(f"Critical Error: Could not import required libraries. {e}")

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class BuoyProcessor:
    def __init__(self, config_path, input_dir, output_dir, args):
        self.config_path = config_path
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        
        # Load Config
        try:
            self.cfg_mgr = BuoyConfig(self.config_path)
            self.defaults = self.cfg_mgr.cfg.get('defaults', {})
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            sys.exit(1)

        self.output_prefix = self.defaults.get('output_prefix', 'BUOYS_')

        # --- Resolve Dates ---
        # CLI overrides Config overrides None
        start_str = args.start if args.start else self.defaults.get('start_date')
        end_str = args.end if args.end else self.defaults.get('end_date')
        
        self.start_date = pd.to_datetime(start_str) if start_str else pd.NaT
        self.end_date = pd.to_datetime(end_str) if end_str else pd.NaT

        # --- Resolve Download Logic ---
        config_always_download = self.defaults.get('always_download', True)
        # If the user explicitly passes --skip-download, do not download
        if args.skip_download:
            self.do_download = False
        else:
            self.do_download = config_always_download

    def run_ingest(self):
        """Executes the AWI download script if requested."""
        if not self.do_download:
            logger.info("Skipping data download step. Using existing data in raw directory.")
            return

        logger.info(f"Starting data ingestion into {self.input_dir}...")
        
        # Determine minimum year to save disk space during extraction
        # Use config year_buffer (default 3 years) to keep buoys that might still be alive
        year_buffer = self.defaults.get('year_buffer', 3)
        min_year = (self.start_date.year - year_buffer) if pd.notna(self.start_date) else None
        
        if min_year:
            logger.info(f"Target start year is {self.start_date.year}. Extracting buoys deployed from {min_year} onwards...")

        try:
            ingest_awi_buoys.run_ingest(
                destination_dir=self.input_dir,
                min_year=min_year,
                clear_existing=True,
                urls=self.defaults.get('awi_urls')
            )
        except Exception as e:
            logger.error(f"Data ingestion failed: {e}")

    def clean_output(self):
        """Recreates the output directory to ensure a clean state."""
        if self.output_dir.exists():
            logger.info(f"Cleaning output directory: {self.output_dir}")
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def filter_by_date(self, df):
        """Filters a dataframe by the globally defined start and end dates."""
        mask = np.ones(len(df), dtype=bool)
        if pd.notna(self.start_date):
            mask &= (df.index >= self.start_date)
        if pd.notna(self.end_date):
            mask &= (df.index <= self.end_date)
        return df.loc[mask]

    def shorten_id(self, original_id):
        """
        Smartly shortens long buoy IDs to fit into 8 characters while maintaining uniqueness.
        Specific logic for SvalMIZ/OMB IDs.
        """
        # Strategy 1: SvalMIZ specific (e.g. 2025_04_KVS_SvalMIZ_01 -> 25OMB_01)
        if "SvalMIZ" in original_id or "KVS" in original_id:
            parts = original_id.replace('-', '_').split('_')
            # Look for the year (starts with 20) and the index (digits at end)
            year_part = next((p for p in parts if p.startswith('20') and len(p)==4), None)
            index_part = parts[-1] if parts[-1].isdigit() else None
            
            if year_part and index_part:
                # Format: YYOMB_XX (e.g., 25OMB_01) -> 8 chars
                short_id = f"{year_part[-2:]}OMB_{index_part[-2:]}"
                return short_id

        # Strategy 2: Standard cleaning
        clean = original_id.replace("_", "").replace("-", "")
        
        # If it fits, return it
        if len(clean) <= 8:
            return clean
            
        # Strategy 3: Preserve the END of the string (usually where the unique ID is)
        # e.g. "Buoy_Long_Name_12345" -> "ame12345"
        return clean[-8:]

    def format_line(self, stid, timestamp, lat, lon, skin_temp_c, air_temp_c, 
                    ts_qual, tair_qual, press=np.nan, ff=np.nan, dd=np.nan, st_type="SIMBA"):
        """Formats an observation record into the SvalMIZ ASCII standard."""
        if pd.isna(lat) or pd.isna(lon): return None
        if abs(lat) < 1e-4 and abs(lon) < 1e-4: return None 
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180): return None
        # We need at least one valid temp
        if pd.isna(skin_temp_c) and pd.isna(air_temp_c): return None

        undef_float = self.defaults.get('undef_float', -99.9)
        undef_int = self.defaults.get('undef_int', -9)
        undef_dd = self.defaults.get('undef_dd', -99) 

        Ts_K = skin_temp_c + 273.15 if not pd.isna(skin_temp_c) else undef_float
        Ts_Q = int(ts_qual)   # Caller is responsible for passing -9 when there is no measurement

        T2m_K = air_temp_c + 273.15 if not pd.isna(air_temp_c) else undef_float
        T2m_Q = int(tair_qual)  # Caller is responsible for passing -9 when there is no measurement

        Press = float(press) if not pd.isna(press) else undef_float
        FF = int(round(ff)) if not pd.isna(ff) else undef_int
        DD = int(round(dd)) if not pd.isna(dd) else undef_dd
        Cloud = undef_float

        # Ensure ID fits in 8 chars
        safe_id = self.shorten_id(str(stid))
        
        # Ensure Type fits in 5 chars
        safe_type = f"{str(st_type):<5}"[:5]

        str_pos = f"{safe_id:8s} {safe_type:5s} {float(lat):8.4f} {float(lon):9.4f}"
        str_time = timestamp.strftime(" %Y %m %d %H %M")
        str_obs = f" {Ts_K:6.2f} {T2m_K:6.2f} {undef_float:6.2f} {Press:6.2f} {FF:2d} {DD:3d} {Cloud:5.2f} {Ts_Q:3d} {T2m_Q:3d}"

        return str_pos + str_time + str_obs + '\n'

    def write_line(self, timestamp, line_str):
        """Appends formatted line to the appropriate year-specific file."""
        year_str = timestamp.strftime("%Y")
        out_year_dir = self.output_dir / year_str
        out_year_dir.mkdir(exist_ok=True)
        
        filename = f"{self.output_prefix}{timestamp.strftime('%Y%m%d%H00')}.txt"
        filepath = out_year_dir / filename
        
        with open(filepath, 'a') as f:
            f.write(line_str)

    def process_standard_buoy(self, buoy_id):
        """Primary handler for standard CSV buoy data."""
        logger.info(f"Processing Buoy ID: {buoy_id}")
        
        try:
            base_conf = self.cfg_mgr.get_config_for_id(buoy_id)
            
            conf = copy.deepcopy(base_conf)
            conf['files']['primary'] = f"{buoy_id}_{base_conf['files']['primary']}"
            if 'aux' in conf['files']:
                conf['files']['aux'] = f"{buoy_id}_{base_conf['files']['aux']}"

            df_meta, df_string = data_loader.load_buoy_data(str(self.input_dir), conf)
            
            # --- DATE FILTERING ---
            df_meta = self.filter_by_date(df_meta)
            if df_meta.empty:
                logger.info("  -> Exported 0 records (No data in requested date range).")
                return
            
            s_interface = None
            algo_conf = conf['algorithm']
            qc_conf = conf.get('qc', {})
            station_type = conf.get('station_type', '').strip()

            # Both flag series start at -9 (no QC run / no measurement).
            # Automated QC routines overwrite them with 0/1/2 where applicable.
            # For buoys without automated QC, the config's quality_flag acts as a
            # manual quality assessment (e.g. quality_flag: 0 = "I trust this sensor").
            ts_flags  = pd.Series(-9, index=df_meta.index)
            t2m_flags = pd.Series(-9, index=df_meta.index)
            manual_t2m_flag = conf.get('air_temp_config', {}).get('quality_flag', -9)

            # 1. Processing for Thermistor String Buoys
            if algo_conf['method'] == 'leading_edge' and df_string is not None:
                detector = simba_algo.SimbaInterfaceDetector(df_string)
                s_interface = detector.detect_leading_edge(edge_ratio=algo_conf['params']['edge_ratio'])

                if qc_conf.get('enabled', False) and s_interface is not None:
                    s_interface = s_interface.reindex(df_meta.index)
                    qc = simba_qc.SimbaQC(df_string.loc[df_meta.index], s_interface, qc_conf.get('params'))
                    df_qc_result = qc.compute_flags()
                    ts_flags = df_qc_result['quality_flag']  # 0, 1, or 2

                # Air temp comes from the AUX sensor; no automated QC is run on it.
                # Apply the config's manual quality assessment.
                t2m_flags[:] = manual_t2m_flag

            # 2. Processing for Non-String Buoys (no skin temp; only T2m QC)
            elif algo_conf['method'] == 'none':
                if station_type in ['SVP', 'CALIB'] and qc_conf.get('enabled', False):
                    qc_params = qc_conf.get('params', {})
                    qc = svp_qc.SVPQualityControl(df_meta, temp_col='air_temp', qc_params=qc_params)
                    df_qc_result = qc.compute_flags()
                    t2m_flags = df_qc_result['quality_flag']  # 0, 1, or 2
                elif station_type in ['SNOW', 'METEO'] and qc_conf.get('enabled', False):
                    qc_params = qc_conf.get('params', {})
                    qc = snow_qc.SnowQualityControl(df_meta, temp_col='air_temp', qc_params=qc_params)
                    df_qc_result = qc.compute_flags()
                    t2m_flags = df_qc_result['quality_flag']  # 0 or 2
                else:
                    # No automated QC — apply the config's manual quality assessment.
                    t2m_flags[:] = manual_t2m_flag

            # Export filter: measurements with flags outside this set are replaced with filler.
            # A line is omitted entirely only when both Ts and T2m are filtered out.
            export_flags = set(self.defaults.get('export_flags', [-9, 0, 1, 2]))

            count = 0
            for row in df_meta.itertuples():
                ts = row.Index
                ts_flag  = int(ts_flags.loc[ts])
                t2m_flag = int(t2m_flags.loc[ts])

                # --- Skin temperature ---
                skin_temp = np.nan
                if s_interface is not None:
                    idx = s_interface.get(ts, np.nan)
                    if not pd.isna(idx):
                        try:
                            skin_temp = df_string.iloc[df_string.index.get_loc(ts), int(idx) - 1]
                        except Exception:
                            pass

                air_temp = getattr(row, 'air_temp', np.nan)

                # Apply export filter. A NaN measurement naturally becomes filler
                # regardless of the flag.
                ts_export  = skin_temp if (ts_flag  in export_flags and not pd.isna(skin_temp))  else np.nan
                t2m_export = air_temp  if (t2m_flag in export_flags and not pd.isna(air_temp))   else np.nan

                # Skip the line entirely if there is no exportable temperature data at all.
                if pd.isna(ts_export) and pd.isna(t2m_export):
                    continue

                line = self.format_line(
                    buoy_id, ts, getattr(row, 'lat', np.nan), getattr(row, 'lon', np.nan),
                    ts_export, t2m_export,
                    ts_flag, t2m_flag,
                    getattr(row, 'pressure', np.nan), getattr(row, 'wind_speed', np.nan), getattr(row, 'wind_dir', np.nan),
                    conf['station_type']
                )

                if line:
                    self.write_line(ts, line)
                    count += 1
            
            logger.info(f"  -> Exported {count} records.")

        except Exception as e:
            if "No file matching" not in str(e):
                 logger.error(f"Failed to process {buoy_id}: {e}")

    def process_netcdf_file(self, filepath):
        """Handler for multi-trajectory NetCDF files."""
        filename = filepath.name
        logger.info(f"Processing NetCDF: {filename}")
        
        try:
            conf = self.cfg_mgr.get_config_for_id(filename)
        except ValueError:
            logger.warning(f"No config match for {filename}. Skipping.")
            return

        buoy_dict = netcdf_loader.load_multibuoy_netcdf(str(filepath), conf)

        # Use the config's quality_flag as the manual quality assessment for all
        # measurements in this file (QC is disabled for NetCDF sources).
        netcdf_flag = conf.get('air_temp_config', {}).get('quality_flag', -9)
        export_flags = set(self.defaults.get('export_flags', [-9, 0, 1, 2]))

        total_lines = 0
        for raw_bid, df in buoy_dict.items():

            # --- DATE FILTERING ---
            df = self.filter_by_date(df)
            if df.empty:
                continue

            for row in df.itertuples():
                ts = row.Index
                ts_celsius   = getattr(row, 'ts_celsius',   np.nan)
                tair_celsius = getattr(row, 'tair_celsius', np.nan)

                # -9 when no measurement, otherwise the config's manual flag.
                ts_flag   = netcdf_flag if not pd.isna(ts_celsius)   else -9
                tair_flag = netcdf_flag if not pd.isna(tair_celsius) else -9

                ts_export   = ts_celsius   if (ts_flag   in export_flags and not pd.isna(ts_celsius))   else np.nan
                tair_export = tair_celsius if (tair_flag in export_flags and not pd.isna(tair_celsius)) else np.nan

                if pd.isna(ts_export) and pd.isna(tair_export):
                    continue

                line = self.format_line(
                    raw_bid, ts, getattr(row, 'lat', np.nan), getattr(row, 'lon', np.nan),
                    ts_export, tair_export,
                    ts_flag, tair_flag,
                    np.nan, np.nan, np.nan,
                    conf['station_type']
                )

                if line:
                    self.write_line(ts, line)
                    total_lines += 1
        
        logger.info(f"  -> Exported {total_lines} lines from NetCDF.")

    def run(self):
        self.clean_output()
        self.run_ingest()

        logger.info("Scanning for unique buoy IDs...")
        all_csvs = list(self.input_dir.glob("*.csv"))
        
        unique_ids = set()
        for f in all_csvs:
            if "_" in f.name:
                unique_ids.add(f.name.split('_')[0])
        
        if unique_ids:
            logger.info(f"Found {len(unique_ids)} unique buoys.")
            for bid in sorted(list(unique_ids)):
                self.process_standard_buoy(bid)
        else:
            logger.warning("No CSV buoys found.")

        nc_files = list(self.input_dir.rglob("*hourly_MIP.nc"))
        if nc_files:
            logger.info(f"Found {len(nc_files)} NetCDF files.")
            for f in nc_files:
                self.process_netcdf_file(f)
        else:
            logger.info("No matching NetCDF files found.")

        logger.info("Processing Complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IST Validation Data Processor")
    parser.add_argument("--config", default="buoy_config.yaml", help="Path to YAML config file")
    parser.add_argument("--input", default=os.environ.get("BUOY_DATA_DIR", "./data/raw/"), 
                        help="Root directory containing buoy data")
    parser.add_argument("--output", default="./data/validation_output/ist_txt/", help="Output directory")
    
    parser.add_argument("--start", type=str, help="Start date filter (YYYY-MM-DD). Overrides config.")
    parser.add_argument("--end", type=str, help="End date filter (YYYY-MM-DD). Overrides config.")
    parser.add_argument("--skip-download", action="store_true", help="Skip AWI download and use existing raw data.")
    
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    processor = BuoyProcessor(
        config_path=args.config,
        input_dir=args.input,
        output_dir=args.output,
        args=args
    )
    
    processor.run()