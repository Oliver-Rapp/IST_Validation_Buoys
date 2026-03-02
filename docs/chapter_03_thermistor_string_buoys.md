# 3. Thermistor String Buoys: Interface Detection and Surface Temperature Retrieval

This chapter covers the two thermistor string buoy types processed by the pipeline — the SIMBA (T-series) and the SIMB3 (I-series) — and describes the physical and algorithmic basis for extracting a surface temperature measurement from their data. The quality control applied to these measurements is covered separately in Chapter 4.

---

## 3.1 Instruments

Both instruments are described in full in Section 2.1. For the interface detection algorithm, both use the same Maxim DS28EA00 sensor chain at 2 cm spacing and the same passive temperature measurement principle, so their detection algorithms are identical (Section 3.3).

| | SIMBA (T-series) | SIMB3 (I-series) |
|---|---|---|
| String length | 5 m, 241 sensors | 3.85 m, ~192 sensors |
| Ultrasonic sounder | No | Yes |
| Dedicated air temp sensor | From ~2017 onwards | Yes (always) |
| Primary data file | `*TEMP*raw*.csv` | `*TEMP_proc.csv` |
| Auxiliary data file | `*TS.csv` | `*AUX_proc.csv` |

---

## 3.2 Physical Basis for Interface Detection

### 3.2.1 Thermal Structure of the Vertical Column

The algorithm relies on the thermal conductivity contrast between air (∼0.024 W m⁻¹ K⁻¹), snow (0.1–0.3), and sea ice (1.9–2.3): sensors in snow exhibit inter-sensor temperature gradients roughly 7–23× larger than sensors in ice, creating a characteristic layered structure in the vertical profile. Plotting the absolute finite-difference gradient $|T_{i+1} - T_i|$ along the string identifies each material interface as a step change in gradient magnitude. The challenge is that sensors resolve temperature at 0.0625°C and air-side sensors are subject to environmental noise, so a physically grounded threshold is needed to distinguish a genuine snow signal from quantisation noise.

---

### 3.2.2 Detection Threshold

Following Liao et al. (2019), the pipeline uses a fixed gradient threshold of **0.4375°C** to identify sensors embedded in snow. This value is derived from the minimum thermal conductivity ratio $k_i/k_s \geq 7$ (sea ice vs. snow; Pringle et al., 2007; Sturm et al., 1997) and the 0.0625°C resolution of the DS28EA00 sensor: the minimum snow-side inter-sensor gradient (7 × 0.0625°C = 0.4375°C) exceeds the maximum ice-side gradient (0.1875°C). It is configurable as `threshold_grad` in `buoy_config.yaml`.

> **Note on applicability.** The threshold loses reliability when the snowpack becomes isothermal or wet during melt conditions (Section 3.5).

---

## 3.3 Interface Detection Algorithm

### 3.3.1 Leading Edge Algorithm (Pipeline Default)

The pipeline uses a leading edge algorithm to locate the air–snow interface. It is inspired by the maximum gradient peak approach of Liao et al. (2019), but refines it by backtracking upward from the gradient peak to the point where the gradient first rises above the near-zero air-side baseline. This places the detected interface at the actual top of the snowpack rather than somewhere in its interior.

**Algorithm (implemented in `detect_leading_edge` in `lib/simba_algo.py`):**

1. Compute the absolute finite-difference gradient along the profile: $G_i = |T_{i+1} - T_i|$ for $i = 0, \ldots, N-2$.
2. Zero the first five gradient values ($i < 5$) to exclude spurious spikes at the very top of the string where exposed air-side sensors can produce erroneous gradients (following Liao et al., 2019).
3. Find the peak index $p$ and peak value $G_p = \max_i G_i$.
4. If $G_p < 0.4375$°C (no snow signal detectable): carry the previous time step's result forward.
5. Define the edge threshold: $G_\text{edge} = \text{edge\_ratio} \times G_p$, where `edge_ratio = 0.2` in the default configuration.
6. Examine the gradient profile from the string top up to (but not including) the peak: $G_0, G_1, \ldots, G_{p-1}$.
7. Find all indices in this segment where $G_i < G_\text{edge}$. The last such index defines the interface: $e = \text{last\_low\_grad\_index} + 1$.


**Physical interpretation.** The gradient in air is small. Moving down through the snowpack, the gradient rises sharply at the air–snow interface. The leading edge algorithm identifies the sensor position where the gradient begins to rise. The themperature of this sensor is used as the surface temperature.

**Choice of `edge_ratio`.** The value 0.2 means the algorithm searches for where the gradient exceeds 20% of its peak value. A smaller value locates the surface higher while a larger value converges toward the gradient peak position. The value 0.2 was chosen empirically and can be tuned in `buoy_config.yaml` under `algorithm.params.edge_ratio` for each buoy type.

---

### 3.3.2 Implementation Details and Constraints

**Top exclusion zone.** The first 5 sensors (0–10 cm from the string top) are excluded from the gradient search. Sensors at the very top of the string seem to have significant noise and produce misleading thermal gradient numbers. The number of excluded sensors is hard-coded, but easy to change in the code.

**Upper search limit.** The gradient search is also limited to sensors with index less than 150 (i.e., depths shallower than 3 m from the string top). The air–snow interface is always in the upper portion of the string.

**Temporal persistence (forward fill).** When detection fails — either because the maximum gradient is below the threshold or because the profile is entirely isothermal — the interface position from the previous time step is carried forward. On a melting floe this can produce long periods of constant interface position. **Forward-filled interface positions are automatically flagged as 1 (suspect/non-representative) in the QC system** (see Chapter 4), because they represent times when the gradient signal was too weak for fresh detection. Such periods are identifiable in the QC output by a near-zero peak gradient signal (`peak_strength` in `df_qc`).

---

## 3.4 Surface Temperature Extraction

### 3.4.1 From Interface Index to Temperature

Once the interface sensor index $e$ has been determined, the in-situ IST proxy is taken as the temperature of the sensor at position $e - 1$:

$$T_\text{surface} = T[e - 1]$$

This is the deepest sensor that the algorithm classifies as being in air — the last sensor above the snow surface. It represents the temperature at (or fractionally above) the air–snow interface.

The `Ts` value written to the ASCII output is extracted in `ist_buoy_validation_data.py`, using the same interface index and the $e - 1$ convention.
---

### 3.4.2 Air Temperature

For both SIMB3 and SIMBA (T-series), the air temperature written to the output is taken from the dedicated near-surface sensor in the auxiliary data file rather than from the thermistor string. For SIMB3 this is the `temperature_air` column in the `*AUX_proc.csv` file (a separate DS18B20 sensor). For SIMBA it is the `air temperature` column in the `*TS.csv` time-series file.

This dedicated sensor is mounted near the surface, typically in a radiation shield, and is less susceptible to the solar heating and boundary-layer noise that can affect string sensors exposed in air. Documentation on the SIMBA air temperature sensors was lacking.

---

## 3.5 Limitations and Failure Modes

- **Warm/isothermal conditions:** When air temperature approaches 0°C, the snowpack gradient collapses below the 0.4375°C threshold and the algorithm falls back to temporal persistence (Section 3.3.2), which can freeze the detected interface position for weeks during summer melt. The QC system flags these forward-filled positions via the `peak_strength` check (Chapter 4).
- **Insufficient air exposure:** At least 10 cm of string (5 sensors, the top exclusion zone) must remain above the snow surface for detection to work. Rapid snowfall or wind redistribution can bury the string entirely.

---

## 3.6 Summary

The IST measurement extracted from a SIMBA or SIMB3 buoy is the temperature of the sensor index determined by the leading edge algorithm to be the last sensor in air above the snow surface. The physical basis for locating this sensor rests on the large thermal conductivity contrast between snow and ice, which produces a step change in the inter-sensor temperature gradient at the 0.4375°C threshold derived by Liao et al. (2019). The leading edge algorithm refines the Liao approach by backtracking from the gradient peak to the onset of the snow-layer signal, placing the detected interface closer to the true air–snow boundary.

---

## References

Jackson, K., Wilkinson, J., Maksym, T., Meldrum, D., Beckers, J., Haas, C., and Mackenzie, D. (2013). A novel and low-cost sea ice mass balance buoy. *Journal of Atmospheric and Oceanic Technology*, 30, 2676–2688. https://doi.org/10.1175/JTECH-D-13-00058.1

Liao, Z., Cheng, B., Zhao, J., Vihma, T., Jackson, K., Yang, Q., Yang, Y., Zhang, L., Li, Z., Qiu, Y., and Cheng, X. (2019). Snow depth and ice thickness derived from SIMBA ice mass balance buoy data using an automated algorithm. *International Journal of Digital Earth*, 12(8), 962–979. https://doi.org/10.1080/17538947.2018.1545877

Merkouriadi, I., Cheng, B., Graham, R. M., Rösel, A., and Granskog, M. A. (2017). Critical role of snow on sea ice growth in the Atlantic sector of the Arctic Ocean. *Geophysical Research Letters*, 44(20), 10479–10485. https://doi.org/10.1002/2017GL075494

Planck, C. J., Whitlock, J., Polashenski, C., and Perovich, D. (2019). The evolution of the seasonal ice mass balance buoy. *Cold Regions Science and Technology*, 165, 102792. https://doi.org/10.1016/j.coldregions.2019.102792

Preußer, A., Nicolaus, M., and Hoppmann, M. (2025). Snow depth, sea ice thickness and interface temperatures derived from measurements of SIMBA buoy 2020T78. *PANGAEA*. https://doi.org/10.1594/PANGAEA.973358

Pringle, D. J., Eicken, H., Trodahl, H. J., and Backstrom, L. G. E. (2007). Thermal conductivity of landfast Antarctic and Arctic sea ice. *Journal of Geophysical Research*, 112, C04017. https://doi.org/10.1029/2006JC003641

Provost, C., Sennéchael, N., Miguet, J., Itkin, P., Rösel, A., Koenig, Z., Villacieros-Robineau, N., and Granskog, M. A. (2017). Observations of flooding and snow-ice formation in a thinner Arctic sea-ice regime during the N-ICE2015 campaign. *Journal of Geophysical Research: Oceans*, 122, 7115–7134. https://doi.org/10.1002/2016JC012011

Sturm, M., Holmgren, J., König, M., and Morris, K. (1997). The thermal conductivity of seasonal snow. *Journal of Glaciology*, 43, 26–40.
