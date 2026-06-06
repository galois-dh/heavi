# Heavi Energy — Precision Metric Framework

**Status:** Defined, pending design-partner pilot data · June 2026

---

## 1. Why precision, and why it is not yet measured

Heavi's published validation measures **recall**:

> *Of the real solar installations that developers actually built, what fraction does the
> tool score High?*

Across 10 states, the answer is **71% among greenfield-eligible installations**, with
positive discrimination versus random rural land in all 10 states. Recall answers "does the
tool recognize good sites?" — and the validation says yes.

But recall is the wrong question for a developer deciding whether to rely on the tool. The
developer's question is **precision**:

> *Of the parcels the tool scores High, what fraction would I actually want to develop?*

Recall can be measured against public ground truth (EIA Form 860). **Precision cannot** —
there is no public dataset of "parcels a developer reviewed and rejected." Measuring
precision requires a domain expert reviewing Heavi's output and judging each High-scored
parcel. That expert is the design partner. This document defines the precision metric **now**
so it is ready to measure the moment pilots begin, with no methodology debate mid-pilot.

---

## 2. Definition

```
                 High-scored sites that pass developer review
   Precision  =  ─────────────────────────────────────────────
                          total High-scored sites
```

A High-scored parcel **passes developer review** if the design partner's site-development
team classifies it as either:

- **Would pursue** — the parcel is genuinely suitable for development consideration; the
  team would advance it in their own pipeline.
- **Already known** — the parcel is already in the developer's pipeline. This *validates*
  the tool: it independently surfaced a site the experts had already chosen.

A High-scored parcel **fails developer review** if classified as:

- **Would not pursue** — the parcel has a real flaw the tool did not catch. Examples: wrong
  zoning, a terrain problem invisible at 10 m DEM resolution, known community opposition, a
  grid constraint not reflected in queue data, land already optioned by a competitor, or a
  parcel-specific title/access issue.

A **false positive** is a "would not pursue." Precision is the complement of the
false-positive rate among High-scored parcels.

---

## 3. Why "already known" counts as a pass

A developer's first reaction to a tool surfacing a site they already hold is "it told me
nothing new." The opposite is true: **independent rediscovery of an expert-selected site is
the strongest possible confirmation that the scoring tracks real-world developer judgment.**
A tool that only ever surfaced novel sites — and never the ones experts had already
chosen — would be the suspicious one. Counting "already known" as a pass measures whether
the tool *agrees with experts*, which is exactly what a screening tool should do.

We report both figures so a partner can see the split:

- **Precision (agreement):** (would-pursue + already-known) / total High
- **Net-new precision:** would-pursue / total High — the rate of *novel* good sites

---

## 4. Measurement Protocol

A single pilot run, repeatable per partner:

1. **Partner provides 50 candidate parcels** from their own screening pipeline (coordinates
   or addresses; any stage of their funnel).
2. **Heavi scores all 50** through the production solar-suitability platform, with full
   per-criterion breakdown, confidence, and interconnection context.
3. **Heavi identifies the top 15 as High** (rank by score; in practice the High band is
   ≥0.70, but we fix N = 15 so precision is measured on a consistent denominator).
4. **The partner's team reviews the 15 High-scored parcels** against their own development
   criteria — the same review they would give any candidate site.
5. **The partner classifies each** as would-pursue / would-not-pursue / already-known.
6. **Compute precision** = (would-pursue + already-known) / 15.

Every "would not pursue" is logged with a **reason code** (zoning, terrain, grid,
community, land-control, other). These reasons are the most valuable output of the pilot:
they tell us which real-world constraint the tool should ingest next.

---

## 5. Target and interpretation

**Target: ≥70% precision** — at least **10 of 15** High-scored parcels pass developer
review.

| Precision | Interpretation |
|---|---|
| ≥ 80% | Strong — the High band is reliable enough to drive real prioritization |
| 70–79% | Target met — useful screening; review the failure reasons for the next data source |
| 50–69% | Marginal — the tool narrows the field but the High band needs another constraint layer |
| < 50% | The High band is not yet trustworthy for this partner's geography/segment; investigate |

A precision below target is **not a failure of the pilot** — it is a prioritized backlog.
If three of five "would not pursue" parcels failed on zoning, the next engineering
investment is a parcel-level zoning layer, and the pilot has paid for itself by saying so.

---

## 6. Relationship to the recall validation

The two metrics are complementary and should always be reported together:

| | Question | Ground truth | Status |
|---|---|---|---|
| **Recall** | Does the tool recognize good sites? | EIA Form 860 (public) | Measured: 71% greenfield-eligible |
| **Precision** | Are the tool's good sites actually good? | Design-partner expert review | Defined here; measured in pilots |

A tool can have high recall and low precision (it finds the good sites but also flags many
bad ones) or the reverse. A screening tool that saves a developer time needs **both**: high
recall so it does not miss opportunities, and high precision so its shortlist is worth
reviewing. The recall result is in hand; this framework closes the loop on precision.

---

## 7. Coverage (a secondary pilot metric)

Alongside precision, pilots measure **coverage**:

```
                 Developer-selected parcels that Heavi also scores High
   Coverage  =  ────────────────────────────────────────────────────────
                        total developer-selected parcels
```

If the developer independently advanced 20 of their 50 parcels, coverage asks how many of
those 20 Heavi also placed in its High band. **Target: ≥80% coverage.** Coverage is recall
measured on the partner's own ground truth rather than EIA's, and it is the metric most
likely to convince a skeptical buyer, because it is *their* sites.

---

*Heavi Energy. This framework is published in advance of pilot data so that precision is
measured against a fixed, agreed definition. Results will be reported per partner, with
failure-reason codes, as pilots complete.*
