import numpy as np
import pandas as pd

class SimbaQC:
    def __init__(self, df_temp, interface_series, qc_params=None):
        """
        Quality Control manager for SIMBA buoy data. Performs physical sanity
        checks and signal strength analysis on detected interfaces.

        Args:
            df_temp: DataFrame of raw temperatures (Index=Time, Cols=T1, T2...).
            interface_series: Series containing the sensor index of the
                              detected air-snow interface.
            qc_params: Optional dict of QC thresholds from buoy_config.yaml.
                       Falls back to hard-coded defaults if not provided.
        """
        self.df = df_temp
        self.t_vals = df_temp.values
        self.interface = interface_series
        self.timestamps = df_temp.index

        # QC Parameters — read from config, fall back to physics-based defaults
        p = qc_params or {}
        self.THRESHOLD_GRAD  = p.get('threshold_grad',   0.4375)  # Liao et al. (2019)
        self.MAX_JUMP        = p.get('max_jump',         1.0)      # Max interface movement per hour (sensors/hr, ~2 cm/hr at 2 cm spacing)
        self.UPPER_TEMP_LIMIT = p.get('upper_temp_limit', 0.0)    # Max realistic surface temp (C)
        self.ABS_MAX_TEMP    = p.get('abs_max_temp',     30.0)    # Hardware error threshold (Max)
        self.ABS_MIN_TEMP    = p.get('abs_min_temp',     -65.0)   # Hardware error threshold (Min)
        self.OCEAN_MAX_TEMP  = p.get('ocean_max_temp',   -1.0)    # Antarctic ocean < -1.0C

    def compute_flags(self):
        """
        Generates Quality Flags based on physical evidence and signal strength.
          0 = Valid and representative of what we are trying to measure.
          1 = Valid but non-representative (e.g. isothermal column, melting surface).
          2 = Invalid (hardware error, algo failure, physically impossible value).
        """
        n_steps, n_sensors = self.t_vals.shape
        grads = np.abs(np.diff(self.t_vals, axis=1))
        grads[:, :5] = 0 # Mask top exclusion zone

        # --- Physical Sanity Metrics ---

        # 1. Profile Insanity Check
        # Detects severe hardware malfunctions (e.g., short circuits) reporting impossible values.
        profile_is_insane = np.any((self.t_vals > self.ABS_MAX_TEMP) |
                                   (self.t_vals < self.ABS_MIN_TEMP), axis=1)

        # 2. Ocean Sanity Check
        # The bottom of the string is submerged in Antarctic seawater (~ -1.8C).
        # If the average of the bottom 10 sensors is warmer than -1.0C, the
        # hardware is likely returning digital fill values (0.0C).
        avg_bottom_temp = np.mean(self.t_vals[:, -10:], axis=1)
        ocean_is_too_warm = avg_bottom_temp > self.OCEAN_MAX_TEMP

        # 3. Detection Specific Metrics
        peak_strengths = np.zeros(n_steps)
        surface_temps = np.zeros(n_steps)
        dt_hours = self.timestamps.to_series().diff().dt.total_seconds() / 3600.0
        dt_hours.iloc[0] = 1.0  # No prior step; prepend sets first diff to 0, so result is 0/1 = 0
        volatility = np.abs(np.diff(self.interface.fillna(0).values, prepend=self.interface.iloc[0])) / dt_hours.values
        if_idx = self.interface.fillna(0).astype(int).values

        for t in range(n_steps):
            edge_idx = if_idx[t]
            if edge_idx == 0: continue

            # Signal Strength: Find the peak associated with the leading edge detection
            search_start = max(0, edge_idx - 2)
            search_end = min(grads.shape[1], edge_idx + 10)
            peak_strengths[t] = np.max(grads[t, search_start:search_end])

            # Temperature at the specific interface point
            temp_lookup = np.clip(edge_idx - 1, 0, n_sensors - 1)
            surface_temps[t] = self.t_vals[t, temp_lookup]

        # --- Flag Assignment Logic (highest severity wins) ---
        quality_flags = np.zeros(n_steps, dtype=int)

        # FLAG 2: INVALID
        # Algo failed, profile has impossible values, ocean is too warm (fill value),
        # or detected surface is above 0°C (physically impossible for sea ice).
        mask_bad = (self.interface.isna() |
                    profile_is_insane |
                    ocean_is_too_warm |
                    (surface_temps > self.UPPER_TEMP_LIMIT))
        quality_flags[mask_bad] = 2

        # FLAG 1: NON-REPRESENTATIVE
        # Isothermal column: valid temperature reading but interface is ambiguous
        # (algorithm relies on persistence rather than a real gradient signal).
        mask_isothermal = (peak_strengths < self.THRESHOLD_GRAD) & (quality_flags < 2)
        quality_flags[mask_isothermal] = 1

        # FLAG 1: NON-REPRESENTATIVE (consistency warning)
        # Interface moved faster than MAX_JUMP sensors/hr (~2 cm/hr at 2 cm spacing, unstable detection)
        # or surface is near 0°C (melting).
        mask_jump = (volatility > self.MAX_JUMP) & (quality_flags < 2)
        mask_warm = (surface_temps > 0.0) & (quality_flags < 2)
        quality_flags[mask_jump | mask_warm] = 1

        # Combine into result DataFrame
        return pd.DataFrame({
            'peak_strength': peak_strengths,
            'surface_temp': surface_temps,
            'avg_ocean_temp': avg_bottom_temp,
            'quality_flag': quality_flags,
            'total_conf': np.select(
                [quality_flags == 0, quality_flags == 1, quality_flags == 2],
                [100, 50, 0],
                default=0
            )
        }, index=self.timestamps)