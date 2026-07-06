# Hybrid Negative Vector Experiment Design

## Architecture

The experimental workflow adds a retrieval layer around the existing mapping process. It does not replace the approved master reference or production dashboard gates. The workflow creates retrieval objects, retrieves positive and negative candidates, fuses scores, routes rows, and writes full audit outputs.

## Retrieval Object Types

- `canonical_tuple`: approved latest-master surgical targets.
- `manufacturer_alias`: approved manufacturer or historical-name aliases.
- `product_family_alias`: product, family, customs phrase, and abbreviation aliases.
- `reviewed_mapping_example`: prior approved mapping examples, if available.
- `hard_exclusion_term`: deterministic exclusion terms.
- `negative_vector_example`: semantic negative examples for dental, veterinary, cosmetic/aesthetic, IVD/lab, imaging, pharma, PPE, furniture, and general supplies.
- `excluded_prior_row`: previously confirmed excluded rows, when available.
- `ambiguous_scope_example`: examples that should go to review rather than auto-exclusion.
- `new_target_candidate`: provisional clusters that may become aliases or reference update requests after human approval.

## Positive Index Design

Positive retrieval objects combine segment path, product, player, family/model, aliases, and common import terms into a normalized retrieval text. The experiment evaluates exact/alias signals, BM25-like token overlap, fuzzy matching, character n-gram similarity, and a local n-gram vector proxy.

## Negative Index Design

Negative objects contain exclusion categories and examples. Negative retrieval is used to calculate scope conflict and positive-vs-negative margin. It is not a simple blacklist. Strong negative evidence with weak positive evidence can auto-exclude; strong positive and negative evidence routes to review.

## Scoring Logic

Candidate score is configurable:

```
candidate_score =
  0.25 * exact_or_alias_score
+ 0.20 * bm25_score
+ 0.15 * fuzzy_score
+ 0.10 * char_ngram_score
+ 0.20 * vector_score
+ 0.10 * prior_approved_example_score
- generic_token_penalty
- manufacturer_only_penalty
- exclusion_conflict_penalty
```

The experiment also records product evidence, family evidence, manufacturer evidence, generic-token risk, exclusion terms, top positive candidates, top negative candidates, and scope margin.

## Decision Gates

`auto_map` is allowed only when the selected candidate is a latest-master canonical tuple, product/family evidence is strong, the row is not generic-token-only, not manufacturer-only, not vector-only, and has no strong exclusion conflict.

`review_required` is used for weak surgical evidence, fuzzy-only evidence, semantic/vector-only evidence, generic-token risk, manufacturer-only evidence, positive/negative conflicts, multiple close candidates, and reference gaps.

`auto_exclude` is allowed only when hard or negative exclusion evidence is strong and surgical evidence is weak.

`new_target_candidate` is used for recurring or high-value surgical-looking rows with no approved canonical target.

## Efficiency Design

- Normalize rows once and cache extracted features.
- Apply hard exclusions and deterministic evidence before expensive retrieval.
- Use cheap token/character prefiltering before fuzzy scoring.
- Use local deterministic vector proxy by default.
- Keep external embeddings and LLM adjudication behind disabled feature flags.
- Write row-level audit output so reruns can compare score changes without re-reviewing everything.

## New-Target Discovery Design

Unmatched/review rows with surgical evidence and weak approved-target matches are clustered by evidence terms and value. The workflow writes a human approval queue with source examples, proposed action, and web-evidence placeholders. Production master updates are explicitly out of scope for the experiment.

## Guardrails

- Latest master list is the source of truth.
- Vector DB is not a source of truth.
- No vector-only auto-mapping.
- No manufacturer-only auto-mapping.
- No generic-token auto-mapping.
- Negative vectors do not behave as automatic blacklists.
- New targets require human approval before production.
- Every decision is auditable from scores, evidence terms, candidates, and reason codes.
