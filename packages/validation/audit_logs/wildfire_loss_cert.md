# Audit Certificate — `wildfire_loss` v0.1.0

**Execution ID:** `3b8b4377-8496-4066-b721-1b9ce45dbc2c`  
**Timestamp:** 2026-05-15T22:30:26.891326+00:00  
**Methodology doc version:** `89caa222b6b059ffb2d64aa66df6259f43fbe0fea8ba290fa894c99046004881`  
**Duration:** 66693.7 ms  

## Inputs
```json
{
  "vulnerability_model_run_id": "ca43038e-04e9-43ee-b800-46455b60dc3e",
  "vulnerability_methodology_hash": "10e96fde8758c088495cdc1be9722c9239839aacdcfd68d956a3f564565c35cc",
  "predictors": [
    "burn_probability",
    "distance_to_fuel_m",
    "canopy_cover_100m",
    "slope_degrees",
    "is_res1"
  ],
  "coefficients": {
    "const": 0.9304137982718326,
    "burn_probability": -130.75537981077997,
    "distance_to_fuel_m": 0.01919159438809745,
    "canopy_cover_100m": -0.023897246113682814,
    "slope_degrees": 0.06880940046522348,
    "is_res1": 0.24504502964155503
  },
  "return_periods_yr": [
    10,
    25,
    50,
    100,
    250,
    500,
    1000
  ]
}
```

## Scored output
```json
{
  "n_structures": 185300,
  "total_eal": 47586439.26203247,
  "mean_eal": 256.8075513331488,
  "median_eal": 6.157780667083532,
  "ep_curve": [
    {
      "return_period_years": 10,
      "annual_freq_exceed": 0.1,
      "loss_amount": 10377837.913928626
    },
    {
      "return_period_years": 25,
      "annual_freq_exceed": 0.04,
      "loss_amount": 13752257.863926966
    },
    {
      "return_period_years": 50,
      "annual_freq_exceed": 0.02,
      "loss_amount": 16858049.261225805
    },
    {
      "return_period_years": 100,
      "annual_freq_exceed": 0.01,
      "loss_amount": 20944229.16986009
    },
    {
      "return_period_years": 250,
      "annual_freq_exceed": 0.004,
      "loss_amount": 27979501.854048662
    },
    {
      "return_period_years": 500,
      "annual_freq_exceed": 0.002,
      "loss_amount": 42388006.40479162
    },
    {
      "return_period_years": 1000,
      "annual_freq_exceed": 0.001,
      "loss_amount": 44322034.699454404
    }
  ]
}
```

## Data layers consulted

- `wildfire_nsi_structures`

## Queries executed (2)

1. (4462.2 ms, 185300 rows) layers=['wildfire_nsi_structures']
   ```sql
   SELECT     fd_id,     occtype,     st_damcat,     val_struct,     burn_probability,     distance_to_fuel_m,     canopy_cover_100m,     slope_degrees,     cbfips,     ST_X(geometry) AS lng,     ST_Y(geometry) AS lat FROM wildfire_nsi_structu …
   ```
2. (18707.5 ms, 185300 rows) layers=['wildfire_nsi_structures']
   ```sql
   UPDATE wildfire_nsi_structures SET expected_annual_loss = … (bulk via temp table)
   ```

## Attestation

This certificate records the exact inputs, SQL executed, data layers consulted, and scored output for a single module execution. A compliance reviewer can re-run the recorded SQL against the same database snapshot to reproduce the raw inputs to the scoring function, then apply the methodology document (`89caa222b6b059ffb2d64aa66df6259f43fbe0fea8ba290fa894c99046004881`) to reproduce the output deterministically.