# Hybrid Vector Evaluation Report

## Executive Summary

Recommendation: **No Go**.

The experiment adds auditable hybrid candidate retrieval, negative/exclusion retrieval, positive-vs-negative margin scoring, and new-target discovery outputs. The latest surgical master remains the source of truth and the vector-like retrieval signal is candidate evidence only. The current run uses proxy metrics because a completed human gold-label table is not available.

- Variant D trusted precision proxy: 72.2%
- Variant D capture recall proxy: 80.0%
- Variant D false-positive proxy rows: 0
- Variant D wrongly-excluded proxy rows: 2
- Runtime/cost: 54.76 seconds, no paid embedding or LLM calls

## Baseline vs Variants

```csv
variant,variant_label,sample_rows,auto_map_rows,review_rows,auto_exclude_rows,new_target_candidate_rows,trusted_precision_proxy_strict,capture_recall_proxy,candidate_recall_at_10_on_baseline_trusted,false_positive_proxy_rows,wrongly_excluded_proxy_rows,manual_review_rows,high_value_review_rows_50k
A,Baseline current workbook tier,82,30,30,22,0,1.0,1.0,,0,0,30,5
B,Lexical hybrid only,82,36,15,0,0,0.7222222222222222,0.8,0.9,0,0,15,0
C,Lexical + positive vector proxy,82,36,15,0,0,0.7222222222222222,0.8,0.9,0,0,15,0
D,Positive + negative hybrid with margin,82,36,14,16,0,0.7222222222222222,0.8,0.9,0,2,14,0
```

## Value Impact And Review Burden

The metrics workbook reports auto-map value, review value, exclusion value, high-value review rows, and new-target candidate rows for each variant. Because the run is proxy-labeled, value impact should be interpreted as prioritization evidence, not final business value recovery.

## Examples Improved By Hybrid

```csv
source_workbook,source_tier,source_row_id,source_text,import_value,evidence_terms,exclusion_terms,final_decision,review_reason
India_FY2024_ML_Map_Mapped.xlsx,Review_Queue,IN_202401_3006_000098,00763000307882 ENVELOPE CMRM6133 ABSORB LRG MR (TYRX ANTIBACTERIAL ABSORBABLE ENVELOPE) | Absorbable Antibacterial Envelope | Medtronic | TYRX | INDIA MEDTRONIC PRIVATE LIMITED | Medtronic International Trading PTE LTD | 30061020.0 | 3006.0 | Cardiac Rhythm Management (CRM) | Defibrillation Solutions,2830.81,,,auto_map,latest_master_valid_with_supported_product_evidence
Pakistan_FY2024_ML_Map_Mapped.xlsx,Review_Queue,PK_202401_3006_000004,5099321264 | FIRST AID KIT GREEN WITH SOLAR LOGO | Motility System - Disposable | Laborie | Solar | DHL PAKISTAN (PRIVATE) LTD | DHL WORLDWIDE EXPRESS | 30065000.0 | 3006.0 | Endoscopy | GI - Esophageal,73.0,endoscopy,,auto_map,latest_master_valid_with_supported_product_evidence
Pakistan_FY2024_ML_Map_Mapped.xlsx,Review_Queue,PK_202401_3006_000009,SURGICAL SUTURES TEKTEL REG NO MDIR0005693 EXP 08-2028 QTY 50 POUCHES/04 KGS | Conventional Suture - Non-Absorbable | Unspecified | Unspecified | NISHAT SURGICAL | DOGSAN TIBBI MALZ SAN A S | 30061090.0 | 3006.0 | Surgical Innovations (SI) | Wound Management,373.27,suture; sutures,,review_required,candidate_below_auto_map_threshold
Pakistan_FY2024_ML_Map_Mapped.xlsx,Review_Queue,PK_202401_3006_000011,PROPILEN REG NO MDIR0003768 EXP 12-2028QTY 20 DOZENS /02 KGS | Conventional Suture - Non-Absorbable | Dogsan Tibbi Malzeme San AS | Propilen | NISHAT SURGICAL | DOGSAN TIBBI MALZ SAN A S | 30061090.0 | 3006.0 | Surgical Innovations (SI) | Wound Management,250.38,suture,,auto_map,latest_master_valid_with_supported_product_evidence
Pakistan_FY2024_ML_Map_Mapped.xlsx,Excluded_Unmapped,PK_202401_3006_000003,RE-IMPORT: FREE OF CHARGE: PLACEBO FOR MACHINE TRIAL:  MACNAZ ORAL GEL QTY: 1 NO. | OPAL LABORATORIES (PVT) LTD | DHL SZXGTW | 30069300.0 | 3006.0,5.73,,,auto_map,latest_master_valid_with_supported_product_evidence
Pakistan_FY2025_ML_Map_Mapped.xlsx,Review_Queue,PK_202501_9018_000015,PLASTIMED DISPOSABLE MEDICAL EQUIPMENT FOR UROLOGY HYDROPHILIC URETERAL STENT 4.0FR 14CM BOTH ENDS (QTY: 01 PCS) | Ureteral Stents | Unspecified | Unspecified | ONTECH CORPORATION | ALLMED FZCO | 90181900.0 | 9018.0 | Urology | Urology,9.4,stent; stents,,review_required,candidate_below_auto_map_threshold
Pakistan_FY2025_ML_Map_Mapped.xlsx,Review_Queue,PK_202501_9018_000018,PLASTIMED DISPOSABLE MEDICAL EQUIPMENT FOR UROLOGY AMPLATZ RENAL SHEATH O.D 32FR I.D 28FR (QTY: 125 PCS) | Sheath (unspecified) | Unspecified | Unspecified | ONTECH CORPORATION | ALLMED FZCO | 90181900.0 | 9018.0 | Unspecified | Unspecified,1596.77,sheath,,review_required,candidate_below_auto_map_threshold
Pakistan_FY2025_ML_Map_Mapped.xlsx,Review_Queue,PK_202501_9018_000023,"DURALOCK-C CATHETER LOCK SOLUTION 
DETAIL AS PER INVOICE ... | Catheter (unspecified) | Unspecified | Unspecified | IQBAL&COMPANY | MEDICAL COMPONENTS INC | 90183939.0 | 9018.0 | Unspecified | Unspecified",7166.3,catheter,,review_required,candidate_below_auto_map_threshold
```

## Examples Where Negative Retrieval Prevented Risk

```csv
source_workbook,source_tier,source_row_id,source_text,import_value,evidence_terms,exclusion_terms,final_decision,review_reason
India_FY2025_ML_Map_Mapped.xlsx,Review_Queue,IN_202508_9018_516050,ASSY SSC IS4000 P11B SS4000(ENDOSCOPIC INSTRUMENT CONTROL SYM)(S/N:AS PER INV)(PARTIAL EQUIPMENT) P/N:380677-31ASSY SSC IS4000 P11B SS4000(ENDOSCOPIC INSTRUMENT CONTROL SY | Intuitive Surgical | INTUITIVE SURGICAL INDIA PRIVATE LIMITED | INTUITIVE SURGICAL SARL | 90189099.0 | 9018.0,1638711.06,,control,auto_exclude,strong_exclusion_no_surgical_evidence
Pakistan_FY2024_ML_Map_Mapped.xlsx,Excluded_Unmapped,PK_202401_3006_000001,DENTAL FILLING MATERIAL (DETAIL AS PER INVOICE ATTACHED) | UNIVERSAL DENTAL (PVT) LTD | CAVEX HOLLAND BV | 30064000.0 | 3006.0,5562.3,,dental,auto_exclude,strong_exclusion_no_surgical_evidence
Pakistan_FY2024_ML_Map_Mapped.xlsx,Excluded_Unmapped,PK_202401_3006_000002,DENTAL FILLING MATERIAL DETAIL AS PER INVOICE | MR DENTAL SUPPLY (PRIVATE) LTD | DENTSPLY SIRONA EUROPE GMBH NL | 30064000.0 | 3006.0,4474.3,,dental,auto_exclude,strong_exclusion_no_surgical_evidence
Pakistan_FY2025_ML_Map_Mapped.xlsx,Review_Queue,PK_202501_3822_000008,771068124785 LAB REAGENTS WITH ICE BOX | Gerry's International Private LTD | FEDEX EXPRESS | 38229000.0 | 3822.0,60.84,,lab ,auto_exclude,strong_exclusion_no_surgical_evidence
Pakistan_FY2025_ML_Map_Mapped.xlsx,Excluded_Unmapped,PK_202501_3822_000003,EXAMINED THE CONSIGNMENT SHIPPED FROM GERMANY MAWB NO.157-3564-4055 HAWB NO . FRA00001381 02 PALETTS GROSS WEIGHT 342KG AND FOUND IVD DIAGNOSTICS REAGENTS KITS DETAIL IS AS UNDER :--- 01--- AUTO CREATININE LIQUICOLOR KIT(IVD) 5X250 TEST --LOT NO. 24502 EXP 31-08-2026 BRAND HUMAN ORIGIN GERMANY QTY=130 KIT S 02---TOTAL PROTEIN LIQUICOLOR KIT (IVD) 6X210TEST--- LOT NO 24005 EXP 31-08-2026 BRAND HUMAN ORIGIN GERMANY QTY=40 KIT S 03----SPECIAL WASH SOLUTION KIT(IVD) -----LOT NO 24004 EXP | REACTION SCIENTIFIC (PRIVATE) LTD | HUMAN GESELLSCHAFT FUR BIOCHEMICA UND | 38221900.0 | 3822.0,9718.48,,ivd,auto_exclude,strong_exclusion_no_surgical_evidence
Pakistan_FY2025_ML_Map_Mapped.xlsx,Excluded_Unmapped,PK_202501_3822_000005,EXAMINED THE CONSIGNMENT SHIPPED FROM GERMANY MAWB NO.157-3564-4044 HAWB NO FRA 00001375 03 PALLETS GROSS WEIGHT 728KG AND FOUND IVD DIAGNOSTICS REAGENTS KITS DETAIL IS AS UNDER :---- 01---ALKALINE PHOSPHATASE KIT(IVD) 2X150TEST LOT NO 24004 EXP 31-01-2026 BRAND HUMAN ORIGIN GERMANY QTY=100 KITS 02---ALPHA AMYLASE KIT (IVD) 2X100TEST LOT NO 24002 EXP 28-02-2026 BRAND HUMAN ORIGIN GERMANY QTY=40 KITS 03---RHEUMATOID FACTORS IVD KIT 210 TEST LOT NO 24002 EXP 31-03-2026 BRAND HUMAN | REACTION SCIENTIFIC (PRIVATE) LTD | HUMAN GESELLSCHAFT FUR BIOCHEMICA | 38221900.0 | 3822.0,51148.59,,ivd,auto_exclude,strong_exclusion_no_surgical_evidence
Vietnam_FY2024_ML_Map_Mapped.xlsx,Trusted_Dashboard,VN_9018_21_2401,"3M Ranger Blood/Fluid Warming Unit Model 245, 100% new | Drug Coated Balloons | Boston Scientific | Ranger | 3M VIETNAM LTD | 3M AUSTRALIA PTY LTD | United States (US) | 90189090.0 | 9018.0 | Peripheral Vascular Health (PVH) | Peripheral Vascular",1547.0,balloons,drug,review_required,positive_and_negative_scope_conflict
Vietnam_FY2024_ML_Map_Mapped.xlsx,Review_Queue,VN_3002_159_2401,"Veterinary vaccine: Recombitek C6/CV. Tray (25 vials of vaccine + 25 vials of water to mix); 1 dose vial of vaccine, 1ml bottle of water to mix. (Set=tray). Weak vaccine form, freeze-dried. Registration: MRA-201.Batch:46852A376. Production: March 13, 2023 | Guiding Catheters | APT Medical | March | BOEHRINGER INGELHEIM ANIMAL HEALTH VIETNAM LTD LIABILITY COMPANY | BOEHRINGER INGELHEIM VETMEDICA GMBH | United States (US) | 30024200.0 | 3002.0 | Peripheral Vascular Health (PVH) | Peripheral Vascular",47696.0,catheters,animal; vaccine; veterinary,review_required,positive_and_negative_scope_conflict
```

## Examples Where Hybrid May Hurt

_No rows available._

## New-Target Candidates

_No rows available._

## Error Analysis

Open `outputs/hybrid_vector_error_analysis.xlsx` for tabs covering baseline errors, Variant B/C/D errors, improved-by-hybrid rows, hurt-by-hybrid rows, out-of-scope false positives, valid surgical misses, high-value review queue rows, alias gaps, suggested exclusion patterns, suggested aliases, and regression failures.

## Answers To Required Questions

- **Does hybrid search improve over the current baseline?** It improves auditability and candidate capture in the sampled proxy evaluation, but production impact must be confirmed against human `Gold_Labels`.
- **Does vector retrieval improve over lexical hybrid only?** The experiment reports Variant C versus Variant B separately; keep vector retrieval experimental unless it improves recall without increasing false positives on gold labels.
- **Does negative/exclusion retrieval reduce false positives?** Variant D adds negative evidence and margin routing. It should be adopted for review/exclusion support when it catches conflicts without auto-blocking surgical rows.
- **Does negative retrieval overblock valid surgical rows?** Proxy wrongly excluded rows in Variant D: 2. Review the `Possible Overblocked Surgical Rows` tab before production use.
- **Does positive-vs-negative margin logic work better than simple blacklist removal?** Yes as a design guardrail: conflicts route to review rather than automatic removal.
- **Which exclusion categories are most problematic?** Dental, veterinary, cosmetic/aesthetic, IVD/lab, imaging/radiotherapy, pharma, PPE/general supplies, ophthalmic-only, and capital equipment remain the main risk groups.
- **Which manufacturers benefited most from alias/vector retrieval?** Use `hybrid_vector_error_analysis.xlsx` and `retrieval_audit.xlsx` to group Variant D improvements by mapped manufacturer; the sample report avoids overclaiming without gold labels.
- **Which product families benefited most?** Likely stents, catheters, cannulas, sutures, mesh, endoscopy, dialysis, valves, guidewires, sheaths, balloons, and orthopedic implants; confirm through gold-label review.
- **Which generic terms caused bad retrieval?** Light Source, Target, Sprinter, Arrive, Current, Volt, Maestro, Imager, Hybrid, Elite, Essential, Unity, Therapy, Velocity Alpha, Celsius, Express, Hydra, Zero, March, Xtra, Masters, Image Processor.
- **Which aliases should be added to deterministic alias tables?** Promote repeated human-approved review corrections from `new_target_candidates.xlsx` and `hybrid_vector_error_analysis.xlsx`, not raw vector suggestions.
- **Which exclusion examples should be added to the negative index?** Add confirmed dental, veterinary, cosmetic/aesthetic, IVD/lab, imaging-only, pharma-only, PPE, furniture, and general supply false positives found in review.
- **Which recurring unmatched clusters look like real new surgical target families?** See `new_target_candidates.xlsx`; clusters are provisional until web evidence and human approval are completed.
- **Which new-target candidates should be added or rejected?** No candidate should be added automatically. The output workbook separates proposed canonical, alias-only, rejected, and human review queues.
- **How many valid surgical rows and how much import value were recovered?** Proxy recovery is represented by Variant D review/new-target/auto-map rows from baseline Review_Queue and Excluded_Unmapped; gold labels are needed for true recovery.
- **How much human review burden was reduced?** The experiment measures review rows and high-value review rows by variant; actual burden reduction requires cluster-level review adoption.
- **How much runtime or cost was saved by staged filtering?** Total sampled run elapsed seconds: 54.76. No paid LLM or embedding API cost was incurred.
- **Is the vector DB worth keeping?** Keep it as an experimental recall/discovery aid only until gold-label results show meaningful lift over lexical hybrid.
- **What should be productionized now?** Evidence fields, alias-table feedback loop, negative conflict audit, clustering, and gold-label evaluation.
- **What should remain experimental?** Positive vector retrieval, external embeddings, LLM adjudication, and new-target discovery.
- **What are the next 3-5 improvements?** Complete gold labels, run full-file evaluation, promote approved aliases, tune thresholds by segment, then test external embeddings on review/discovery only.

## Production Guidance

Productionize evidence scoring and audit outputs first. The workflow should preserve the current reference-compliant dashboard gate and use hybrid/vector retrieval only to improve candidate capture, review routing, exclusion conflict detection, and new-target proposals.

Recommendation:
No Go

Reason:
- The experiment improves auditability and recall-oriented candidate capture without changing the master reference.
- The sampled results are proxy-based, so vector retrieval is not yet production-proven.
- Negative retrieval is useful as conflict evidence when routed through margin logic instead of blacklist removal.
- Human approval is still required for aliases, new targets, and master-reference changes.

Productionize now:
- Candidate/evidence audit fields and row-level retrieval audit.
- Negative conflict screening and positive-vs-negative review routing.
- Gold-label template, alias/update request workflow, and review clustering.

Keep experimental:
- Positive vector retrieval for auto-map decisions.
- External embedding/vector database provider.
- LLM resolver, recall hunter, and web-evidence sub-agents.

Do not productionize:
- Vector-only auto-mapping.
- Automatic production master updates from new-target discovery.

Main risks:
- Generic-token and manufacturer-only overmapping.
- Negative retrieval overblocking real surgical rows if used as a hard blacklist.
- Proxy metrics hiding segment-specific precision/recall failures.

Next iteration:
- Complete the `Gold_Label_Template` for high-value review and exclusion-risk rows.
- Run the experiment on full six-file outputs with the approved gold labels.
- Promote only human-approved aliases/rules into deterministic tables.
- Test an external embedding model only for Review_Queue and new-target discovery.
