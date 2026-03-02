# 1. Introduction

## 1.1 Background and Objectives

The OSI SAF High Latitude IST product retrieves radiometric skin temperature of the sea ice surface from AVHRR/3 and VIIRS infrared brightness temperatures, validated operationally through satellite–in-situ colocation. A key challenge is representativeness: most available drifting buoy measurements are 2 m air temperature, which diverges from the radiometric skin temperature by 3–5 K under calm, clear conditions and cannot serve as a direct validation reference (Dybkjaer & Eastwood, 2016). This pipeline processes AWI Meereisportal and SvalMIZ OpenMetBuoy data (Arctic and Antarctic, 2024–2025) to assemble a quality-controlled dataset specifically targeting this gap.

Two measurement objectives are served: **skin temperature (Ts)**, extracted algorithmically from thermistor string profiles (SIMB3 and SIMBA; Chapter 3) and measured directly by SvalMIZ OMB infrared sensors; and **near-surface air temperature (T2m)** from all other instrument types, providing spatial density and atmospheric context. QC is applied independently to each objective (Chapter 4).

## 1.2 Quality Philosophy

The QC criteria are calibrated to be conservative. When there is uncertainty about whether a given observation is reliable, the preference is to flag it rather than to pass it. A reduction in data volume is an acceptable cost if it comes with a corresponding improvement in the confidence that the retained observations are accurate. The QC flag scheme uses three levels (0 = Good, 1 = Suspect, 2 = Invalid). The export filter is configurable via `export_flags` in `buoy_config.yaml`; by default all flags (including -9, meaning no QC was performed) are exported so that the downstream user can apply their own filter.

This approach is particularly important for thermistor string buoys, where the skin temperature estimate is derived from an algorithm rather than measured directly. The algorithm can fail or return low-confidence results under isothermal conditions, near the melting point, or when the sensor string has partially flooded. The QC module is designed to detect and flag these cases.

## 1.3 Output and Downstream Use

The pipeline produces a fixed-width ASCII dataset formatted to work with exisitng systems, with one record per buoy per timestep containing: station identifier, timestamp, geographic position, skin temperature (Ts), near-surface air temperature (T2m), and quality flags for each temperature field.

This dataset is intended for ingestion into a separate colocalization workflow, which matches each in-situ observation against the nearest satellite retrieval in space and time and computes validation statistics.

---

## References

Dybkjaer, G., Eastwood, S., and Howe, E. (2018). *OSI SAF Product User Manual for the CDOP3 High Latitude L2 Sea and Sea Ice Surface Temperature Product (OSI-205-a/b)*, v1.3. EUMETSAT OSI SAF.

Dybkjaer, G., and Eastwood, S. (2016). *Validation Report for the CDOP2 High Latitude L2 Sea and Sea Ice Surface Temperature Product (OSI-205)*, v1.1. EUMETSAT OSI SAF.
