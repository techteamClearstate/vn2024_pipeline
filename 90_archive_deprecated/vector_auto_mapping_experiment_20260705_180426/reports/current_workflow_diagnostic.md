# Current Workflow Diagnostic

## Current Pipeline Summary

The current surgical import workflow maps noisy shipment rows to the latest surgical master reference. The local repository contains a staged pipeline: extraction, deterministic/fuzzy matching, reference-compliant mapping, scope review, dashboard rebuild, and publication of one current workbook per country/year.

Current input evidence used by the workflow includes shipment description fields such as `Detailed_Product`, importer/exporter/manufacturer party text, HS code, country/year metadata, quantity, value, and existing mapped fields where available. Current output fields include canonical segment, sub-segment, product, manufacturer/player, family/model, confidence/status fields, `Dash_Include`, QA status, and review/exclusion routing.

The approved reference is `reference/brand_model/Surg_Brand_model_list_Master_03July26.xlsx`. The `Updated` sheet is the latest full surgical reference and `Updated (excl. generic)` is the stricter no-generic reference used to prevent generic family/model tokens from driving trusted mappings.

## Current Mapping Methods

- Exact and prefix family matching through reference-derived tuples.
- Manufacturer and historical-name alias matching.
- Product/category matching with HS and category gates.
- Fuzzy and lexical matching for noisy product/family descriptions.
- Scope exclusion rules for dental, veterinary, cosmetic/aesthetic, lab/IVD, imaging-only, ophthalmic-only, donation/humanitarian, non-surgical capital equipment, and general supplies.
- Manual review routing through `Review_Queue`, `Extended_Surgical_Decision`, `Alias_Update_Request`, and `Reference_Update_Request`.
- Dashboard rebuild only from reference-valid, trusted rows.

## Strengths

- The latest master reference remains the source of truth for trusted dashboard inclusion.
- Trusted rows already validate against full family keys or category keys.
- Generic-token and exclusion conflicts are increasingly visible in the output workbooks.
- The six-file publication process keeps one current workbook per country/year in the shared mapped-results folder.
- Existing `Candidate_Table` and QA tabs provide a foundation for a more auditable retrieval experiment.

## Weaknesses

- Recall is still limited by missing aliases, manufacturer-only rows, unspecified categories, and reference gaps.
- Review queues are large because candidate evidence is not fully decomposed into product, family, manufacturer, exclusion, and retrieval-method scores.
- Fuzzy or semantic evidence can be hard to audit unless every candidate and negative signal is retained.
- Excluded/unmapped rows may contain valid surgical-looking clusters that should be routed to review or new-target discovery rather than silently dropped.
- There is no complete human gold-label denominator, so precision and recall remain proxy-based.

## Where Hybrid / Vector Retrieval May Help

- Retrieve candidate product families from messy customs wording that does not exactly match approved aliases.
- Find similar prior reviewed mappings for repeated descriptions.
- Cluster high-value unmatched rows and review buckets into reusable alias or reference-update candidates.
- Improve recall for endoscopy, catheters, cannulas, stents, guidewires, sutures, mesh, hemostats, valves, dialysis, autotransfusion, and orthopedic implant language.

## Where Vector Retrieval May Hurt

- Generic medical terms can retrieve plausible but wrong surgical targets.
- Manufacturer-only text can overmap to popular families from the same player.
- Imaging, lab/IVD, dental, cosmetic, veterinary, and pharma rows can be semantically close to surgical device text.
- Negative vectors can overblock true surgical rows if used as hard blacklists rather than margin evidence.

## Experimental Design Overview

The experiment compares the current workbook tier split against lexical hybrid retrieval, positive vector-style retrieval, and positive-plus-negative retrieval. The vector component is intentionally implemented as a local deterministic n-gram proxy by default to avoid paid APIs and keep results reproducible. It is a candidate-generation signal only; it cannot directly create a trusted mapping.
