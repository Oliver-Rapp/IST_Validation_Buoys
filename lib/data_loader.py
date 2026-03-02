import pandas as pd
import numpy as np
import os
import glob
from pathlib import Path

def load_buoy_data(data_dir, config):
    """
    Generic loader driven by the configuration dictionary.
    
    Returns:
        df_meta (pd.DataFrame): Standardized columns dynamically mapped from config.
        df_string (pd.DataFrame OR None): Thermistor string data.
    """
    data_path = Path(data_dir)
    
    # 1. Identify Files
    primary_pattern = config['files']['primary']
    primary_files = list(data_path.glob(primary_pattern))
    
    if not primary_files:
        raise FileNotFoundError(f"No file matching {primary_pattern} in {data_dir}")
    
    df_primary = pd.read_csv(primary_files[0], parse_dates=['time']).set_index('time').sort_index()
    
    # Load Aux (if defined)
    df_aux = None
    if 'aux' in config['files']:
        aux_pattern = config['files']['aux']
        aux_files = list(data_path.glob(aux_pattern))
        if aux_files:
            df_aux = pd.read_csv(aux_files[0], parse_dates=['time']).set_index('time').sort_index()
            df_aux = df_aux.reindex(df_primary.index, method='nearest', limit=1)

    # 2. Extract Standard Metadata Dynamically
    df_meta = pd.DataFrame(index=df_primary.index)
    col_map = config.get('columns', {})
    
    def get_col(name):
        """Get column from aux or primary, supporting fallback alternatives.

        Args:
            name: Column name (str) or list of column names to try in order.

        Returns:
            Series or np.nan if not found.
        """
        if not name:
            return np.nan
        # Support list of alternative column names (try in order)
        candidates = name if isinstance(name, list) else [name]
        for col_name in candidates:
            if df_aux is not None and col_name in df_aux.columns:
                return df_aux[col_name]
            if col_name in df_primary.columns:
                return df_primary[col_name]
        return np.nan

    # Dynamically map all columns defined in the YAML
    for std_name, raw_name in col_map.items():
        df_meta[std_name] = get_col(raw_name)

    # 3. Extract Thermistor String (if applicable)
    df_string = None
    if config.get('algorithm', {}).get('method') != "none":
        # Filter columns starting with 'T' followed by digits
        t_cols = [c for c in df_primary.columns if c.startswith('T') and len(c) > 1 and c[1].isdigit()]
        
        try:
            t_cols.sort(key=lambda x: int(''.join(filter(str.isdigit, x.split('(')[0]))))
            df_string = df_primary[t_cols]
        except Exception as e:
            print(f"Warning: Could not sort thermistor columns. Check format. {e}")

    return df_meta, df_string