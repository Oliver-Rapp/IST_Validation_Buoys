# 4. Quality Control

This chapter describes the automated quality control (QC) applied to each buoy type before the data are written to the output files. QC is handled by three separate modules in the `lib/` directory, each targeting a different measurement type and instrument category. The modules assign integer flags to each observation; these flags travel through to the output files and can be used by downstream consumers to filter the dataset.

The chapter describes what each check does and the physical reasoning behind it.

---

## 4.1 Overview

### 4.1.1 Flag Values

All QC in the pipeline uses a common three-value flag scheme:

| Flag | Meaning |
|---|---|
| `0` | **Good** — the measurement passes all checks and is considered representative of the quantity being measured. |
| `1` | **Suspect** — the measurement is likely physically valid, but there is evidence that it may not be representative. Common causes: the sensor is insulated from the atmosphere (buried under snow), the reading is affected by solar heating of the sensor housing, or the measurement is dominated by ocean temperature rather than air temperature. |
| `2` | **Invalid** — the measurement fails a hard threshold check and should not be used. Common causes: sensor values outside physically plausible limits, a completely dead sensor, or some other clearly unphysical values. |

In addition to these three values, a flag of `-9` is used to indicate *no QC was performed* or *no measurement exists for that field*. A buoy that has no skin temperature sensor (e.g. SVP, CALIB, snow buoys) will always have `Ts_Q = -9`. Equally, a buoy type for which QC is disabled in the YAML will carry the manually configured `quality_flag` value from its config entry, which is typically `0` (meaning "I trust this instrument").

### 4.1.2 Which QC Applies to Which Buoy Type

| Buoy type | Skin temp QC | Air temp QC | QC module |
|---|---|---|---|
| SIMB3, SIMBA (thermistor string) | Automated (`simba_qc`) | N/A (manual flag from config) | `lib/simba_qc.py` |
| SVP, CALIB | N/A  | Automated (`svp_qc`) | `lib/svp_qc.py` |
| Snow buoy | N/A | Automated (`snow_qc`) | `lib/snow_qc.py` |
| Weather buoy (METEO) | N/A | Automated (`snow_qc`) | `lib/snow_qc.py` |
| SvalMIZ OMB | None (manual flag = 0) | None (manual flag = 0) | — |

The key asymmetry for thermistor string buoys is that *only the skin temperature* receives automated QC. The air temperature, which comes from a dedicated near-surface sensor in the AUX or TS file (Section 3.4.2), is trusted at face value and assigned the manually configured `quality_flag` (default `0`).

### 4.1.3 The Export Filter

QC flags do not automatically exclude measurements from the output. A separate `export_flags` list in the `defaults` section of the YAML controls which flag values are written:

```yaml
export_flags: [-9, 0, 1, 2]   # Export everything (default)
```

Measurements whose flag is not in `export_flags` are replaced with the fill value (`-99.9` for temperatures). A record line is omitted entirely only when *both* the skin temperature and air temperature would be filled. This means that, for example, a SVP buoy with a good air temperature but no skin temperature sensor still produces an output line with fill for `Ts` and a real value for `T2m`.

---

## 4.2 Thermistor String Buoys (SIMBA and SIMB3)

**Source:** `lib/simba_qc.py`, class `SimbaQC`

**Called from:** `ist_buoy_validation_data.py`, method `process_standard_buoy`, when the algorithm method is `leading_edge` and `qc.enabled` is `true`.

This module evaluates the quality of the interface detection result produced by `SimbaInterfaceDetector` (Chapter 3). It does not re-run the algorithm; it interrogates the detection output and the raw temperature array for physical consistency.

### 4.2.1 Inputs

The `SimbaQC` class receives:
- `df_temp`: the full temperature array (time × sensor index), as a DataFrame.
- `interface_series`: the time series of detected interface sensor indices, as a Series. A value of `NaN` means the algorithm found no valid interface for that timestep.
- `qc_params`: the dictionary from `buoy_config.yaml` under `qc.params` (optional; all parameters have physics-based defaults).

### 4.2.2 Derived Quantities

Before flag assignment, three time-series diagnostics are computed across the full record:

1. **`peak_strength`**: For each timestep, the maximum absolute gradient value in a search window extending from two sensors above to ten sensors below the detected interface. This captures the steepest part of the snow gradient associated with the detection.

2. **`surface_temp`**: The temperature of the sensor immediately above the detected interface (index `e - 1`), which is the value exported as the skin temperature.

3. **`volatility`**: The absolute change in interface sensor index between consecutive timesteps, normalised by the elapsed time in hours (units: sensors/hr). SIMB3 observations are 4-hourly and SIMBA are 6-hourly; normalising by the actual timestep makes the threshold time-invariant and directly comparable between instruments.

### 4.2.3 Flag 2 — Invalid

A timestep receives Flag 2 if any of the following conditions are true:

| Condition | Physical interpretation | Config parameter |
|---|---|---|
| `interface.isna()` | The algorithm found no valid interface | — |
| Any sensor in the profile outside `[abs_min_temp, abs_max_temp]` | Hardware failure (short circuit, fill value 0.0 reported as valid) | `abs_min_temp` (−65°C), `abs_max_temp` (30°C) |
| Mean of bottom 10 sensors > `ocean_max_temp` | Bottom of string reading above expected (Ant)arctic seawater temperature. | `ocean_max_temp` (−1.0°C) |
| `surface_temp > upper_temp_limit` | Detected surface temperature above 0°C; physically impossible for sea ice. It is possible that this could indicate measurment of melt water on top of the ice. | `upper_temp_limit` (0.0°C) |

Flag 2 is assigned unconditionally: a timestep that receives Flag 2 cannot subsequently receive Flag 1.

### 4.2.4 Flag 1 — Suspect

After Flag 2 is assigned, the following checks are evaluated for the remaining timesteps:

| Condition | Physical interpretation | Config parameter |
|---|---|---|
| `peak_strength < threshold_grad` | The gradient signal is weaker than the minimum expected in the snowpack. This check captures forward-filled interface positions: whenever the algorithm cannot detect a strong gradient peak, it carries the previous position forward (Section 3.3.2), and this Flag 1 check fires immediately. The detection position may still be physically plausible, but its accuracy cannot be verified from the current gradient signal. | `threshold_grad` (0.4375°C) |
| `volatility > max_jump` | The interface moved faster than `max_jump` sensors/hr (~2 cm/hr at 2 cm spacing). Physical movement of the snow surface is assumed exceed this rate; faster apparent movement is more likely an algorithm instability than a real event. | `max_jump` (1 sensor/hr) |


### 4.2.5 Configurable Parameters

All thresholds are read from `buoy_config.yaml` under `buoy_types.simb3.qc.params` (or the equivalent `legacy_simba` entry):

```yaml
qc:
  enabled: true
  params:
    threshold_grad: 0.4375    # Min expected gradient at snow–air interface (°C)
    max_jump: 1.0             # Max interface movement per hour (sensors/hr, ~2 cm/hr at 2 cm spacing)
    upper_temp_limit: 0.0     # Max physically plausible surface temperature (°C)
    abs_max_temp: 30.0        # Hardware error upper limit (°C)
    abs_min_temp: -65.0       # Hardware error lower limit (°C)
    ocean_max_temp: -1.0      # Expected maximum bottom-of-string water temperature (°C)
```

---

## 4.3 SVP and CALIB Buoys

**Source:** `lib/svp_qc.py`, class `SVPQualityControl`

**Called from:** `ist_buoy_validation_data.py` when the algorithm method is `none` and the station type is `SVP` or `CALIB`.

Unlike thermistor string buoys, SVP and CALIB buoys carry no thermistor chain. Their contribution to the validation dataset is a single temperature measurement from a hull or housing sensor, stored in the `air_temp` field and exported as `T2m`. For both instrument types, the column used is `temperature_surface (degC)` from the AWI supplied file.

### 4.3.1 Rationale for Minimal QC

Because single-point hull temperatures cannot reliably distinguish between true air exposure, snow burial, solar heating, or ocean immersion, no representativeness checks are applied. Observations passing the hardware sanity checks below receive flag `−9` (measurement present, representativeness not assessed) rather than `0` (Good); see Section 4.1.1.

### 4.3.2 Inputs

The `SVPQualityControl` class receives:
- `df`: the full metadata DataFrame, including the `air_temp` column.
- `temp_col`: the name of the temperature column to evaluate (default `'air_temp'`).
- `qc_params`: the parameter dictionary from `buoy_config.yaml` under `qc.params`.

If the temperature column is entirely `NaN`, all records receive Flag 2 immediately.

### 4.3.3 Flag 2 — Invalid

Only hardware-level failures are flagged as Invalid:

| Condition | Physical interpretation | Config parameter |
|---|---|---|
| `t < min_temp_limit` or `t > max_temp_limit` | Value outside the physically plausible range for near-surface polar temperatures | `min_temp_limit` (−50°C), `max_temp_limit` (20°C) |
| `roc.abs() > max_hourly_jump` | Temperature changed by more than 10°C in one hour — a transmission spike or hardware glitch | `max_hourly_jump` (10°C/hr) |


### 4.3.4 Flag 1 — Not Used

Flag 1 (Suspect) is not assigned by this module. The failure modes that would motivate Flag 1 checks (burial, solar heating, ocean immersion) cannot be reliably identified from the temperature signal alone.

### 4.3.5 Configurable Parameters

```yaml
qc:
  enabled: true
  params:
    # Flag 2 — hardware validity only
    min_temp_limit: -50.0
    max_temp_limit: 20.0
    max_hourly_jump: 10.0
```

---

## 4.4 Snow Buoys

**Source:** `lib/snow_qc.py`, class `SnowQualityControl`

**Called from:** `ist_buoy_validation_data.py` when the algorithm method is `none` and the station type is `SNOW`.

The snow buoy QC is intentionally simplified. It assigns only Flag 0 (Good) or Flag 2 (Invalid) — there is no Flag 1 (Suspect).

### 4.4.1 Flag 2 — Invalid

| Condition | Config parameter |
|---|---|
| `t < min_temp_limit` | `min_temp_limit` (−70°C) |
| `t > max_temp_limit` | `max_temp_limit` (25°C) |
| Hourly rate of change > `max_hourly_jump` | `max_hourly_jump` (10°C/hr) |


All other observations are assigned Flag 0.

### 4.4.2 Note on Flag 1

No Flag 1 (Suspect) checks are implemented for snow buoys. Based on observed data quality from deployed snow buoys, burial of the air temperature sensor appears uncommon (snow buoys have a taller mast profile than SVP or CALIB sensors), and the records generally look clean. All observations that pass the Flag 2 checks are assigned Flag 0 (Good).

---

## 4.5 Weather Buoys (METEO)

**Source:** `lib/snow_qc.py`, class `SnowQualityControl`

Weather buoys (A-series) measure air temperature using dedicated meteorological instruments. They receive the same automated QC as snow buoys, using the `SnowQualityControl` module, since both measure air temperature at or near the ice surface using simple thermometers rather than thermistor strings. The QC assigns only Flag 0 (Good) or Flag 2 (Invalid) — there is no Flag 1 (Suspect).

### 4.5.1 Flag 2 — Invalid

| Condition | Config parameter |
|---|---|
| `t < min_temp_limit` | `min_temp_limit` (−70°C) |
| `t > max_temp_limit` | `max_temp_limit` (25°C) |
| Hourly rate of change > `max_hourly_jump` | `max_hourly_jump` (10°C/hr) |

All other observations are assigned Flag 0.

### 4.5.2 Configurable Parameters

```yaml
qc:
  enabled: true
  params:
    min_temp_limit: -70.0
    max_temp_limit: 25.0
    max_hourly_jump: 10.0
```

---

## 4.6 SvalMIZ OpenMetBuoy (OMB)

SvalMIZ OpenMetBuoy records from the NetCDF file are not subject to automated QC. Both `Ts_Q` and `T2m_Q` are set to the `quality_flag` value specified in the YAML configuration entry, which is currently `0` (Good).

The rationale is that SvalMIZ OMB data are provided as QCed data and are assumed to be good. If problems are identified in these records, the `quality_flag` in the YAML can be changed to `1` or `2` to apply a blanket manual flag to the entire dataset.

---

## 4.7 Flag Propagation in the Export

The flag assignment and export logic in `ist_buoy_validation_data.py` works as follows:

1. Both `ts_flags` and `t2m_flags` are initialised to a Series of `−9` (no QC, no measurement) for all timesteps.

2. For **thermistor string buoys**, `ts_flags` is overwritten with the output of `simba_qc.compute_flags()`. The `t2m_flags` series is set to the manual `quality_flag` from the YAML (typically `0`).

3. For **SVP and CALIB buoys**, `t2m_flags` is overwritten with the output of `svp_qc.compute_flags()`. This returns `−9` for observations that pass the hardware checks (meaning "measurement exists, representativeness not assessed") and `2` for Invalid observations. The `ts_flags` series remains `−9` throughout, reflecting the absence of a skin temperature sensor.

4. For **snow buoys and weather buoys (METEO)**, `t2m_flags` is overwritten with the output of `snow_qc.compute_flags()`, which returns `0` (Good) or `2` (Invalid). The `ts_flags` series remains `−9`.

5. For **OMBs (SvalMIZ OpenMetBuoy)**, both flag series are set to the manual `quality_flag`.

6. The `export_flags` set is read from the YAML `defaults`. For each observation, a temperature value is replaced with `NaN` (and ultimately the fill value `−99.9`) if its flag is not in `export_flags`. The output line is omitted entirely only if both temperatures would be fill values.

The flag values written to the output files are always one of `{−9, 0, 1, 2}`. For SVP and CALIB buoys, the `T2m_Q` field uses `−9` to mean "measurement present but representativeness not assessed" — distinct from a field that is `−9` because no sensor exists for that quantity.

---

## 4.8 Summary

| Module | Buoy types | Fields QC'd | Flag scheme |
|---|---|---|---|
| `simba_qc.SimbaQC` | SIMB3, SIMBA | Skin temperature only | 0, 1, 2 |
| `svp_qc.SVPQualityControl` | SVP, CALIB | Air temperature only | −9 (no QC) or 2 (invalid) |
| `snow_qc.SnowQualityControl` | Snow buoy, Weather buoy (METEO) | Air temperature only | 0, 2 only |
| — (manual) | SvalMIZ OMB | Both fields | Config value (0) |
