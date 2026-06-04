# Exclusion Diagnosis — Excluded EIA Installations (Step 1)

Source: `docs/validation/raw/test1_solar_multistate.json` — 12 EIA installations rated Excluded.

| EIA Plant | State | MW | Criterion | Specific Trigger | Assessment |
|---|---|---|---|---|---|
| Prospero Solar II | TX | 250.0 | excl_protected | GAP 4 · State Resource Management Area (State Land Board) | FALSE POSITIVE (GAP 3-4 — multi-use, solar often permitted) |
| Pima Community College - East Campus | AZ | 1.3 | excl_urban | NLCD 24 (Developed, High Intensity) | TRUE (NLCD 23-24, dense development) |
| AZ State University - Tempe Campus Solar | AZ | 0.1 | excl_urban | NLCD 23 (Developed, Medium Intensity) | TRUE (NLCD 23-24, dense development) |
| Mohave Electric at Fort Mohave | AZ | 4.4 | excl_urban | NLCD 23 (Developed, Medium Intensity) | TRUE (NLCD 23-24, dense development) |
| Mohave Electric at Fort Mohave | AZ | 4.4 | excl_flood | FEMA zone AO | FALSE POSITIVE (A/AE — solar permitted w/ elevated mounting) |
| Arizona Western College PV | AZ | 1.0 | excl_urban | NLCD 24 (Developed, High Intensity) | TRUE (NLCD 23-24, dense development) |
| Eagle Shadow Mountain Solar Farm | NV | 300.0 | excl_protected | GAP 4 · Native American Land Area (American Indian Lands) | FALSE POSITIVE (GAP 3-4 — multi-use, solar often permitted) |
| Boulder Solar Power, LLC | NV | 100.0 | excl_protected | GAP 3 · Area of Critical Environmental Concern (Bureau of Land Management) | FALSE POSITIVE (GAP 3-4 — multi-use, solar often permitted) |
| Tungsten Mountain | NV | 5.0 | excl_protected | GAP 3 · National Public Lands (Bureau of Land Management) | FALSE POSITIVE (GAP 3-4 — multi-use, solar often permitted) |
| Tungsten Mountain | NV | 7.3 | excl_protected | GAP 3 · National Public Lands (Bureau of Land Management) | FALSE POSITIVE (GAP 3-4 — multi-use, solar often permitted) |
| Silver State Solar Power South | NV | 35.7 | excl_protected | GAP 3 · Area of Critical Environmental Concern (Bureau of Land Management) | FALSE POSITIVE (GAP 3-4 — multi-use, solar often permitted) |
| Coral Farms Solar Energy Center | FL | 74.5 | excl_urban | NLCD 23 (Developed, Medium Intensity) | TRUE (NLCD 23-24, dense development) |
| Coral Farms Solar Energy Center | FL | 74.5 | excl_flood | FEMA zone A | FALSE POSITIVE (A/AE — solar permitted w/ elevated mounting) |
| Babcock Solar Energy Center Hybrid | FL | 74.5 | excl_wetlands | {"note": "see scoring basis (NWI/SSURGO)"} | REVIEW |
