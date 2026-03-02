# Raw Data File Reference

This document contains the first 10 lines of each distinct file type present in `data/raw/`, organised by buoy series. One representative buoy is shown per series. Files marked **[PIPELINE]** are actively loaded by the pipeline; others are present in the archive but not currently used.

## File Naming Convention

All files follow the pattern `YEARID_IMEI_FILETYPE.csv`, where:
- `YEARID` is the buoy identifier including deployment year (e.g. `2024I15`, `2021T86`)
- `IMEI` is the Iridium modem serial number
- `FILETYPE` describes the data content and processing level (e.g. `TEMP_proc`, `AUX_raw+filterflag`)

The `_proc` suffix indicates AWI-processed data; `_raw+filterflag` indicates raw transmitted data with an added GPS quality flag column.

---

## I-series (SIMB3) — Example: `2024I15`

### `TEMP_proc.csv` — **[PIPELINE: primary file]**

Processed thermistor string temperatures. 161 columns: `time`, `wdt_counter`, then `T0`–`T158` (159 sensor columns, 2 cm spacing). Note: only columns T0–T158 are shown in the header; data rows below are truncated at T5 for readability.

```
time,wdt_counter,T0 (degC),T1 (degC),T2 (degC),T3 (degC),T4 (degC),T5 (degC),...,T158 (degC)
2024-09-08T16:00:30,11.000000,-2.500000,-2.625000,-2.500000,-2.375000,-2.500000,-2.500000,...,-2.625000
2024-09-08T20:00:31,12.000000,-3.125000,-3.250000,-3.125000,-3.062500,-3.187500,-3.125000,...,-3.000000
2024-09-09T00:00:30,13.000000,-4.750000,-4.937500,-4.812500,-4.687500,-4.875000,-4.875000,...,-4.625000
2024-09-09T04:00:30,14.000000,-5.187500,-5.312500,-5.187500,-5.062500,-5.250000,-5.250000,...,-5.125000
2024-09-09T08:00:30,15.000000,-6.750000,-6.937500,-6.812500,-6.687500,-6.937500,-6.875000,...,-1.750000
2024-09-09T12:00:30,16.000000,-8.312500,-8.437500,-8.312500,-8.187500,-8.437500,-8.437500,...,-1.625000
2024-09-09T16:00:30,17.000000,-6.500000,-6.687500,-6.500000,-6.500000,-6.687500,-6.687500,...,-1.562500
2024-09-09T20:00:30,18.000000,-5.750000,-5.937500,-5.750000,-5.687500,-5.937500,-5.875000,...,-1.562500
2024-09-10T00:00:30,19.000000,-4.625000,-4.625000,-4.375000,-4.312500,-4.437500,-4.312500,...,-1.562500
```

**Key observations:** Observations are 4-hourly. Sensors near the top (T0–T25 at this timestamp) read colder (−3 to −9°C, air side), while deeper sensors read near −1.5°C (ocean side). The snow–ice transition is visible as a step change in values.

---

### `AUX_proc.csv` — **[PIPELINE: aux file]**

Processed auxiliary metadata. Columns: `time`, `latitude`, `longitude`, `temperature_air`, `barometric_pressure`, `water_depth`, `temperature_water`, `snow_distance`, `battery_voltage`, `gps_satellites`, `iridium_signal`, `iridium_retries`.

```
time,latitude (deg),longitude (deg),temperature_air (degC),barometric_pressure (hPa),water_depth (m), temperature_water (degC),snow_distance (m),battery_voltage (V),gps_satellites (none),iridium_signal (none),iridium_retries (none)
2024-09-08T16:00:30,84.942552,162.159344,-8.000000,1011.000000,1.700000,-1.890000,0.944000,18.850000,11.000000,4.000000,0.000000
2024-09-08T20:00:31,84.932144,162.223504,-5.937500,1012.700000,1.700000,-1.890000,0.960000,18.830000,8.000000,5.000000,0.000000
2024-09-09T00:00:30,84.939544,162.252080,-5.375000,1014.200000,1.700000,-1.920000,0.981000,18.830000,7.000000,5.000000,0.000000
2024-09-09T04:00:30,84.946176,162.377120,-5.125000,1015.700000,0.910000,-1.920000,0.986000,18.800000,11.000000,5.000000,0.000000
2024-09-09T08:00:30,84.940816,162.393872,-6.062500,1017.100000,0.500000,-1.900000,0.978000,18.800000,11.000000,3.000000,0.000000
2024-09-09T12:00:30,84.947056,162.307808,-9.312500,1017.700000,1.700000,-1.860000,0.971000,18.800000,7.000000,5.000000,0.000000
2024-09-09T16:00:30,84.955392,162.312960,-7.812500,1018.300000,1.700000,-1.850000,0.972000,18.780000,10.000000,1.000000,0.000000
2024-09-09T20:00:30,84.953584,162.181840,-6.125000,1018.700000,0.410000,-1.920000,0.972000,18.780000,11.000000,4.000000,0.000000
2024-09-10T00:00:30,84.963760,161.994848,-4.125000,1018.500000,0.450000,-1.860000,0.973000,18.750000,8.000000,5.000000,0.000000
```

**Key observations:** The `snow_distance` column (metres from sonar mast to snow surface) is the sonar measurement used as a diagnostic cross-check in the inspection tool. `temperature_water` is a sub-ice ocean temperature sensor. Air temperatures here are −4 to −9°C.

---

### `AUX_raw+filterflag.csv` — [not used by pipeline]

Identical columns to `AUX_proc.csv` plus one additional column: `filter_flag_gps` (0 = good GPS fix, 1 = fix quality suspect).

```
time,latitude (deg),longitude (deg),temperature_air (degC),barometric_pressure (hPa),water_depth (m), temperature_water (degC),snow_distance (m),battery_voltage (V),gps_satellites (none),iridium_signal (none),iridium_retries (none),filter_flag_gps
2024-09-08T16:00:30,84.942552,162.159344,-8.000000,1011.000000,1.700000,-1.890000,0.944000,18.850000,11.000000,4.000000,0.000000,0
2024-09-08T20:00:31,84.932144,162.223504,-5.937500,1012.700000,1.700000,-1.890000,0.960000,18.830000,8.000000,5.000000,0.000000,0
2024-09-09T00:00:30,84.939544,162.252080,-5.375000,1014.200000,1.700000,-1.920000,0.981000,18.830000,7.000000,5.000000,0.000000,0
2024-09-09T04:00:30,84.946176,162.377120,-5.125000,1015.700000,0.910000,-1.920000,0.986000,18.800000,11.000000,5.000000,0.000000,0
2024-09-09T08:00:30,84.940816,162.393872,-6.062500,1017.100000,0.500000,-1.900000,0.978000,18.800000,11.000000,3.000000,0.000000,0
2024-09-09T12:00:30,84.947056,162.307808,-9.312500,1017.700000,1.700000,-1.860000,0.971000,18.800000,7.000000,5.000000,0.000000,0
2024-09-09T16:00:30,84.955392,162.312960,-7.812500,1018.300000,1.700000,-1.850000,0.972000,18.780000,10.000000,1.000000,0.000000,0
2024-09-09T20:00:30,84.953584,162.181840,-6.125000,1018.700000,0.410000,-1.920000,0.972000,18.780000,11.000000,4.000000,0.000000,0
2024-09-10T00:00:30,84.963760,161.994848,-4.125000,1018.500000,0.450000,-1.860000,0.973000,18.750000,8.000000,5.000000,0.000000,0
```

---

## T-series (Legacy SIMBA) — Example: `2021T86`

### `TEMP_proc.csv` — **[PIPELINE: primary file (when available)]**

Processed thermistor string temperatures. 244 columns: `time`, `latitude`, `longitude`, then `T1`–`T241` (241 sensor columns). Unlike SIMB3, the processed TEMP file includes GPS coordinates. Data rows truncated at T5 for readability.

```
time,latitude (deg),longitude (deg),T1 (degC),T2 (degC),T3 (degC),T4 (degC),T5 (degC),...,T241 (degC)
2021-03-17T19:00:18,-70.882030,-4.272780,-1.8125,-1.8125,-1.8750,-1.8125,-1.8750,...,-14.0625
2021-03-18T01:00:18,-70.610660,-7.687380,-1.8125,-1.8125,-1.8750,-1.8125,-1.8750,...,-11.4375
2021-03-18T07:00:18,-70.639620,-7.808990,-1.8125,-1.8125,-1.8750,-1.8125,-1.8750,...,-16.5000
2021-03-18T13:00:18,-70.648700,-7.594640,-1.8750,-1.8125,-1.8750,-1.8125,-1.8750,...,-7.8750
2021-03-18T19:00:18,-70.685030,-7.823710,-1.8125,-1.8125,-1.8750,-1.8125,-1.8750,...,-11.0000
2021-03-19T01:00:18,-70.639620,-7.808990,-1.8125,-1.8125,-1.8750,-1.8125,-1.8750,...,-9.8750
2021-03-19T07:00:18,-70.606100,-7.794330,-1.8750,-1.8125,-1.8750,-1.8125,-1.8750,...,-9.3750
2021-03-19T13:00:17,-70.630300,-8.023120,-1.8750,-1.8125,-1.8750,-1.8125,-1.8750,...,-8.4375
2021-03-19T19:00:17,-70.639620,-7.808990,-1.8125,-1.8125,-1.8750,-1.8125,-1.8750,...,-11.0000
```

**Key observations:** Observations are 6-hourly (vs. 4-hourly for SIMB3). This buoy was deployed in Antarctic pack ice (around 70°S). The entire column reads near −1.8°C — near the seawater freezing point — suggesting the ice is relatively thin or isothermal. The final column (T241) is notably colder (−7 to −16°C), which is the bottom sensor; this may indicate a partial short-circuit or read error common on the last sensor.

---

### `TEMP_raw+filterflag.csv` — **[PIPELINE: primary file (preferred when TEMP_proc absent)]**

Raw thermistor string temperatures with GPS filter flag. 245 columns: `time`, `latitude`, `longitude`, `filter_flag_gps`, then `T1`–`T241`. Data layout is identical to `TEMP_proc` except the `filter_flag_gps` column is inserted after the coordinates.

```
time,latitude (deg),longitude (deg),filter_flag_gps (),T1 (degC),T2 (degC),...,T241 (degC)
2021-03-17T19:00:18,-70.882030,-4.272780,0,-1.8125,-1.8125,...,-14.0625
2021-03-18T01:00:18,-70.610660,-7.687380,1,-1.8125,-1.8125,...,-11.4375
2021-03-18T07:00:18,-70.639620,-7.808990,1,-1.8125,-1.8125,...,-16.5000
2021-03-18T13:00:18,-70.648700,-7.594640,0,-1.8750,-1.8125,...,-7.8750
2021-03-18T19:00:18,-70.685030,-7.823710,0,-1.8125,-1.8125,...,-11.0000
2021-03-19T01:00:18,-70.639620,-7.808990,0,-1.8125,-1.8125,...,-9.8750
2021-03-19T07:00:18,-70.606100,-7.794330,0,-1.8750,-1.8125,...,-9.3750
2021-03-19T13:00:17,-70.630300,-8.023120,0,-1.8750,-1.8125,...,-8.4375
2021-03-19T19:00:17,-70.639620,-7.808990,0,-1.8125,-1.8125,...,-11.0000
```

---

### `TS.csv` — **[PIPELINE: aux file]**

Time series file containing metadata: GPS, air temperature, barometric pressure, tilt, and compass bearing. This is the source of the air temperature value used in the pipeline for SIMBA buoys.

```
time,latitude (deg),longitude (deg),barometric pressure (hPa),air temperature (degC),tilt (deg),compass bearing (deg)
2021-03-17T19:00:15,-70.623136,-7.841605,990,-9.1250,8.0,60.0
2021-03-17T21:00:14,-70.623138,-7.841601,990,-12.3125,7.0,61.0
2021-03-17T23:00:15,-70.623123,-7.841593,989,-11.0000,8.0,62.0
2021-03-18T01:00:15,-70.623135,-7.841600,988,-10.5625,8.0,62.0
2021-03-18T03:00:14,-70.623126,-7.841568,987,-11.1250,8.0,64.0
2021-03-18T05:00:15,-70.623130,-7.841601,986,-14.4375,7.0,62.0
2021-03-18T07:00:15,-70.623143,-7.841596,985,-15.7500,7.0,60.0
2021-03-18T09:00:15,-70.623140,-7.841618,984,-14.9375,8.0,59.0
2021-03-18T11:00:14,-70.623128,-7.841590,982,-11.1250,8.0,63.0
```

**Key observations:** The TS file has 2-hourly resolution (denser than TEMP). Note the GPS coordinates are slightly different from the TEMP file coordinates — the TS uses a separate GPS fix timestamp. Air temperatures here (−9 to −16°C) are significantly colder than the ice surface, consistent with a cold Antarctic winter atmosphere.

---

### `HEAT030_proc.csv` — [not used by pipeline]

Heat pulse data recorded 30 seconds after an 8 V heating pulse is applied to the thermistor chain. The differential temperature rise at each sensor encodes the thermal conductivity of the surrounding medium, enabling interface detection under isothermal conditions. 244 columns: `time`, `latitude`, `longitude`, then `H1`–`H241`. Values are the temperature *rise* (°C) above baseline.

```
time,latitude (deg),longitude (deg),H1 (degC),...,H241 (degC)
2021-03-18T01:01:40,-70.639620,-7.808990,0.6875,...,0.0625
2021-03-19T01:01:34,-70.644190,-7.701850,0.6875,...,0.0625
2021-03-20T01:01:33,-70.639620,-7.808990,0.6875,...,0.0000
2021-03-21T01:01:57,-70.639620,-7.808990,0.6875,...,0.0000
2021-03-22T01:01:33,-70.606100,-7.794330,0.7500,...,0.0000
2021-03-23T01:01:33,-70.639620,-7.808990,0.7500,...,0.0000
2021-03-24T01:01:44,-70.639620,-7.808990,0.8125,...,0.0000
2021-03-25T01:01:33,-70.610660,-7.687380,0.8125,...,0.0000
2021-03-26T01:01:33,-70.639620,-7.808990,0.8125,...,0.0000
```

**Key observations:** Observations are daily. Temperature rises near the top of the string (~0.7–0.8°C) are consistent with sensors in air; rises in ice are lower (~0.5–0.6°C); sensors in brine or ocean show even lower rises.

---

### `HEAT120_proc.csv` — [not used by pipeline]

As `HEAT030_proc.csv` but measured 120 seconds after the heating pulse. Longer integration gives a stronger thermal conductivity signal.

```
time,latitude (deg),longitude (deg),H1 (degC),...,H241 (degC)
2021-03-18T01:01:40,-70.639620,-7.808990,0.6250,...,0.0000
2021-03-19T01:01:34,-70.644190,-7.701850,0.6250,...,0.0000
2021-03-20T01:01:33,-70.639620,-7.808990,0.6875,...,0.0000
2021-03-21T01:01:57,-70.639620,-7.808990,0.6875,...,0.0000
2021-03-22T01:01:33,-70.606100,-7.794330,0.7500,...,0.0000
2021-03-23T01:01:33,-70.639620,-7.808990,0.8750,...,0.0000
2021-03-24T01:01:44,-70.639620,-7.808990,0.8750,...,-0.0625
2021-03-25T01:01:33,-70.610660,-7.687380,0.8750,...,0.0000
2021-03-26T01:01:33,-70.639620,-7.808990,0.8750,...,0.0000
```

---

### `raw+filterflag.csv` — [not used by pipeline]

A "summary" raw file containing only GPS, pressure, air temperature, tilt and compass — no thermistor string data. Format is identical to `TS.csv` plus a `filter_flag_gps` column. This appears to be an alternative to the `TS.csv` file.

```
time,latitude (deg),longitude (deg),barometric pressure (hPa),air temperature (degC),tilt (deg),compass bearing (deg),filter_flag_gps ()
2021-03-17T19:00:15,-70.623136,-7.841605,990,-9.1250,8.0,60.0,0
2021-03-17T21:00:14,-70.623138,-7.841601,990,-12.3125,7.0,61.0,0
2021-03-17T23:00:15,-70.623123,-7.841593,989,-11.0000,8.0,62.0,0
2021-03-18T01:00:15,-70.623135,-7.841600,988,-10.5625,8.0,62.0,0
2021-03-18T03:00:14,-70.623126,-7.841568,987,-11.1250,8.0,64.0,0
2021-03-18T05:00:15,-70.623130,-7.841601,986,-14.4375,7.0,62.0,0
2021-03-18T07:00:15,-70.623143,-7.841596,985,-15.7500,7.0,60.0,0
2021-03-18T09:00:15,-70.623140,-7.841618,984,-14.9375,8.0,59.0,0
2021-03-18T11:00:14,-70.623128,-7.841590,982,-11.1250,8.0,63.0,0
```

---

## S-series (Snow buoy) — Example: `2023S100`

### `raw+filterflag.csv` — **[PIPELINE: primary file]**

The pipeline config for snow buoys uses `*raw+filterflag.csv` as the primary file. Contains GPS, four snow distance sensors, air temperature, body temperature, barometric pressure, and individual filter flags for each sensor channel.

```
time,latitude (deg),longitude (deg),distance_to_initial_snow_ice_interface_1 (m),distance_to_initial_snow_ice_interface_2 (m),distance_to_initial_snow_ice_interface_3 (m),distance_to_initial_snow_ice_interface_4 (m),barometric_pressure (hPa),temperature_air (degC),temperature_body (degC),GPS_time_since_last_fix (min),filter_flag_snow1,filter_flag_snow2,filter_flag_snow3,filter_flag_snow4,filter_flag_baro_press,filter_flag_temp_air,filter_flag_temp_body,filter_flag_gps
2023-09-09T13:00:00,89.9156,0.2194,0.204,0.180,0.180,0.192,1003.4,-5.4,0.1,0,0,0,0,4,0,0,0,1
2023-09-09T14:00:00,89.9128,-1.0948,0.204,0.180,0.180,0.182,1003.3,-6.1,0.2,0,0,0,0,0,0,0,0,1
2023-09-09T15:00:00,89.9094,-1.6288,0.204,0.180,0.180,0.172,1003.1,-6.3,0.3,0,0,0,0,0,0,0,0,1
2023-09-09T16:00:00,89.9056,-1.6110,0.194,0.180,0.180,0.172,1002.9,-6.1,0.3,0,0,0,0,0,0,0,0,1
2023-09-09T17:00:00,89.9008,-1.2546,0.194,0.180,0.180,0.172,1002.8,-6.3,0.4,0,0,0,0,0,0,0,0,1
2023-09-09T18:00:00,89.8950,-0.9746,0.204,0.180,0.180,0.152,1002.7,-5.5,0.4,0,0,0,0,0,0,0,0,1
2023-09-09T19:00:00,89.8882,-1.1100,0.204,0.180,0.180,0.142,1002.6,-5.0,0.5,0,0,0,0,0,0,0,0,1
2023-09-09T20:00:00,89.8812,-1.5994,0.204,0.190,0.180,0.122,1002.6,-4.3,0.5,0,0,0,0,0,0,0,0,0
2023-09-09T21:00:00,89.8744,-2.2574,0.204,0.180,0.180,0.132,1002.5,-3.8,0.6,0,0,0,0,0,0,0,0,0
```

**Key observations:** Hourly observations. The four `distance_to_initial_snow_ice_interface` columns are ultrasonic snow depth sensors. `temperature_air` is the near-surface air temperature used by the pipeline; `temperature_body` is the sensor housing temperature. The individual `filter_flag_*` columns give per-channel AWI quality flags. `filter_flag_gps = 1` on the first rows indicates a GPS fix timing issue.

---

### `proc.csv` — [not used by pipeline]

Processed version of the same data: identical columns except the per-channel filter flags are omitted.

```
time,latitude (deg),longitude (deg),distance_to_initial_snow_ice_interface_1 (m),distance_to_initial_snow_ice_interface_2 (m),distance_to_initial_snow_ice_interface_3 (m),distance_to_initial_snow_ice_interface_4 (m),barometric_pressure (hPa),temperature_air (degC),temperature_body (degC),GPS_time_since_last_fix (min)
2023-09-09T13:00:00,89.9156,0.2194,0.204,0.180,0.180,NaN,1003.4,-5.4,0.1,0
2023-09-09T14:00:00,89.9128,-1.0948,0.204,0.180,0.180,0.182,1003.3,-6.1,0.2,0
2023-09-09T15:00:00,89.9094,-1.6288,0.204,0.180,0.180,0.172,1003.1,-6.3,0.3,0
2023-09-09T16:00:00,89.9056,-1.6110,0.194,0.180,0.180,0.172,1002.9,-6.1,0.3,0
2023-09-09T17:00:00,89.9008,-1.2546,0.194,0.180,0.180,0.172,1002.8,-6.3,0.4,0
2023-09-09T18:00:00,89.8950,-0.9746,0.204,0.180,0.180,0.152,1002.7,-5.5,0.4,0
2023-09-09T19:00:00,89.8882,-1.1100,0.204,0.180,0.180,0.142,1002.6,-5.0,0.5,0
2023-09-09T20:00:00,89.8812,-1.5994,0.204,0.190,0.180,0.122,1002.6,-4.3,0.5,0
2023-09-09T21:00:00,89.8744,-2.2574,0.204,0.180,0.180,0.132,1002.5,-3.8,0.6,0
```

**Note:** The `proc.csv` lacks the per-channel filter flags and the `NaN` in sensor 4 of the first row is a missing value (raw+filterflag shows `0.192` with `filter_flag_snow4 = 4`). The pipeline uses `raw+filterflag.csv` to have access to those flags, even though the pipeline's own QC does not currently use the per-channel filter flags directly.

---

## A-series (Weather buoy) — Example: `2024A7`

### `raw+filterflag.csv` — **[PIPELINE: primary file]**

Raw data with GPS filter flag. Columns: `time`, `latitude`, `longitude`, `temperature`, `temperature_air`, `temperature_air_1m`, `temperature_body`, `barometric_pressure`, `battery_voltage`, `wind_speed`, `wind_direction`, `filter_flag_gps`.

```
time,latitude (deg),longitude (deg),temperature (degC),temperature_air (degC),temperature_air_1m (degC),temperature_body (degC),barometric_pressure (hPa),battery_voltage (V),wind_speed (m/s),wind_direction (deg),filter_flag_gps
2024-09-11T06:00:00,84.9615,179.5264,-2.21,-2.87,-2.86,-2.80,1015.694,12.45,4.36367,80.4,0
2024-09-11T07:00:00,84.9624,179.5559,-76.32,-2.91,-2.93,-3.06,1015.674,12.43,4.75591,80.1,0
2024-09-11T08:00:00,84.9620,179.5639,-95.40,-2.86,-2.84,-3.02,1015.524,12.44,5.73651,89.0,0
2024-09-11T09:00:00,84.9615,179.5439,-95.80,-2.92,-2.92,-3.00,1015.644,12.43,3.97143,58.3,0
2024-09-11T10:00:00,84.9614,179.4969,-97.60,-2.73,-2.72,-3.00,1015.383,12.43,4.85397,31.6,0
2024-09-11T11:00:00,84.9620,179.4268,-75.61,-3.12,-3.15,-3.12,1015.023,12.42,4.95203,31.1,0
2024-09-11T12:00:00,84.9646,179.3422,-41.75,-3.38,-3.39,-3.52,1014.659,12.42,6.91323,40.8,0
2024-09-11T13:00:00,84.9699,179.2607,-105.20,-3.93,-3.96,-3.73,1014.511,12.42,6.32487,46.5,0
2024-09-11T14:00:00,84.9767,179.1970,-106.00,-3.78,-3.80,-3.90,1014.699,12.42,5.44233,45.2,0
```

**Key observations:** The weather buoy carries **three temperature channels**: `temperature`, `temperature_air`, and `temperature_air_1m`. The pipeline maps only `temperature_air (degC)`. The `temperature_air_1m` column is a second near-surface air temperature sensor at 1 m height, which the pipeline does not currently use but could be a useful cross-check. The `temperature` column shows large anomalous negative values (−76 to −106°C on this buoy); the column's purpose is not documented by AWI and the values are clearly non-physical — it is not used by the pipeline. Wind speed and direction are available from weather buoys.

---

### `proc.csv` — [not used by pipeline]

Processed version: identical columns except `filter_flag_gps` is removed.

```
time,latitude (deg),longitude (deg),temperature (degC),temperature_air (degC),temperature_air_1m (degC),temperature_body (degC),barometric_pressure (hPa),battery_voltage (V),wind_speed (m/s),wind_direction (deg)
2024-09-11T06:00:00,84.9615,179.5264,-2.21,-2.87,-2.86,-2.80,1015.694,12.45,4.36367,80.4
2024-09-11T07:00:00,84.9624,179.5559,-76.32,-2.91,-2.93,-3.06,1015.674,12.43,4.75591,80.1
2024-09-11T08:00:00,84.9620,179.5639,-95.40,-2.86,-2.84,-3.02,1015.524,12.44,5.73651,89.0
2024-09-11T09:00:00,84.9615,179.5439,-95.80,-2.92,-2.92,-3.00,1015.644,12.43,3.97143,58.3
2024-09-11T10:00:00,84.9614,179.4969,-97.60,-2.73,-2.72,-3.00,1015.383,12.43,4.85397,31.6
2024-09-11T11:00:00,84.9620,179.4268,-75.61,-3.12,-3.15,-3.12,1015.023,12.42,4.95203,31.1
2024-09-11T12:00:00,84.9646,179.3422,-41.75,-3.38,-3.39,-3.52,1014.659,12.42,6.91323,40.8
2024-09-11T13:00:00,84.9699,179.2607,-105.20,-3.93,-3.96,-3.73,1014.511,12.42,6.32487,46.5
2024-09-11T14:00:00,84.9767,179.1970,-106.00,-3.78,-3.80,-3.90,1014.699,12.42,5.44233,45.2
```

---

## C-series (CALIB buoy) — Example: `2021C26`

### `raw+filterflag.csv` — [not used by pipeline]

Raw data with GPS filter flag. Columns: `time`, `latitude`, `longitude`, `temperature_surface`, `barometric_pressure`, `GPS_time_since_last_fix`, `filter_flag_gps`.

```
time,latitude (deg),longitude (deg),temperature_surface (degC),barometric_pressure (hPa),GPS_time_since_last_fix (min),filter_flag_gps
2021-07-29T12:19:00,84.0758,-40.7576,15.5,903.8,0,0
2021-07-29T13:00:00,84.0782,-40.7434,11.0,1013.6,0,0
2021-07-29T14:00:00,84.0794,-40.7384,9.3,1014.8,0,0
2021-07-29T15:00:00,84.0802,-40.7314,8.7,1014.8,0,0
2021-07-29T16:00:00,84.0800,-40.7228,7.9,1014.3,0,0
2021-07-29T17:00:00,84.0786,-40.7158,7.2,1014.6,0,0
2021-07-29T18:00:00,84.0760,-40.7132,7.0,1014.6,0,0
2021-07-29T19:00:00,84.0724,-40.7184,6.6,1014.6,0,0
2021-07-29T20:00:00,84.0686,-40.7362,7.0,1014.8,0,0
```

**Key observations:** Only a single temperature column (`temperature_surface`) — this is mapped to `air_temp` in the pipeline config. The data starts in late July 2021; temperatures of 7–15°C are unrealistically warm for near-surface air over sea ice and almost certainly reflect solar heating of the sensor housing on this initial record (note the `15.5°C` first observation). The pressure of `903.8 hPa` on the first row is also anomalous (likely a sensor initialization artifact; subsequent rows show ~1014 hPa which is physically plausible).

---

### `proc.csv` — **[PIPELINE: primary file]**

Processed version: identical columns except `filter_flag_gps` is removed.

```
time,latitude (deg),longitude (deg),temperature_surface (degC),barometric_pressure (hPa),GPS_time_since_last_fix (min)
2021-07-29T12:19:00,84.0758,-40.7576,15.5,903.8,0
2021-07-29T13:00:00,84.0782,-40.7434,11.0,1013.6,0
2021-07-29T14:00:00,84.0794,-40.7384,9.3,1014.8,0
2021-07-29T15:00:00,84.0802,-40.7314,8.7,1014.8,0
2021-07-29T16:00:00,84.0800,-40.7228,7.9,1014.3,0
2021-07-29T17:00:00,84.0786,-40.7158,7.2,1014.6,0
2021-07-29T18:00:00,84.0760,-40.7132,7.0,1014.6,0
2021-07-29T19:00:00,84.0724,-40.7184,6.6,1014.6,0
2021-07-29T20:00:00,84.0686,-40.7362,7.0,1014.8,0
```

---

## P-series (SVP buoy) — Example: `2023P261`

### `raw+filterflag.csv` — [not used by pipeline]

Raw data with GPS filter flag. Columns: `time`, `latitude`, `longitude`, `drift_speed`, `temperature_surface`, `barometric_pressure`, `battery_voltage`, `GPS_time_since_last_fix`, `number_of_satellites`, `filter_flag_gps`.

```
time,latitude (deg),longitude (deg),drift_speed (m/s),temperature_surface (degC),barometric_pressure (hPa),battery_voltage(V),GPS_time_since_last_fix (min),number_of_satellites,filter_flag_gps ()
2023-09-01T08:00:00,85.9447,128.1846,0.000,0.6,997.9,15.8,0,6,0
2023-09-01T09:00:00,85.9437,128.2020,0.049,0.2,998.0,15.8,0,11,0
2023-09-01T10:00:00,85.9422,128.2065,0.048,0.2,998.0,15.8,0,8,0
2023-09-01T11:00:00,85.9404,128.1997,0.058,0.2,997.6,15.8,0,11,0
2023-09-01T12:00:00,85.9383,128.1790,0.079,0.2,997.4,15.8,0,12,0
2023-09-01T13:00:00,85.9361,128.1469,0.098,0.2,997.3,15.8,0,11,0
2023-09-01T14:00:00,85.9341,128.1106,0.101,0.2,997.2,15.8,0,10,0
2023-09-01T15:00:00,85.9322,128.0708,0.106,0.2,997.3,15.8,0,11,0
2023-09-01T16:00:00,85.9302,128.0231,0.122,0.2,997.1,15.8,0,9,0
```

**Key observations:** Hourly observations. `drift_speed` is a derived quantity (not used by pipeline). `temperature_surface` is mapped to `air_temp` in the pipeline config (same mapping as CALIB). `number_of_satellites` is present in the raw file but not in the processed version.

---

### `proc.csv` — **[PIPELINE: primary file]**

Processed version: `filter_flag_gps` and `number_of_satellites` are removed.

```
time,latitude (deg),longitude (deg),drift_speed (m/s),temperature_surface (degC),barometric_pressure (hPa),battery_voltage(V),GPS_time_since_last_fix (min),number_of_satellites ()
2023-09-01T08:00:00,85.9447,128.1846,0.000,0.6,997.9,15.8,0,6
2023-09-01T09:00:00,85.9437,128.2020,0.049,0.2,998.0,15.8,0,11
2023-09-01T10:00:00,85.9422,128.2065,0.048,0.2,998.0,15.8,0,8
2023-09-01T11:00:00,85.9404,128.1997,0.058,0.2,997.6,15.8,0,11
2023-09-01T12:00:00,85.9383,128.1790,0.079,0.2,997.4,15.8,0,12
2023-09-01T13:00:00,85.9361,128.1469,0.098,0.2,997.3,15.8,0,11
2023-09-01T14:00:00,85.9341,128.1106,0.101,0.2,997.2,15.8,0,10
2023-09-01T15:00:00,85.9322,128.0708,0.106,0.2,997.3,15.8,0,11
2023-09-01T16:00:00,85.9302,128.0231,0.122,0.2,997.1,15.8,0,9
```

**Note:** The `proc.csv` appears to still include `number_of_satellites` despite having `filter_flag_gps` removed — the difference between proc and raw+filterflag is less consistent for P-series than for other buoy types. This may vary by buoy.

---

## Dataset-Wide Column Variability

The preceding sections show one representative buoy per series. The full dataset contains hardware variants with different column structures. This section documents all known variants found by scanning every file in `data/raw/`.

---

### P-series (SVP) — 6 variants

The SVP buoys show the most hardware diversity in the dataset.

| Type | Key columns | Buoys (n) | Pipeline impact |
|---|---|---|---|
| **Type 1** | `temperature_surface`, `submerged_boolean`, `accelometer_variance`, `sampling_ratio` | 2022P259, 2022P260, 2023P292–P298, 2024P311–P315 (14) | Maps `temperature_surface` ✅ |
| **Type 1b** | `temperature_surface`, `submerged_boolean`, `sampling_ratio` (no accelometer) | 2023P272–P285, 2025P276, 2025P316–P333, 2026P340, 2026P342 (29) | Maps `temperature_surface` ✅ |
| **Type 2** | `temperature_surface`, `barometric_pressure`, `battery_voltage`, `GPS_time_since_last_fix`, `number_of_satellites` | 2022P238–P242, 2023P261–P268, 2024P299–P311, 2025P343–P352 (34) | Maps `temperature_surface` ✅; barometric pressure is a bonus column not in the config |
| **Type 3** | `drift_speed` only — no `temperature_surface` | 2023P286, 2023P288–P290 (4) | `air_temp` returns NaN; records omitted from output |
| **Type 4** | `temperature_surface`, `battery_voltage`, `GPS_signal_to_noise_ratio`, `GPS_time_since_last_fix` | 2022P253, 2022P258 (2) | Maps `temperature_surface` ✅ |
| **Type 5** | `temperature_surface`, `barometric_pressure`, `barometric_pressure_tendency`, `submerged_boolean`, `accelometer_variance`, `sampling_ratio` | 2025P318, 2025P319 (2) | Maps `temperature_surface` ✅ |

The `submerged_boolean` column (Types 1, 1b, 5) indicates whether the sensor has gone below the waterline. This could be used as an additional QC flag but is not currently read by the pipeline.

---

### I-series (SIMB3) — 2 AUX variants

TEMP files are fully uniform across all 7 buoys (159 T-columns, T0–T158, 4-hourly).

AUX files have two variants:

| Variant | Extra columns | Buoys |
|---|---|---|
| Standard | *(12 cols: lat, lon, air_temp, pressure, water_depth, temperature_water, snow_distance, battery_voltage, gps_satellites, iridium_signal, iridium_retries)* | 2024I14, 2024I15, 2024I16, 2025I17 |
| With IMU | Same + `pitch (deg)`, `roll (deg)`, `heading (none)` | 2023I10, 2023I11, 2023I12 |

**2023I8 and 2023I9** are a separate hardware variant: their AUX file matches the Standard format, but they also have an additional ocean CTD file (`*_proc.csv` with columns `ocean_conductivity (mS)`, `ocean_temperature (degC)`, `ocean_pressure (hPa)`). This file is not used by the pipeline and has no effect on processing.

---

### T-series (SIMBA) — variable string length

The TEMP thermistor string length is not fixed. The pipeline handles this correctly (T-columns are detected dynamically), but the variation should be noted.

| String length | T-columns | Buoys (n) |
|---|---|---|
| 240 sensors (T1–T240, 4.80 m) | 240 | Most buoys 2022–2026 (40 buoys) |
| 241 sensors (T1–T241, 4.82 m) | 241 | Oldest batch 2021–2022: 2021T86, 2021T87, 2022T88, 2022T95–T98 (7 buoys) |
| 242 sensors (T1–T242, 4.84 m) | 242 | 2023T89, 2024T125, 2025T146 (3 buoys) |
| 264 sensors (T1–T264, 5.28 m) | 264 | 2023T106 only (1 buoy) |

**2023T113** — standard 240-column header but only 15 data rows (early deployment failure or retrieval issue). Processes normally.

**2024T124** — anomalous: the file named `*_TEMP_raw+filterflag.csv` actually contains radiation sensor data (`longwave_radiation_up`, `shortwave_radiation_down`, `albedo_surface`, etc.). This appears to be a data archive labelling error. The file does not contain T-columns and will not be picked up by the T-column detector; the TS aux file will still load normally if present.

---

### S-series (Snow) — fully uniform

All 43 snow buoys have identical column structures. The only variation is `proc.csv` (without per-channel filter flags) vs `raw+filterflag.csv` (with filter flags). No sub-types detected.

---

### A-series (Weather) — 3 hardware types

Three distinct instrument packages have been deployed under the A-series identifier.

| Type | Key columns | Buoys | Pipeline impact |
|---|---|---|---|
| **Standard** | `temperature`, `temperature_air`, `temperature_air_1m`, `temperature_body`, `barometric_pressure`, `battery_voltage`, `wind_speed`, `wind_direction` | 2024A7 | Maps `temperature_air` ✅ |
| **Dual-height** | `temperature`, `temperature_air_1m`, `temperature_air_2m`, `temperature_body`, `barometric_pressure`, `barometric_voltage`, `num1` | 2024A8 | **Fallback mapping:** Data loader tries `temperature_air` first, then `temperature_air_2m`, then `temperature_air_1m`. ✅ Works without modification. |
| **Radiation station** | `temperature`, `temperature_air`, `barometric_pressure`, `humidity_relative`, `wind_speed_vector`, `wind_direction`, `longwave_radiation_up`, `longwave_radiation_down`, `shortwave_radiation_up`, `shortwave_radiation_down`, `albedo_surface` | 2025A6 | Maps `temperature_air` ✅; the radiation columns are available but not read by the pipeline. |

The `temperature` column (first column, distinct from `temperature_air`) shows anomalous values on 2024A7 (−76 to −106°C) and is NaN on 2024A8. Its purpose is not documented by AWI and it is not used by the pipeline.

---

### C-series (CALIB) — with/without barometric pressure

| Variant | Columns | Buoys (n) |
|---|---|---|
| With pressure | `temperature_surface`, `barometric_pressure`, `GPS_time_since_last_fix` | 2021C26, 2025C41–C46 (6 buoys) |
| Without pressure | `temperature_surface`, `GPS_time_since_last_fix` (no pressure column) | 2021C36, 2021C38, 2021C40, 2022C33, 2022C35, 2022C37, 2022C39 (7 buoys) |

The pipeline config maps `pressure: "barometric_pressure (hPa)"` — for the 7 buoys without this column, the pressure field will be NaN. This is handled gracefully and has no effect on the temperature output.

---

## AWI Official Interface Temperature Dataset (SIMBA_icethick_all)

**Location:** `data/AWI_official/SIMBA_icethick_all/datasets/`

**Citation:** Preußer, A.; Nicolaus, M.; Hoppmann, M. (2025): Snow depth, sea ice thickness and interface temperatures derived from measurements of SIMBA buoys deployed in the Arctic Ocean and Southern Ocean between 2012 and 2023 [dataset publication series]. PANGAEA, https://doi.org/10.1594/PANGAEA.973193

This is the AWI official processed output for 96 SIMBA (T-series) buoys, covering 2012–2024, spanning both the Arctic (Transpolar Drift Stream) and Antarctic (Weddell Sea/Atka Bay). Interface positions and temperatures were derived using a **manual classification** method that combines the SIMBA-ET (passive temperature gradient) and SIMBA-HT (heat pulse rise ratio) signals. This dataset is the primary reference for validating our automated interface detection algorithm.

**Full 100% overlap** with all T-series buoys in our raw data (2021–2023): every buoy we process has a corresponding AWI official file.

---

### File format

Each buoy contributes one file named `YEARID_icethick.tab` (e.g., `2021T86_icethick.tab`). The files are PANGAEA-format tab-separated text. Each file begins with a multi-line comment block (`/* DATA DESCRIPTION: ... */`) containing citation metadata, parameter descriptions, and geographic/temporal coverage. The data table begins immediately after the closing `*/` line.

**Loading procedure:** Skip all lines up to and including `*/`, then read the remainder as a tab-delimited table with the first row as column names. Empty cells represent missing values (NaN).

```python
with open(f) as fh:
    lines = fh.readlines()
start = next(i for i, l in enumerate(lines) if l.strip() == '*/') + 1
df = pd.read_csv(f, sep='\t', skiprows=start, header=0, na_values=[''])
df['Date/Time'] = pd.to_datetime(df['Date/Time'])
```

---

### Columns

All 96 files share an identical column structure (no variants detected).

| Column | Unit | Description |
|---|---|---|
| `Date/Time` | ISO timestamp | Observation time |
| `Latitude` | deg | GPS latitude |
| `Longitude` | deg | GPS longitude |
| `EsEs [m]` | m | Sea ice thickness (smoothed with 3-day running mean) |
| `Snow thick [m]` | m | Snow thickness; negative values indicate onset of ice surface melt |
| `EsEs unc [m]` | m | Ice thickness uncertainty (quantised: 0.04, 0.06, 0.08, 0.12, 0.16 m; approximately 2–8× the 2 cm sensor spacing) |
| `Snow thick unc [m]` | m | Snow thickness uncertainty |
| `Dist rel atm/snow IF [m]` | m | Position of the atmosphere/snow interface relative to the initial ice surface at deployment. Positive = above ice surface level (snow present), negative = below original surface (ice melt). |
| `T atm/snow IF [°C]` | °C | **Temperature at the atmosphere/snow interface** — the primary column for IST comparison with our pipeline |
| `Thermistor atm/snow IF` | — | Thermistor number (1-indexed) at the detected atmosphere/snow interface |
| `Dist rel snow/ice IF [m]` | m | Position of the snow/ice interface relative to initial ice surface |
| `T snow/ice IF [°C]` | °C | Temperature at the snow/ice interface |
| `Thermistor snow/ice IF` | — | Thermistor number at the detected snow/ice interface |
| `Dist rel ice/oce IF [m]` | m | Position of the ice/ocean interface relative to initial ice surface |
| `T ice/oce IF [°C]` | °C | Temperature at the ice/ocean interface |
| `Thermistor ice/oce IF` | — | Thermistor number at the detected ice/ocean interface |

**Note on thermistor numbering:** AWI uses 1-indexed thermistor numbers; our pipeline uses 0-indexed `edge_idx`. Subtract 1 from the AWI thermistor number to compare directly with our output.

---

### Representative data rows — `2021T86_icethick.tab`

```
Date/Time	Latitude	Longitude	EsEs [m]	Snow thick [m]	EsEs unc [m]	Snow thick unc [m]	Dist rel atm/snow IF [m]	T atm/snow IF [°C]	Thermistor atm/snow IF	Dist rel snow/ice IF [m]	T snow/ice IF [°C]	Thermistor snow/ice IF	Dist rel ice/oce IF [m]	T ice/oce IF [°C]	Thermistor ice/oce IF
2021-03-17T19:00:18	-70.6231	-7.8416	2.360	0.080	0.04	0.04							0.0	-1.88	5
2021-03-18T01:00:18	-70.6231	-7.8416	2.363	0.080	0.06	0.06	0.08	-1.81	1	0.0	-1.88	5	-2.36	-1.81	123
2021-03-18T07:00:18	-70.6231	-7.8416	2.365	0.080	0.08	0.06	0.08	-1.81	1	0.0	-1.88	5	-2.36	-1.81	123
2021-03-18T13:00:18	-70.6231	-7.8416	2.365	0.080	0.08	0.06	0.08	-1.81	1	0.0	-1.88	5	-2.36	-1.81	123
```

**Key observations:** The first row has no atmosphere/snow interface detected (atm/snow IF columns are empty); the snow/ice interface is still present. Interface positions are relative to the initial ice surface at deployment; 0.08 m means the snow surface is 8 cm above the original ice level. Thermistor 1 at the air/snow interface indicates the top of the string.

---

### Dataset-wide statistics

| Statistic | Value |
|---|---|
| Total buoys | 96 (T-series only, 2012–2024) |
| Total observations | 66 479 |
| Dominant observation cadence | 6-hourly (89 buoys); 1-hourly (4 buoys: 2012T4, 2022T91–T93); 12-hourly (2 buoys: 2012T1, 2023T102); 15-hourly (1 buoy: 2016T44, short deployment) |
| `T atm/snow IF` range | −44.88°C to +7.81°C (mean −16.27°C) |
| `T atm/snow IF` missing rate | ~22.7% of observations (interface not detected by AWI) |
| `Dist rel atm/snow IF` range | −0.40 m to +1.52 m |
| `EsEs [m]` range | 0.22 m to 8.64 m (mean 1.89 m) |
| `Snow thick [m]` range | −0.014 m to +1.33 m; 458 rows with negative values (melt indicator) |
| Thermistor numbers at atm/snow IF | 1–114 |

---

### Missing values and interface detection gaps

When the AWI classification cannot locate an interface at a given timestep, all three columns for that interface group (`Dist rel`, `T`, `Thermistor`) are empty simultaneously — there is no partial detection. The ice thickness (`EsEs [m]`) is usually still present even when interface temperatures are missing, since it is derived from a separate smoothed estimate.

The 22.7% missing rate for `T atm/snow IF` reflects periods where the manual classifier could not confidently identify the snow surface — typically during the melt season when the isothermal condition erases the characteristic temperature gradient, or at the very start of a deployment before the string has settled thermally.

---

### Classification method

The AWI interface positions were derived by **manual classification** by Preußer et al. They combined two signals:
- **SIMBA-ET gradient**: the vertical derivative of passive temperature, used to identify the snow surface (sharp cold-to-warm transition going downward).
- **SIMBA-HT rise ratio**: the temperature rise after a resistive heating pulse, used to discriminate ice from ocean (ice has lower thermal conductivity than brine/water).

Ice and snow thickness are smoothed with a 3-day running mean before the interface positions are finalised. The overall position uncertainty is stated as 2–4× the 2 cm sensor spacing (4–8 cm) for both snow depth and ice thickness.

Our pipeline's automated algorithm (Chapter 3) uses only SIMBA-ET and does not use the heat pulse data. The thermistor number at `T atm/snow IF` (minus 1 to convert to 0-indexed) is directly comparable to our pipeline's `edge_idx - 1` output variable.

---

### Overlap with our pipeline

All 24 T-series buoys processed by our pipeline for 2021–2023 have a corresponding AWI official file:

```
2021T86, 2021T87, 2022T88, 2022T91, 2022T92, 2022T93, 2022T94, 2022T95,
2022T96, 2022T97, 2022T98, 2023T89, 2023T99, 2023T100, 2023T102, 2023T104,
2023T105, 2023T106, 2023T107, 2023T109, 2023T110, 2023T111, 2023T112, 2023T114
```

The AWI dataset extends back to 2012, giving 72 additional historical buoys for which we have official interface detections but no raw thermistor data in our pipeline's `data/raw/` directory.
