# Workflow improvement & testing methods

Suggestions for further improving and testing the surgical trade-data enrichment
pipeline, beyond the current lexical 3-tier cascade + learned HS priors +
consistency reranker + negative-cue guards. Ordered roughly by expected
value-for-effort. Items marked **[scaffolded]** already have partial support.

## A. Higher recall / precision on matching

1. **Multi-candidate generation + learned re-ranker.** For each row, generate the
   top-k family/product candidates from ALL signals (prefix trie, fuzzy/edit-distance,
   hs_prior, embedding similarity) instead of first-hit-wins, then score candidates
   with a re-ranker using features: HS6/HS8 consistency, maker consistency, description
   head-noun match, segment prior, candidate string coverage. Pick argmax. This is the
   general form of today's hand guards + consistency reranker.

2. **LLM sub-agent re-ranker for ambiguous/confusing cases** *[scaffolded — optional]*.
   Route only the low-confidence, high-$ collisions (e.g. Artificial Disc→IBD Cage,
   Electric scalpel→SI hardware, Carpentier-Edwards→Annuloplasty Ring, brand-collision
   families) to an LLM that sees the full description + the candidate list + the
   reference taxonomy, and returns the best product with a rationale. Keep it OFF the
   hot path (batch the residual few hundred rows) so cost/latency stay bounded. The
   held-out gate already clears 90/90 without it, so this is precision polish.

3. **Semantic/embedding candidate generator.** Encode descriptions and reference
   Product/Family labels with a sentence-transformer; nearest-neighbour retrieval as a
   recall booster for paraphrased, translated, or misspelled brands the literal trie
   misses. Use as a CANDIDATE source feeding the re-ranker (A1), not a direct labeller,
   to protect precision.

4. **Fuzzy / edit-distance brand matching** for customs-OCR typos (e.g. "RONYX"→ONYX,
   "PROPILENS"→Prolene). Gate by small edit distance + shared HS to avoid false hits.

5. **Market-specific ground truth for PK / India.** Today PK/India rely on VN-GT
   transfer priors (precision-capped, conservative). Even a small human-labelled sample
   (~200–500 rows each) would let build_prior learn market-native HS×token→device and
   family models, lifting their family/product recall the way VN's GT does.

## B. Out-of-scope suppression (precision)

6. **Generalize the negative-cue framework** beyond dental/veterinary. Drive new cue
   sets from HS-leak analysis: HS 3822/3006/9027 still carry lab-reagent, cosmetic, and
   industrial rows that occasionally collide with device brands. Build cue sets the same
   plain-substring way (validated to touch 0 legit-surgical rows).

7. **Adopt the master's generic-family flags as a living blocklist** *[done, iter-12]*.
   The team's "Generic Family Name?" column (709 rows) is now honoured via the
   "Updated (excl. generic)" tab. Future master revisions flow through automatically —
   re-running is enough. Consider surfacing newly-flagged terms in the QC report.

## C. Evaluation & testing

8. **Automated regression harness (CI-style).** Run the held-out 3-dim eval on every
   config/lexicon change and fail if any dim drops below its floor (recall >90%,
   precision >90% product / >80% family). Prevents silent regressions — the exact
   before/after discipline used in iter-12, automated.

9. **$-value-weighted metrics.** Current recall/precision are row-count based. Add
   value-weighted versions so a high-$ mislabel (e.g. a $17M dental leak) is scored
   proportionally — aligns the metric with the deliverable's dollar bounds.

10. **Ablation studies.** Toggle each guard/veto/prior independently and report its
    marginal precision/recall/$ contribution, so the stack stays justified and no rule
    is dead weight.

11. **Cross-year consistency QC.** The same brand/HS should map consistently across
    FY2024↔FY2025 within a market; flag divergences as candidate errors (a free,
    GT-less signal now that both years are mapped).

12. **Stratified spot-check.** Scale the reservoir spot-check N up and stratify by tier
    AND by $-value bucket so high-value rows get proportional human eyes.

## D. Usability / auditability

13. **Confidence dial.** Expose per-tier confidence thresholds so a user can pick
    recall-max vs precision-max per deliverable, instead of one fixed operating point.

14. **Dashboard drill-through** from each aggregated line to its raw contributing rows
    for audit / dispute resolution.

15. **Active-learning loop.** Surface the lowest-confidence / highest-value matched rows
    for human review each cycle; feed corrections back as incremental GT (feeds A5, C8).
