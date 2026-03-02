import numpy as np
import pandas as pd

class SVPQualityControl:
    """
    Minimal quality control for SVP and CALIB buoys.

    These buoy types carry a single hull/housing temperature sensor whose
    relationship to the near-surface air temperature is uncertain and varies
    with deployment conditions (solar exposure, snow burial, ocean immersion).
    Because the representativeness of each observation cannot be reliably
    assessed from the temperature signal alone, no representativeness (Flag 1)
    checks are applied.

    Flag assignment:
        -9: No QC performed — measurement exists but representativeness is
            not assessed. This is the default for all observations that pass
            the hardware checks below.
         2: Invalid — the value is outside the physically plausible range for
            near-surface polar air temperatures, or an impossible spike was
            detected indicating a transmission or hardware error.

    Flag 1 (Suspect) is intentionally not used for these buoy types.
    """

    def __init__(self, df, temp_col='air_temp', qc_params=None):
        self.df = df.copy()
        if not isinstance(self.df.index, pd.DatetimeIndex):
            self.df.index = pd.to_datetime(self.df.index)
        self.df = self.df.sort_index()

        self.tc = temp_col
        self.params = qc_params if qc_params is not None else {}

    def compute_flags(self):
        # Default: -9 (measurement present, representativeness not assessed)
        flags = pd.Series(-9, index=self.df.index, dtype=int)
        t = self.df[self.tc]

        # If the temperature column is entirely missing, mark all as Invalid
        if t.isna().all():
            flags[:] = 2
            return pd.DataFrame({'quality_flag': flags})

        # --- Configurable thresholds ---
        p_min_t    = self.params.get('min_temp_limit',  -50.0)
        p_max_t    = self.params.get('max_temp_limit',   20.0)
        p_max_jump = self.params.get('max_hourly_jump',  10.0)

        # --- Hourly rate of change ---
        dt_hours = self.df.index.to_series().diff().dt.total_seconds() / 3600.0
        roc = t.diff() / dt_hours

        # --- Flag 2: unphysical range or impossible spike ---
        bad_mask = (
            (t < p_min_t) |             # Below plausible polar air temperature
            (t > p_max_t) |             # Above plausible polar air temperature
            (roc.abs() > p_max_jump)    # Transmission spike or hardware glitch
        )
        flags.loc[bad_mask] = 2

        return pd.DataFrame({'quality_flag': flags})
