import xarray as xr
import pandas as pd
import numpy as np

def load_multibuoy_netcdf(filepath, config):
    """
    Loads a SvalMIZ style NetCDF containing multiple trajectories.
    Returns a Dictionary: { 'BuoyID': DataFrame, ... }
    """
    try:
        ds = xr.open_dataset(filepath)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return {}

    # Map internal column names to NetCDF variable names
    col_map = config['columns']
    var_id = col_map.get('id', 'trajectory_id')
    var_lat = col_map.get('lat', 'latitude')
    var_lon = col_map.get('lon', 'longitude')
    var_ts = col_map.get('ts', 'surface_temperature')
    var_tair = col_map.get('tair', 'air_temperature')

    # Dictionary to store results
    buoy_data = {}

    # The file has a 'trajectory' dimension
    if 'trajectory' not in ds.sizes:
        print(f"Error: 'trajectory' dimension not found in {filepath}")
        return {}
        
    n_trajs = ds.sizes['trajectory']

    for i in range(n_trajs):
        # Extract one trajectory
        subset = ds.isel(trajectory=i)
        
        # --- ROBUST ID EXTRACTION ---
        raw_id = subset[var_id].values
        
        # Check dimensions: 0-d array means it's already a scalar (string/bytes)
        if np.ndim(raw_id) == 0:
            # Extract the scalar value
            val = raw_id.item()
            if isinstance(val, bytes):
                bid = val.decode('utf-8').strip()
            else:
                bid = str(val).strip()
        else:
            # It's an array (likely characters). Iterate and join.
            # Handle mixed types (bytes vs str) inside array
            chars = []
            for c in raw_id:
                if isinstance(c, bytes):
                    chars.append(c.decode('utf-8'))
                elif isinstance(c, str):
                    chars.append(c)
                else:
                    chars.append(str(c))
            bid = "".join(chars).strip()

        # Convert to DataFrame
        # We drop the 'trajectory' dim to flatten it to time series
        try:
            df = subset[[var_lat, var_lon, var_ts, var_tair]].to_dataframe()
        except KeyError as e:
            print(f"  [Warning] Missing variable in NetCDF for {bid}: {e}")
            continue
            
        # Clean up DataFrame
        df = df.reset_index().set_index('time').sort_index()
        
        # Rename to standard columns for the export script
        df = df.rename(columns={
            var_lat: 'lat',
            var_lon: 'lon',
            var_ts: 'ts_kelvin',       # MIP data is in Kelvin
            var_tair: 'tair_kelvin'    # MIP data is in Kelvin
        })

        # --- UNIT CONVERSION (Kelvin -> Celsius) ---
        # The rest of your pipeline expects Celsius inputs
        # Note: xarray might preserve attributes, but calculations return standard Series
        df['ts_celsius'] = df['ts_kelvin'] - 273.15
        df['tair_celsius'] = df['tair_kelvin'] - 273.15

        # Store in dict
        buoy_data[bid] = df

    ds.close()
    return buoy_data