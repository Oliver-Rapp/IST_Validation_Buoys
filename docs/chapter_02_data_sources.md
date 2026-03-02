# 2. Data Sources

The validation dataset is assembled from two independent collections of drifting sea ice buoy data: processed CSV observations distributed by the Alfred Wegener Institute (AWI) Sea Ice Physics group through the Meereisportal data portal, and calibrated NetCDF data from the Norwegian Meteorological Institute's Svalbard Marginal Ice Zone (SvalMIZ) campaign. The two collections differ in data format, instrument type, and the nature of their surface temperature measurements, and are described separately below.

The pipeline is configured to process data for 2024 to 2025 by default, but can in principle be applied to any period covered by the AWI archive, which extends back to approximately 2012. For data prior to 2024 there often exist datasets that have been processed and QCed by AWI and might be more useful than using this pipeline.

---

## 2.1 AWI Meereisportal Buoy Data

The Alfred Wegener Institute (AWI) operates a large network of autonomous sea ice drifters across both polar oceans and distributes pre-processed observational data through the Meereisportal platform (https://www.meereisportal.de; Grosfeld et al., 2016). Data are publicly available as processed CSV files archived both on Meereisportal and in PANGAEA. The pipeline downloads Arctic and Antarctic datasets in bulk as zip archives directly from the Meereisportal server and ingests all buoy types described below.

Buoy IDs in the AWI network follow a consistent naming convention: a four-digit year prefix followed by a letter identifying the instrument type and a sequential number (e.g., `2024I15`, `2023T82`, `2024C04`). The type letter is used by the pipeline to automatically match each buoy to the appropriate processing configuration.

### 2.1.1 SIMB3 Seasonal Ice Mass Balance Buoys (I-series)

**Instrument:** The Seasonal Ice Mass Balance buoy, third generation (SIMB3; Planck et al., 2019), is a floating autonomous platform designed for monitoring the full thermodynamic evolution of a sea ice floe through an annual cycle. Its primary sensor is a 3.85 m Bruncin digital temperature chain (DTC) with sensors at 2 cm intervals (approximately 192 sensors), spanning the air–snow–ice–ocean column, with ±0.25°C accuracy and 0.125°C reported resolution. In addition to the temperature chain, SIMB3 carries a downward-facing ultrasonic sounder that measures the distance from the sensor mast to the snow surface, a dedicated air temperature sensor (DS18B20, ±0.5°C), a barometric pressure sensor, and a GPS receiver. AWI-processed data is typically provided at 4-hourly intervals.

**Relevance to IST validation:** The thermistor string records the full vertical temperature profile from the air through snow and ice into the ocean. Because the thermal conductivities of air, snow, ice, and water differ substantially, each material interface produces a characteristic change in the temperature gradient. The air–snow interface, which is the surface that the satellite IST retrieval observes, can be located by detecting the sharp thermal gradient transition at the top of the snowpack. The temperature at this interface — extracted from the thermistor that is closest to it — is taken as the in-situ IST measurement. This detection is performed algorithmically as described in the processing chapter (Chapter 3).

**Data files:** Each buoy contributes two pre-processed CSV files: a thermistor string file (`*TEMP_proc.csv`) containing the full temperature time series, and an auxiliary file (`*AUX_proc.csv`) containing GPS position, air temperature, barometric pressure, and the sonar snow-distance measurement.

**ID prefix:** `I` (e.g., `2024I15`)

---

### 2.1.2 SIMBA Buoys (T-series)

**Instrument:** The Snow and Ice Mass Balance Array (SIMBA; Jackson et al., 2013) is the predecessor to SIMB3, still in active use. Like SIMB3, it deploys a 5 m thermistor string with 241 sensors at 2 cm spacing using the same Maxim DS28EA00 chip. SIMBA also incorporates a resistive heating element in each sensor, enabling a secondary "heat pulse" measurement mode (SIMBA-HT) that can distinguish material boundaries even under isothermal conditions. The pipeline currently processes the passive temperature (SIMBA-ET) profiles only. Since at least 2017 the T series buoys have also had an entry for air temperature despite this not being documented. 

**Relevance to IST validation:** Identical in principle to SIMB3. The same air–snow interface detection algorithm is applied, and the interfacial temperature is used as the in-situ IST.

**Data files:** A thermistor string file (`*TEMP*raw*.csv`) and a time-series auxiliary file (`*TS.csv`) containing GPS position, air temperature, and barometric pressure.

**ID prefix:** `T` (e.g., `2023T82`)

---

### 2.1.3 Snow Buoys (S-series)

**Instrument:** The Snow Beacon (MetOcean, Halifax, Canada) is a lightweight platform designed for monitoring snow accumulation and melt on sea ice (Nicolaus et al., 2021). It carries four ultrasonic distance sensors that measure relative snow height with 1 mm precision, an air temperature sensor (YSI 44032, ±0.1°C) at 1.5 m height, and a barometric pressure sensor.

**Relevance to IST validation:** Snow buoys do not measure surface temperature directly. They contribute an air temperature record which provides useful context for interpreting IST observations. 

**Data files:** A single processed CSV file (`*raw+filterflag.csv`) containing snow depth, air temperature, pressure, and GPS position.

**ID prefix:** `S` (e.g., `2024S11`)

---

### 2.1.4 CALIB Buoys (C-series)

**Instrument:** The Compact Air-Launched Ice Beacon (CALIB) is a lightweight GPS tracker and environmental monitor. Unlike the SVP buoys, CALIBs can be air-dropped from aircraft, enabling deployment over areas inaccessible by vessel. The primary sensors are a YSI 44032 surface/body temperature sensor (±0.1°C), a barometric pressure sensor (±1.0 hPa), and a GPS receiver (±2.5 m).

**Relevance to IST validation:** Their surface/body temperature sensor measures the temperature of the buoy housing at ice level, which approximates the near-surface air temperature when the sensor is properly exposed. 

**Data files:** A single processed CSV file (`*_proc.csv`) containing temperature, pressure, and GPS position.

**ID prefix:** `C` (e.g., `2024C04`)

---

### 2.1.5 SVP Buoys (P-series)

**Instrument:** The Surface Velocity Profiler is designed for tracking sea ice drift. Its primary purpose is to measure ice motion via GPS. The measurements include a body temperature from a thermistor (±0.5°C) and a barometric pressure sensor (±1.0 hPa). The instrument can be placed directly on the ice surface or into open water. 

**Relevance to IST validation:** Their body temperature is a proxy for near-surface air temperature but with lower accuracy than Snow Buoys, as the sensor is not thermally isolated from the buoy body. SVPs are nonetheless valuable because of their large numbers providing dense spatial sampling of surface conditions and ice drift.

**Data files:** A single processed CSV file (`*_proc.csv`) containing temperature, pressure, and GPS position.

**ID prefix:** `P` (e.g., `2024P17`)

---

### 2.1.6 Weather Buoys / Automatic Weather Stations (A-series)

**Instrument:** The A-series buoys in the AWI network are Automatic Weather Stations (AWS). They carry a comprehensive suite of sensors mounted on a 2 m mast: air temperature (Campbell Scientific PT100/3, ±0.1°C), barometric pressure (±1.0 hPa), wind speed and direction (±0.3 m/s and ±3°).

**Relevance to IST validation:** AWS buoys do not measure skin temperature, but they offer the most complete surface meteorological record of any instrument type in the dataset. The wind observations are valuable for identifying periods of strong turbulent mixing that reduce the thermal stratification near the surface. Air temperature is quality-controlled using the same `SnowQualityControl` module as snow buoys (Flag 0 or 2; see Section 4.5). Unfortunately there are very few of these buoys deployed.

**Data files:** A single processed CSV file (`*raw+filterflag.csv`). Different hardware variants of the AWS unit use different column names for air temperature (`temperature_air`, `temperature_air_2m`, or `temperature_air_1m`). The pipeline tries each name in that order and uses the first one present.

**ID prefix:** `A`

---

## 2.2 SvalMIZ OpenMetBuoy Data

 The SvalMIZ-25 campaign was conducted in April–May 2025 aboard the Norwegian Coast Guard vessel KV Svalbard, during which 21 buoys were deployed north of the Svalbard Archipelago (Müller et al., 2025).

**Instrument:** The standard OMB measures ice drift (GPS, 30-minute interval) and 1-D wave energy spectra (motion sensor with on-board Kalman filtering). For the SvalMIZ campaigns, the OMB is augmented with a meteorological mast assembly carrying:

- A **1 m temperature mast** with a DS18B20 digital temperature sensor housed in a Rikasensor RK95-02B radiation shield, measuring air temperature at 1 m above the ice surface. Sensors are individually calibrated against a PT-100 reference at three temperature points prior to deployment.
- An **MLX90614 infrared thermometer** with a long-wave bandpass optical filter (5.5–14 µm), pointed downward to measure the radiometric surface temperature of the snow or ice beneath the buoy. Sixty individual readings are averaged over 60 seconds and transmitted as a single observation, reducing measurement noise from ~0.4°C (single reading standard deviation) to a much lower effective value. The sensor has been evaluated against a professional Campbell IR120 reference sensor and shows a mean deviation of 0.16°C.
- Two **in-ice temperature sensors** at the snow–ice interface and 0.3 m depth into the ice.


**Relevance to IST validation:** The MLX90614 IR sensor provides a direct radiometric measurement of snow surface temperature that is physically analogous to what the satellite IST algorithm observes from space — both measure upwelling longwave thermal emission from the surface within overlapping wavelength bands. This makes SvalMIZ OMB data the most direct validation reference available in the dataset, requiring no algorithmic derivation of skin temperature. There is however some concern related to icing occuring on the IR sensor which leads to measurments tranding towards the air temperature adjacent to the frost on the sensor.

**Data format:** Calibrated, quality-controlled data from the SvalMIZ-25 campaign are distributed as a multi-trajectory NetCDF file (`2025_KVS_deployment_hourly_MIP.nc`), containing one trajectory per buoy with hourly-averaged observations of surface temperature, air temperature, GPS position, and ancillary wave parameters.

---

## Summary

| Buoy type | ID prefix | Skin temp (Ts) | Air temp (T2m) | Other parameters | Data source |
|---|---|---|---|---|---|
| SIMB3 | I | Derived (thermistor) | Yes | Pressure, snow depth | AWI Meereisportal |
| Legacy SIMBA | T | Derived (thermistor) | Yes | Pressure | AWI Meereisportal |
| Snow Buoy | S | No | Yes | Pressure, snow depth | AWI Meereisportal |
| CALIB | C | No | Yes (body) | Pressure | AWI Meereisportal |
| SVP | P | No | Yes (body) | Pressure | AWI Meereisportal |
| Weather Buoy (BAS AWS) | A | No | Yes | Pressure, wind | AWI Meereisportal |
| SvalMIZ OMB | — | Yes (IR radiometer) | Yes | Wave spectra | MET Norway (NetCDF) |

---

## 2.4 Potential Future Data Sources

The following sources have not been integrated into the pipeline but may be of interest for extending the validation dataset.

**International Arctic Buoy Programme (IABP)** — A multinational programme that maintains a network of drifting buoys across the Arctic Ocean, with limited Antarctic coverage. Publicly available data include air temperature, sea-level pressure, and a "surface" temperature (typically from an above-ice sensor), but no thermistor string measurements. Data are available at https://iabp.apl.uw.edu/data.html.

**Antarctic Meteorological Research and Data Center (AMRDC)** — Distributes observations from a network of Automatic Weather Stations (AWS) operating across the Antarctic continent and ice shelves, including air temperature, pressure, wind speed, and humidity. The stations are fixed land-based installations rather than drifting sea ice platforms, which makes them better suited to validating IST over land ice and ice shelves than over sea ice. Data are available at https://amrdc.ssec.wisc.edu/.

---

## References

Grosfeld, K., Treffeisen, R., Asseng, J., Bartsch, A., Bräuer, B., Fritzsch, B., Gerdes, R., Hendricks, S., Hiller, W., Heygster, G., Krumpen, T., Lemke, P., Melsheimer, C., Nicolaus, M., Ricker, R., and Weigelt, M. (2016). Online sea-ice knowledge and data platform <www.meereisportal.de>. *Polarforschung*, 85(2), 143–155. https://doi.org/10.2312/polfor.2016.011

Jackson, K., Wilkinson, J., Maksym, T., Meldrum, D., Beckers, J., Haas, C., and Mackenzie, D. (2013). A novel and low-cost sea ice mass balance buoy. *Journal of Atmospheric and Oceanic Technology*, 30, 2676–2688. https://doi.org/10.1175/JTECH-D-13-00058.1

Müller, M., Rabault, J., Palerme, C., and Tjernström, J. (2025). Cruise Report — KV Svalbard 25 April–11 May 2025: SvalMIZ-25 Svalbard Marginal Ice Zone 2025 Campaign. Norwegian Meteorological Institute.

Nicolaus, M., Hoppmann, M., Arndt, S., Hendricks, S., Katlein, C., Nicolaus, A., Rossmann, L., Schiller, M., and Schwegmann, S. (2021). Snow depth and air temperature seasonality on sea ice derived from snow buoy measurements. *Frontiers in Marine Science*, 8, 655446. https://doi.org/10.3389/fmars.2021.655446

Planck, C. J., Whitlock, J., Polashenski, C., and Perovich, D. (2019). The evolution of the seasonal ice mass balance buoy. *Cold Regions Science and Technology*, 165, 102792. https://doi.org/10.1016/j.coldregions.2019.102792

Rabault, J., Sutherland, G., Jensen, A., Christensen, K. H., and Marchenko, A. (2021). OpenMetBuoy-v2021: An easy-to-build, affordable, customizable, open-source instrument for oceanographic measurements of drift and waves in sea ice and the open ocean. *Geosciences*, 11(7), 280. https://doi.org/10.3390/geosciences11070280
