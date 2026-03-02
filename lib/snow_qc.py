import numpy as np
import pandas as pd

class SnowQualityControl:
    """
    Simplified Quality Control for Snow Buoys (Air Temperature).
    Flags:
        0: Good (Valid temperature reading)
        2: Bad (Unphysical values or extreme spikes)
    """
    
    def __init__(self, df, temp_col='air_temp', qc_params=None):
        self.df = df.copy()
        if not isinstance(self.df.index, pd.DatetimeIndex):
            self.df.index = pd.to_datetime(self.df.index)
        self.df = self.df.sort_index()
        
        self.tc = temp_col
        self.params = qc_params if qc_params is not None else {}

    def compute_flags(self):
        flags = pd.Series(0, index=self.df.index, dtype=int)
        t = self.df[self.tc]
        
        # If the column is completely empty, return all Bad
        if t.isna().all():
            flags[:] = 2
            return pd.DataFrame({'quality_flag': flags})

        # --- 1. Calculate Hourly Rate of Change ---
        # Time difference in hours between consecutive rows
        dt_hours = self.df.index.to_series().diff().dt.total_seconds() / 3600.0
        roc = t.diff() / dt_hours

        # --- 2. Load Configurable Parameters ---
        p_min_t = self.params.get('min_temp_limit', -70.0)
        p_max_t = self.params.get('max_temp_limit', 25.0)
        p_max_jump = self.params.get('max_hourly_jump', 10.0)

        # --- 3. Evaluate FLAG 2 (BAD / INVALID) ---
        bad_mask = (
            (t < p_min_t) |               # Too cold
            (t > p_max_t) |               # Too hot
            (roc.abs() > p_max_jump)      # Impossible spike
        )
        flags.loc[bad_mask] = 2

        # Everything else remains 0 (Good)
        return pd.DataFrame({
            'quality_flag': flags
        })