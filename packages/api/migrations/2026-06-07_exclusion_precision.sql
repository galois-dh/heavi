-- Exclusion precision refinements (Heavi Exclusion Precision Spec, Step 4).
--
-- Diagnosis of the 12 Excluded EIA installations in Test 1 found the exclusion
-- logic was too aggressive: 6 of 6 protected-area exclusions were GAP 3-4 land
-- (BLM/state/tribal multi-use, where major US solar farms operate), and both
-- flood exclusions were A-type 100-year floodplains (solar operates there with
-- elevated mounting). This migration aligns methodology_criteria with the
-- refined logic in solar_scoring_v2.py. The refinements reflect real-world
-- permitting practice, not a desire to move a metric.

-- 1) Protected areas — hard-exclude GAP 1-2 only; GAP 3-4 become advisory.
UPDATE methodology_criteria SET
    exclusion_threshold = 'GAP 1-2 overlap only (GAP 3-4 → advisory, not exclusion)',
    exclusion_rationale = (
        'Per USGS PAD-US documentation, GAP 1-2 lands are managed for biodiversity '
        'with development precluded (wilderness, nature preserves, national parks). '
        'GAP 3-4 lands allow multiple uses including energy development with '
        'appropriate permitting — many of the largest US solar installations exist '
        'on BLM (GAP 3) land. Hard exclusion is therefore limited to GAP 1-2.'
    )
WHERE workflow_type='solar_siting' AND criterion_id='excl_protected';

-- 2) Developed land — hard-exclude NLCD 23-24 only; 21-22 become advisory.
UPDATE methodology_criteria SET
    exclusion_threshold = 'NLCD 23-24 only (21-22 → advisory, not exclusion)',
    exclusion_rationale = (
        'Hernandez et al. (2015) excluded developed land but did not differentiate '
        'by intensity class. NLCD Class 21 (Developed, Open Space) includes land '
        'uses compatible with solar (parks, golf courses, institutional campuses) '
        'and Class 22 (Low Intensity) is not strictly incompatible. Hard exclusion '
        'is limited to Class 23-24 (medium/high-intensity development), which is '
        'incompatible with utility-scale ground-mount solar.'
    )
WHERE workflow_type='solar_siting' AND criterion_id='excl_urban';

-- 3) Steep slope — raise threshold 15% → 20%.
UPDATE methodology_criteria SET
    exclusion_threshold = 'slope > 20 % (raised from 15 %)',
    exclusion_rationale = (
        'Literature threshold ranges from 3 % (Hernandez et al. 2015, conservative) '
        'to 20° (~36 %, some international studies). 20 % (~11.3°) is moderate and '
        'accommodates single-axis tracker installations on rolling terrain, which '
        'are common in practice.'
    )
WHERE workflow_type='solar_siting' AND criterion_id='excl_steep';

-- 4) Flood — convert from hard exclusion to a SCORED penalty criterion.
--    V zones still hard-exclude (handled in scoring via the basis); A/AE take a
--    scored penalty. As a scored criterion it leaves the exclusion-factor
--    denominator (confidence logic) and joins the weighted composite at 0.05.
UPDATE methodology_criteria SET
    criterion_type      = 'scored',
    criterion_name      = 'Flood Zone (scored penalty)',
    weight_default      = 0.05,
    weight_min          = 0.03,
    weight_max          = 0.07,
    weight_rationale    = (
        'Converted from hard exclusion to a scored penalty (weight 0.05). Solar PV '
        'installations can operate in SFHA zones with elevated mounting; FEMA '
        'permits development in A/AE zones with appropriate floodplain development '
        'permits. Only V zones (coastal high hazard with wave action) remain '
        'incompatible with ground-mount solar and are retained as a hard exclusion. '
        'A/AE zones score 0.35 (penalty), X/outside-SFHA score 1.0.'
    ),
    exclusion_threshold = 'V zones only remain a hard exclusion; A/AE → scored penalty',
    exclusion_rationale = (
        'Solar PV can operate in Special Flood Hazard Areas with elevated mounting. '
        'FEMA permits development in A/AE zones with floodplain development permits; '
        'these are now a scored penalty rather than a fatal flaw. Only V zones '
        '(coastal high hazard, wave action) are incompatible with ground-mount solar.'
    )
WHERE workflow_type='solar_siting' AND criterion_id='excl_flood';
