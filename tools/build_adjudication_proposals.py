"""Build Adjudication_Proposals workbooks from LLM-assisted review-cluster triage.

Part of the recall-recovery loop (docs/REFERENCE_COMPLIANCE_PLAN.md Phase 3):
high-value Review_Queue clusters from the per-market Surgical_Mapping_QA_Report
are adjudicated (in-session, by an LLM resolver reading cluster member
descriptions) into structured, master-validated proposals. Nothing here changes
any mapping: every row carries a blank `Approved` column for a human reviewer,
and only `tools/apply_review_adjudications.py` acting on `Approved = Y` rows
writes anything into the governed `reference/` tables.

Decision vocabulary (one row per proposal, a cluster may carry several):
  add_alias               a term present in the descriptions maps to an EXISTING
                          master family (family_aliases map) or category
                          (category_qualifier_map); validated against the master
                          at build time, refused otherwise.
  add_rule                a context/disambiguation or negative rule proposal
                          (documented spec; applied manually or in a follow-up).
  confirm_out_of_scope    descriptions are out of surgical scope; terms proposed
                          for a scope_exclude list in reference/term_lists.csv.
  propose_master_addition player/family absent from the master; emitted for the
                          analyst-owned master workbook (never edited here).
  needs_human             cannot be resolved from the descriptions alone
                          (business scope rulings, generic descriptions).

Run:  PYTHONIOENCODING=utf-8 python tools/build_adjudication_proposals.py --market Pakistan --fy 2024
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.reference_compliance import load_master, norm_exact, norm_loose  # noqa: E402

OUT_DIR = ROOT / "outputs" / "remapped_current"
REPORT_DIR = OUT_DIR / "reports"

CLUSTER_KEYS = ["QA_Status", "Product_Evidence_Group", "Negative_Conflict_Group",
                "HS4", "Manufacturer", "Family"]

PROPOSAL_COLUMNS = [
    "Market", "FY", "Cluster_QA_Status", "Cluster_Evidence_Group",
    "Cluster_Conflict_Group", "Cluster_HS4", "Cluster_Manufacturer",
    "Cluster_Family", "Cluster_Rows", "Cluster_Value_USD",
    "Decision", "Proposal_Type", "Alias_Term", "Target_Table",
    "Proposed_Segment", "Proposed_Subsegment", "Proposed_Product",
    "Proposed_Player", "Proposed_Family", "Master_Validated",
    "Rationale", "Evidence_Quote", "Reviewer_Guidance",
    "Approved", "Reviewer_Notes",
]


def C(qa, hs4, mfr="", fam="", evg="", neg=""):
    """Cluster selector; empty string matches blank/NaN in that key."""
    return {"QA_Status": qa, "Product_Evidence_Group": evg,
            "Negative_Conflict_Group": neg, "HS4": hs4,
            "Manufacturer": mfr, "Family": fam}


def P(cluster, decision, rationale, evidence, guidance="", proposal_type="",
      alias="", target="", key5=None):
    row = {
        "cluster": cluster, "Decision": decision, "Proposal_Type": proposal_type,
        "Alias_Term": alias, "Target_Table": target,
        "Rationale": rationale, "Evidence_Quote": evidence,
        "Reviewer_Guidance": guidance,
    }
    if key5:
        (row["Proposed_Segment"], row["Proposed_Subsegment"],
         row["Proposed_Product"], row["Proposed_Player"],
         row["Proposed_Family"]) = key5
    return row


# ---------------------------------------------------------------------------
# Pakistan FY2024 — adjudicated 2026-07-07 (LLM resolver: Claude, in-session).
# Top review clusters by value (~$110M of $159M review value, ~69%).
# ---------------------------------------------------------------------------
PK24 = [
    # --- IV vascular-access consumables (3 clusters, ~$27M combined) --------
    P(C("Review - latest reference gap", "9018", "Unspecified", "Unspecified"),
      "confirm_out_of_scope",
      "Cluster is dominated by IV cannulae / IV catheters (ward infusion "
      "consumables). The master's only cannula categories are cardiac-surgery "
      "extracorporeal cannulae and renal fistula/cannula — there is no "
      "IV-access category, so these cannot become reference-valid.",
      "IV Cannula with Port & Wings | I.V. CANNULLA CATHETER | MEDECO IV "
      "CANNULA 22G",
      guidance="Ratify that IV cannulae/IV administration consumables are out "
               "of surgical scope. Non-IV members of this cluster (e.g. "
               "nephrostomy pigtail catheters) fall to the residual "
               "needs_human row below.",
      proposal_type="scope_term", alias="iv cannula; i.v cannula; i.v. cannula; "
      "intravenous cannula; intravenous catheter",
      target="term_lists:general_consumable_cues"),
    P(C("Review - latest reference gap", "9018", "Unspecified", "Unspecified"),
      "needs_human",
      "Residual non-IV rows in the unspecified cannula/catheter cluster "
      "(urology nephrostomy/pigtail catheters, drainage catheters) have no "
      "clear master category; urology drainage is likely out of scope but a "
      "human should skim the non-IV remainder.",
      "PLASTIMED ... UROLOGY NEPHROSTOMY PIGTAIL CATHETER",
      guidance="Skim members without IV tokens after the IV rule is applied."),
    P(C("Review - latest reference gap", "9018", "B. Braun", "Unspecified"),
      "confirm_out_of_scope",
      "Entire cluster is B. Braun Introcan peripheral IV catheters — same "
      "IV-access consumable class as the unspecified IV cluster; no master "
      "category exists.",
      "CANNULA) INTROCAN-W FEP 24GX3/4\", 0.7X19MM",
      guidance="Covered by the same IV-consumable ruling; 'introcan' may also "
               "be added as a specific cue if the generic IV terms are judged "
               "too broad.",
      proposal_type="scope_term", alias="introcan",
      target="term_lists:general_consumable_cues"),
    P(C("Review - latest reference gap", "9018", "Nipro", "Unspecified"),
      "confirm_out_of_scope",
      "Entire cluster is Nipro/JMI IV cannulae (wing catheters with injection "
      "port) — IV-access consumables, no master category.",
      "I.V CANNULA: WING CATH (ETFE) WITHOUT STOPPER W/INJECTION PORT 22G",
      guidance="Covered by the IV-consumable ruling.",
      proposal_type="scope_term", alias="",
      target="term_lists:general_consumable_cues"),

    # --- Decodable Medtronic catalog families (aliases to existing master) --
    P(C("Review - latest reference gap", "9021", "Medtronic", "Unspecified"),
      "add_rule",
      "Cluster is Medtronic DES shipments under catalog codes 'RONYX####' "
      "(Resolute Onyx RX) with a standalone 'ONYX' token. A bare 'onyx' alias "
      "is ambiguous (master also has Medtronic 'Onyx' NV liquid embolics), so "
      "this needs a context-guarded rule, not a plain alias: Medtronic party + "
      "'stent' in description + 'onyx'/'ronyx' prefix => Resolute Onyx DES.",
      "STENT RONYX30034X ONYX 3.00X34RX | STENT RONYX30038X ONYX 3.00X38RX",
      guidance="$14.5M cluster. Approve as a disambiguation rule "
               "(stent-context onyx => DES); do NOT approve a bare 'onyx' "
               "family alias.",
      proposal_type="disambiguation_rule",
      alias="onyx|ronyx + stent context => resolute onyx",
      target="rule_spec",
      key5=("Coronary and Renal Denervation (CRDN)", "PCI Stents", "DES",
            "Medtronic", "Resolute Onyx")),
    P(C("Review - latest reference gap", "9018", "Medtronic", "Unspecified"),
      "add_alias",
      "Cluster contains Medtronic 'Export Advance' aspiration catheters "
      "spelled out in the description; master family 'Export' (CRDN PCI non "
      "stents, aspiration catheters) exists.",
      "CATHETER ADVANCECE ASPIR EXPORT ADVANCE QTY : 1000 EA",
      guidance="'export advance' is unambiguous as a whole phrase. The "
               "LA6xxxx rows in this cluster are Launcher guide catheters "
               "(catalog prefix LA6) — see companion add_rule row.",
      proposal_type="family_alias", alias="export advance",
      target="term_mappings:family_aliases",
      key5=("Coronary and Renal Denervation (CRDN)", "PCI Non Stents",
            "Aspiration Catheters", "Medtronic", "Export")),
    P(C("Review - latest reference gap", "9018", "Medtronic", "Unspecified"),
      "add_rule",
      "The 'CATHETER LA6xxxx' rows are Medtronic Launcher 6F guiding "
      "catheters (catalog prefix LA6/LA7); master family 'Launcher' (CRDN PCI "
      "non stents, guiding catheters) exists but the word never appears — a "
      "catalog-prefix rule is needed.",
      "CATHETER LA6EBU30 LA 6F 100CM EB30 | CATHETER LA6JR40 LA 6F 100CM JR40",
      guidance="Approve as catalog-prefix rule: Medtronic party + 'catheter' "
               "+ token matching LA[67]\\w+ => Launcher.",
      proposal_type="disambiguation_rule", alias="la6/la7 catalog prefix",
      target="rule_spec",
      key5=("Coronary and Renal Denervation (CRDN)", "PCI Non Stents",
            "Guiding Catheters", "Medtronic", "Launcher")),
    P(C("Review - mapped non-dashboard tier", "9018", "Medtronic"),
      "add_alias",
      "High-value members are decodable Medtronic SI devices: 'TRI 2.0 "
      "SIGC60MT ... CARTRIDGE' = Tri-Staple 2.0 endo reloads (master family "
      "'Tri-Staple 2.0'); 'BLUNT TIP SEALER DIVIDER LF1837' = LigaSure Blunt "
      "Tip (master family 'LigaSure Blunt Tip').",
      "TRI 2.0 SIGC60MT 60 MED THK CARTRIDGE | BLUNT TIP SEALER DIVIDER LF1837",
      guidance="Two aliases: 'tri 2.0' => Tri-Staple 2.0 (Endo - Reload); "
               "'blunt tip sealer divider' (and code 'lf1837') => LigaSure "
               "Blunt Tip. Both whole-phrase, low collision risk.",
      proposal_type="family_alias",
      alias="tri 2.0 => tri-staple 2.0; blunt tip sealer divider => ligasure "
            "blunt tip; lf1837 => ligasure blunt tip",
      target="term_mappings:family_aliases",
      key5=("Surgical Innovations (SI)", "Stapling", "Endo - Reload",
            "Medtronic", "Tri-Staple 2.0")),
    P(C("Review - mapped non-dashboard tier", "9021", "Medtronic"),
      "add_alias",
      "Cluster's top members are 'VLV EVPROPLUS-nn' = Medtronic Evolut PRO+ "
      "transcatheter aortic valves; master family 'Evolut Pro Plus' (SH&A, "
      "TCV Aortic) exists. 'evproplus' appears as a clean bounded token.",
      "VLV EVPROPLUS-29 COMM OUS MDR 34L QTY : 20 EA",
      guidance="Alias 'evproplus' => Evolut Pro Plus. Remaining members of "
               "this manufacturer-only cluster stay in review.",
      proposal_type="family_alias", alias="evproplus",
      target="term_mappings:family_aliases",
      key5=("Structural Heart and Aortic (SH&A)", "Catheter Based Therapy",
            "TCV Aortic", "Medtronic", "Evolut Pro Plus")),

    # --- Category-level alias (existing master triple) ----------------------
    P(C("Review - mapped non-dashboard tier", "9021", "Abbott"),
      "add_alias",
      "Cluster is Abbott CRM shipments described as 'CARDIAC MEDICAL DEVICES "
      "I.E PACEMAKERS'; the master triple CRM | Implantables | Pacemaker "
      "exists but the Tier-2 lexicon misses the plural form 'pacemakers'.",
      "CARDIAC MEDICAL DEVICES I.E PACEMAKERS WITH STANDARD ACCESSORIES",
      guidance="Category-level alias only (family unknown): 'pacemakers' => "
               "Product 'Pacemaker'. Rows become category-tier, Manufacturer "
               "Abbott from the party alias.",
      proposal_type="category_alias", alias="pacemakers",
      target="term_mappings:category_qualifier_map",
      key5=("Cardiac Rhythm Management (CRM)", "Implantables", "Pacemaker",
            "", "")),

    # --- Versius robotic system (misspellings) + Light Source guard ---------
    P(C("Review - generic token / weak evidence", "9018", "Ackermann",
        "Light Source"),
      "add_alias",
      "The $5.35M member is a CMR Versius robotic system misspelled 'VERSUS "
      "SURGEON CONSOLE / VERSIS TRAINER', currently mis-mapped to Ackermann "
      "'Light Source' via a generic token. Master has CMR Surgical | Versius "
      "(Robotic Assisted Surgery Capital).",
      "THE VARIOUS ROBOTIC SURGICAL SYSTEM CONSISTING OF : VERSUS SURGEON "
      "CONSOLE LIGHT SOURCE POWER ... VERSIS TRAINER",
      guidance="Misspelling aliases 'versis' and phrase 'versus surgeon "
               "console' => Versius. Business must also rule whether robotic "
               "capital belongs in the dashboard (see Versius donation row).",
      proposal_type="family_alias",
      alias="versis; versus surgeon console",
      target="term_mappings:family_aliases",
      key5=("Surgical Robotics", "Robotic Surgical Technologies",
            "Robotic Assisted Surgery Capital", "CMR Surgical", "Versius")),
    P(C("Review - generic token / weak evidence", "9018", "Ackermann",
        "Light Source"),
      "add_rule",
      "Family 'Light Source' (Ackermann) is a generic token that captured "
      "third-party camera/visualization capital (STEMA 4K systems, P300 "
      "light sources). The family should require an Ackermann party "
      "corroboration to hold.",
      "P300 LIGHT SOURCE: XENON AND HALOGEN | 4K UHD-VIDEO CAMERA ... STEMA",
      guidance="Add 'Light Source' to the ambiguous-family corroboration "
               "guard (or generic_token_families) so uncorroborated hits "
               "release to category tier.",
      proposal_type="disambiguation_rule", alias="light source",
      target="term_lists:ambiguous_family_keywords"),

    # --- Out-of-scope confirmations -----------------------------------------
    P(C("Review - surgical evidence with exclusion conflict", "9021",
        neg="cochlear/hearing"),
      "confirm_out_of_scope",
      "Entire cluster is cochlear implant systems / hearing processors (Med-El, "
      "Cochlear Ltd, Advanced Bionics). The master has no cochlear or hearing "
      "category (ENT segment covers endoscope lens cleaning only).",
      "ARTIFICIAL BODY PARTS HEARING AIDS COCHLEAR IMPLANT SYSTEMS FOR DEAF "
      "CHILDREN",
      guidance="Ratify hearing/audiology as out of scope; the existing "
               "cochlear/hearing conflict screen then becomes an exclusion.",
      proposal_type="scope_term",
      alias="cochlear implant; hearing aid; behind the ear processor",
      target="term_lists:scope_keyword_hearing (new scope_exclude list)"),
    P(C("Review - exclusion term / manual review", "9018", "Medtronic",
        "Arrive", neg="radiotherapy/cyclotron"),
      "confirm_out_of_scope",
      "The single $1.69M row is an Elekta Versa HD linear accelerator "
      "(radiotherapy capital); the family match 'Arrive' (CAS ablation "
      "catheter) is a token false positive. Radiotherapy capital is out of "
      "scope.",
      "LINAR ACCELERATOR - MULTI ENERGY [MAKE: ELEKTA SOLUTIONS AB / MODEL: "
      "VERSA HD]",
      guidance="Confirm exclusion; also consider adding 'arrive' to "
               "ambiguous_family_keywords (common word).",
      proposal_type="scope_term",
      alias="linear accelerator; linac; versa hd",
      target="term_lists:scope_keyword_imaging"),
    P(C("Review - mapped non-dashboard tier", "9018", "Welfare",
        neg="donation/humanitarian"),
      "confirm_out_of_scope",
      "Cluster is a Siemens MAGNETOM Sola MRI scanner donation; imaging "
      "capital is out of scope. Additionally 'Welfare' as a manufacturer was "
      "matched from the importer party name 'AL KHIDMAT WELFARE SOCIETY' — a "
      "party-name false positive.",
      "MAGNETOM SOLA (Donation from Aghosh Al Khidmat ...) | RF CAGE FOR "
      "MAGNETROM SOLA",
      guidance="Confirm exclusion ('magnetom' => imaging list). Separately: "
               "review the 'Welfare' manufacturer alias for party-name "
               "collisions (add corroboration guard or drop).",
      proposal_type="scope_term", alias="magnetom",
      target="term_lists:scope_keyword_imaging"),
    P(C("Review - mapped non-dashboard tier", "9018", "BD"),
      "confirm_out_of_scope",
      "Cluster is dominated by auto-disable syringes and blood-collection "
      "tubes (BD Emerald Pro syringes, SST II tubes) — general/lab "
      "consumables with no master category. Small biopsy-instrument members "
      "remain review-worthy.",
      "Auto Disable Syringes with Needles (5ML) ... BD Emerald Pro | TUBE SST "
      "II PLH 13 X 100",
      guidance="Add 'auto disable syringe' and 'vacutainer'/'sst ii' cues; "
               "keep HGSTAR/biopsy members in review.",
      proposal_type="scope_term",
      alias="auto disable syringe; disposable syringe; sst ii",
      target="term_lists:general_consumable_cues"),
    P(C("Review - mapped non-dashboard tier", "9018", "Nipro",
        neg="general medical supplies"),
      "confirm_out_of_scope",
      "Cluster is IV infusion/administration sets — general consumables, no "
      "master category (master's 'Infusion Catheter' is a PVH device, not an "
      "IV set).",
      "INFUSION SET (I.V ADMINISTRATION SET WITHOUT BURETTEE)",
      guidance="Phrase cues 'infusion set'/'administration set' are specific "
               "enough not to touch PVH infusion catheters.",
      proposal_type="scope_term", alias="infusion set; administration set",
      target="term_lists:general_consumable_cues"),

    # --- Business decisions (blocked, high value) ----------------------------
    P(C("Review - potential missed surgical", "9018"),
      "needs_human",
      "Largest members are GI/endoscopy capital systems (FujiFilm video "
      "endoscopy, EUS systems) and a Nikkiso hemodialysis system. The master "
      "has no video-endoscopy-system or dialysis-machine category — business "
      "must rule whether endoscopy/dialysis capital enters scope (and the "
      "master) or is excluded.",
      "VIDEO ENDOSCOPY ... FUJI FILM | NIKKISO HEMODIALYSIS SYSTEM",
      guidance="Groups with the Olympus endoscopy-capital cluster (~$2.6M) "
               "and Fresenius dialysis cluster (~$6.1M): one ruling covers "
               "~$22M across PK alone."),
    P(C("Review - mapped non-dashboard tier", "9018", "Fresenius"),
      "needs_human",
      "Split cluster: Fresenius FX-series dialyzers COULD map to the existing "
      "master category Renal Care Solutions | Chronic ... | Chronic "
      "Dialyzers (category alias 'dialyzer'/'hemodialyzer' preparable), but "
      "4008S hemodialysis MACHINES have no master category. Needs a renal-"
      "scope ruling before aliasing.",
      "FRESENIUS FX 10 DIALYZER (HEMODIALYZER) | NEW 4008S CLASSIX ... "
      "HEMODIALYSIS MACHINE",
      guidance="If renal consumables are confirmed in scope: alias "
               "'dialyzer; hemodialyzer' => Chronic Dialyzers and propose "
               "master families for FX/HemoFlow."),
    P(C("Review - exclusion term / manual review", "3006", "J&J",
        "Vicryl Plus"),
      "needs_human",
      "Reference-valid J&J Vicryl Plus sutures under HS 3006 (Extended "
      "scope) — blocked on the standing Extended-HS business decision, not on "
      "mapping quality.",
      "ETHICON VICRYL PLUS SUTURE WITH ANTIBACTERIAL SUTURE GAUZE",
      guidance="Same ruling covers Prolene ($1.45M) and Demesorb ($1.08M) "
               "Extended-HS suture clusters: Option A (core HS only) vs "
               "Option B (surgical product regardless of HS)."),
    P(C("Review - surgical product in Extended HS scope", "3006", "J&J",
        "Prolene"),
      "needs_human",
      "Reference-valid Prolene sutures in Extended HS 3006 — same Extended-HS "
      "business ruling as Vicryl Plus.",
      "(SURGICAL SUTURE) PROLENE SUTURE BLU 75CM M3 USP2/0",
      guidance="Covered by the Extended-HS suture ruling."),
    P(C("Review - surgical product in Extended HS scope", "3006", "Demetech",
        "Demesorb"),
      "needs_human",
      "Reference-valid Demetech Demesorb sutures in Extended HS 3006 — same "
      "Extended-HS business ruling.",
      "DEMESORB (ABSORBABLE POLYGLYCOLIC (PGA) SURGICAL SUTURE)",
      guidance="Covered by the Extended-HS suture ruling."),
    P(C("Review - exclusion term / manual review", "9018", "CMR Surgical",
        "Versius", neg="donation/humanitarian"),
      "needs_human",
      "A single $2.63M Versius robotic system donation: the mapping is "
      "master-valid; the open questions are business ones (include donated "
      "capital? include robotic capital in the dashboard?).",
      "DONATION GOODS: THE VERSIUS ROBOTIC SURGICAL SYSTEM",
      guidance="Business ruling on donations + robotic capital scope."),

    # --- Generic manufacturer-only clusters (not resolvable from text) ------
    P(C("Review - mapped non-dashboard tier", "9021", "Zimmer Biomet"),
      "needs_human",
      "Descriptions are generic ('ARTIFICIAL HUMAN BODY PARTS / JOINTS ... AS "
      "PER INVOICE'); the product mix (knee/hip/trauma) is not recoverable "
      "from text. NB: sampled NexGen rows elsewhere in PK confirm Zimmer knee "
      "families ship here, and 'NexGen' is absent from the master.",
      "ARTIFICAL HUMAN BODY PARTS /JOINTS EQUIPMENT / INSTRUMENTS WITH "
      "ASSORTED SIZES AS PER INVOICE",
      guidance="Candidate for invoice-level follow-up with the importer "
               "(RECH INTERNATIONAL) or import-license cross-reference."),
    P(C("Review - mapped non-dashboard tier", "9018", "Cordis"),
      "needs_human",
      "Generic 'CARDIAC MEDICAL DEVICES FOR ANGIOGRAPHY ANGIOPLASTY' with no "
      "product tokens; Cordis interventional mix not recoverable from text.",
      "CARDIAC MEDICAL DEVICES FOR ANGIOGRAPHY ANGIOPLASTY & INTERVENTIONAL "
      "CARDIOLOGY QTY= 11086-BX",
      guidance="Invoice-level follow-up; do not alias."),
    P(C("Review - mapped non-dashboard tier", "9018", "B. Braun"),
      "needs_human",
      "Mixed Aesculap/B.Braun cluster: ortho drills (plausibly in scope), "
      "Spinocan spinal-anesthesia needles (likely out of scope), generic "
      "'medical equipment' rows. No single ruling fits.",
      "ORTHO DRILL WIT ALL STANDARD ACCESSORIES | SPINOCAN 25GX3 1/2\"",
      guidance="Split review: anesthesia needles => out of scope; power "
               "tools => scope ruling."),
    P(C("Review - mapped non-dashboard tier", "9018", "Olympus"),
      "needs_human",
      "Olympus GI endoscopy capital (videoscopes, processors, bronchoscopes) "
      "— covered by the endoscopy-capital scope ruling.",
      "ULTRASONIC GASTRO VIDEOSCOPE | CV-190 (PAL) EXERA III VIDEO PROCESSOR",
      guidance="Grouped with the FujiFilm endoscopy-capital ruling."),
    P(C("Review - mapped non-dashboard tier", "9018", "Nipro"),
      "needs_human",
      "Mixed Nipro cluster: hemodialysis blood tubing sets (renal-scope "
      "ruling), syringes (out of scope), Novofine diabetes pen needles (out "
      "of scope).",
      "BLOOD TUBING SET ... FOR HEMODIALYSIS | NOVOFINE 31G 6MM",
      guidance="Renal ruling covers tubing; 'novofine' and syringe cues can "
               "join general_consumable_cues on approval."),
    P(C("Review - mapped non-dashboard tier", "9021", "Smith & Nephew"),
      "needs_human",
      "Generic 'ARTIFICIAL ORTHOPAEDIC IMPLANTS AS PER INVOICE' rows via "
      "VARITRON; product mix not recoverable from text.",
      "ARTIFICIAL ORTHOPAEDIC IMPLANTS AS PER INVOICE",
      guidance="Invoice-level follow-up like the Zimmer cluster."),
    P(C("Review - mapped non-dashboard tier", "9018", "J&J"),
      "needs_human",
      "Ethicon Endo-Surgery shipments listed only as invoice serial ranges; "
      "product mix (staplers/energy) not recoverable from text.",
      "(ITEMS SERIAL NO.1 TO 46) ETHICON ENDO-SURGERY LLC US",
      guidance="Invoice-level follow-up with HOORA PHARMA."),
    P(C("Review - mapped non-dashboard tier", "9018", "Teleflex"),
      "needs_human",
      "Decodable members exist — 'RediGuard IAB 8Fr 40cc' is an intra-aortic "
      "balloon (no master category: propose addition if cardiac-support is "
      "in scope); CVC sets are vascular-access consumables (likely out).",
      "RediGuard IAB: 8Fr 40cc | CVC SET: 3 LUMEN 7 FR X 16 CM",
      guidance="If cardiac support enters scope: propose master addition "
               "Teleflex/Arrow IAB; else exclude."),
    P(C("Review - precision risk conflict", "9018", "Unspecified",
        "Unspecified"),
      "needs_human",
      "Sampled members look CORRECTLY mapped at category tier (CRDN inflation "
      "devices, SH&A occluder delivery systems, ACM endotracheal tubes) — the "
      "precision-risk flag appears over-cautious here; a quick human pass "
      "could release them.",
      "BALLOON INFLATION DEVICE SCW-BID1-20 | Occluder Delivery System ASD",
      guidance="Fast confirm-release candidate: master triples already "
               "validate."),
]

# ---------------------------------------------------------------------------
# Vietnam FY2024 — adjudicated 2026-07-08 (LLM resolver: Claude, in-session).
# VN review value is far more fragmented than PK (5,186 clusters; 145 needed
# for 60%): this first round covers the top ~17 clusters (~28% of $562M).
# Unlike PK, VN's top clusters are dominated by FALSE POSITIVES correctly
# parked in review — clearing them shrinks the review queue rather than
# growing Trusted.
# ---------------------------------------------------------------------------
VN24 = [
    # --- APT Medical "March" date-token false positives (~$51M) -------------
    P(C("Review - surgical product in Extended HS scope", "3002",
        "APT Medical", "March", neg="pharmaceutical/vaccine"),
      "add_rule",
      "Family 'March' (APT Medical guiding catheter) matched the production "
      "month in vaccine/pharma rows ('Production date: March 2023'). Rows are "
      "GSK/MSD vaccines and biologics under HS 3002 — pharma, out of scope. "
      "Rule: 'March' family hit + pharmaceutical/vaccine/veterinary conflict "
      "+ no APT Medical party => route straight to Excluded_Unmapped.",
      "INFANRIX HEXA Vaccine ... Production date: March 2023 | BEXSERO "
      "Vaccine ... Manufacturer: March 2024",
      guidance="$40.1M cluster of pure date-token noise; two sibling "
               "clusters below share the ruling.",
      proposal_type="disambiguation_rule",
      alias="march + pharma/vaccine/vet conflict => excluded",
      target="rule_spec"),
    P(C("Review - excluded scope: veterinary", "3002", "APT Medical", "March",
        neg="veterinary"),
      "add_rule",
      "Same 'March' date-token false positive on veterinary vaccines "
      "(Zoetis/Virbac pig vaccines). Covered by the March routing rule.",
      "Veterinary vaccine Fostera Gold PCV MH ... Production date: March 15, "
      "2024",
      guidance="Sibling of the $40.1M March cluster.",
      proposal_type="disambiguation_rule",
      alias="march + pharma/vaccine/vet conflict => excluded",
      target="rule_spec"),
    P(C("Review - surgical product in Extended HS scope", "3002",
        "APT Medical", "March", neg="pharmaceutical/vaccine expanded"),
      "add_rule",
      "Same 'March' date-token false positive on biologics (MVASI, Mabthera, "
      "Enterogermina). Covered by the March routing rule.",
      "MVASI (Bevacizumab 100mg/4ml) ... Manufacturer: March 26, 2023",
      guidance="Sibling of the $40.1M March cluster.",
      proposal_type="disambiguation_rule",
      alias="march + pharma/vaccine/vet conflict => excluded",
      target="rule_spec"),

    # --- Master-valid but flagged: business calls ----------------------------
    P(C("Review - precision risk conflict", "9018", "Intromedic", "Mirocam",
        neg="pharmaceutical/vaccine expanded"),
      "needs_human",
      "Intromedic MiroCam MC1200 capsule endoscopes — the full key Endoscopy "
      "| GI | Capsule | Intromedic | Mirocam IS master-valid; the rows were "
      "flagged only by the expanded pharma screen and are marked 'FOC "
      "products' (free of charge) with a $23.5M single row. Whether FOC "
      "declared values belong in the market total is a business/value-"
      "plausibility ruling, not a mapping problem.",
      "Endoscope Capsule /Capsule Endoscope MiroCam Model: MC1200 ... FOC "
      "products",
      guidance="$39.7M would grow VN trusted ~15%: verify declared values "
               "before release."),
    P(C("Audit - manufacturer only", "9018", "Terumo", "Exchange Wire"),
      "needs_human",
      "Terumo Vietnam importing production components (threading/insertion "
      "needles) from Terumo Corporation — these are inputs to local "
      "MANUFACTURING, not devices sold into the Vietnamese market. Needs a "
      "business ruling on excluding manufacturing-input imports (importer = "
      "local factory of the exporter group).",
      "SC55S1864BV#&Medical threading needle ... TERUMO VIETNAM CO LTD <- "
      "TERUMO CORPORATION",
      guidance="Candidate rule: importer==manufacturer's own local plant => "
               "exclude as intra-group production flow."),

    # --- Out-of-scope confirmations (false-positive clean-up) ---------------
    P(C("Review - surgical evidence with exclusion conflict", "9021",
        neg="dental"),
      "confirm_out_of_scope",
      "Straumann/Neodent permanent dental implant abutments — dental domain, "
      "no master category. The dental screen worked; ratify exclusion.",
      "Permanent dental implant abutment implanted in the human body ... "
      "NEODENT",
      guidance="Ratify: dental stays out of scope.",
      proposal_type="scope_term", alias="dental implant abutment",
      target="term_lists:scope_keyword_dental"),
    P(C("Review - candidate surgical evidence", "9021"),
      "confirm_out_of_scope",
      "Artificial tooth roots (Biotem/Dentium/Straumann titanium implants) — "
      "dental, no master category.",
      "Artificial tooth root, ASTFA 4010S, long-term implant ... Biotem",
      guidance="Terms cover the Vietnamese-customs phrasing of dental "
               "implants.",
      proposal_type="scope_term", alias="artificial tooth root; tooth root",
      target="term_lists:scope_keyword_dental"),
    P(C("Review - candidate surgical evidence", "9021", "Abbott",
        "Epic Mitral Valve"),
      "confirm_out_of_scope",
      "Motiva silicone breast implants (Establishment Labs) mis-attributed "
      "to Abbott 'Epic Mitral Valve'. Breast/aesthetic implants have no "
      "master category — cosmetic domain.",
      "Motiva-ERSD-300Q breast implants (Sterile Silicone Breast Implants ...)",
      guidance="Also fixes the Abbott attribution false positive.",
      proposal_type="scope_term", alias="breast implant",
      target="term_lists:scope_keyword_cosmetic"),
    P(C("Review - candidate surgical evidence", "9027"),
      "confirm_out_of_scope",
      "Jabil UV curing machines for printed circuit boards — industrial "
      "electronics equipment under HS 9027, not medical at all.",
      "Machine using ultraviolet rays to dry printed circuit board adhesive, "
      "brand Jabil",
      guidance="Industrial-electronics cue.",
      proposal_type="scope_term", alias="printed circuit board",
      target="term_lists:scope_keyword_lab_ivd"),
    P(C("Review - unspecified category with surgical evidence", "9018",
        "Terumo ", "Trima Accel", neg="blood pressure monitor"),
      "confirm_out_of_scope",
      "Omron home blood-pressure monitors hs_prior-mapped to 'Trima Accel' — "
      "consumer monitoring devices, no master category; the conflict screen "
      "caught them, ratify exclusion.",
      "OMRON AUTOMATIC BLOOD PRESSURE MONITOR ... HEM-8712",
      guidance="NB the mapped Manufacturer carries a trailing space "
               "('Terumo ') — attribution is itself a false positive.",
      proposal_type="scope_term", alias="blood pressure monitor",
      target="term_lists:scope_keyword_imaging"),
    P(C("Review - surgical evidence with exclusion conflict", "9021",
        neg="cochlear/hearing"),
      "confirm_out_of_scope",
      "Cochlear Nucleus implant systems — hearing/audiology, no master "
      "category (same ruling as the Pakistan FY2024 cochlear cluster).",
      "Cochlear Implant Hearing Aid (Curved Cochlear Implant) - Cochlear "
      "Nucleus Cl512",
      guidance="Covered by the scope_keyword_hearing list created by the PK "
               "ingestion; idempotent re-add is safe.",
      proposal_type="scope_term",
      alias="cochlear implant; hearing aid; behind the ear processor",
      target="term_lists:scope_keyword_hearing (new scope_exclude list)"),
    P(C("Review - candidate surgical evidence", "9021", "Terumo",
        "Capiox RX", neg="pharmaceutical/vaccine expanded"),
      "confirm_out_of_scope",
      "Alcon AcrySof intraocular lenses mis-attributed to Terumo 'Capiox "
      "RX'. Ophthalmic IOLs have no master category — ophthalmic domain "
      "needs its own scope list.",
      "Acrysof IQ Aspheric IOL - 22.0 diopter artificial lens ... ALCON",
      guidance="Creates scope_keyword_ophthalmic; 'diopter' is specific "
               "enough for customs text.",
      proposal_type="scope_term",
      alias="intraocular lens; acrysof; diopter",
      target="term_lists:scope_keyword_ophthalmic (new scope_exclude list)"),
    P(C("Review - unspecified category", "9021", "Norm Tibbi ",
        "Trauma Plates And Screws"),
      "confirm_out_of_scope",
      "Invisalign orthodontic aligners hs_prior-mapped to 'Trauma Plates And "
      "Screws' — dental orthodontics, out of scope; mapping is a false "
      "positive.",
      "Invisalign System - Comprehensive (Including upper and lower "
      "aligners)",
      guidance="'invisalign' and 'orthodontic aligner' as dental cues.",
      proposal_type="scope_term", alias="invisalign; orthodontic aligner",
      target="term_lists:scope_keyword_dental"),
    P(C("Review - surgical evidence with exclusion conflict", "9018",
        fam="Forceps", neg="dental"),
      "confirm_out_of_scope",
      "Osstem dental chairs mis-holding family 'Forceps' — dental capital "
      "equipment, out of scope.",
      "K3 CART AirSucWater LowAir EMS S5 dental chair ... OSSTEM",
      guidance="'dental chair' cue; also a generic-token lesson for "
               "'Forceps'.",
      proposal_type="scope_term", alias="dental chair",
      target="term_lists:scope_keyword_dental"),

    # --- Genuine recall: spine fixation category alias -----------------------
    P(C("Review - unspecified category", "9021", "Nuvasive",
        "Thoracolumbar rods and screws"),
      "add_alias",
      "Nuvasive multiaxial spinal screws (30-day+ implants): the master "
      "category CST | Total Spinal | Spinal Fusion Fixation - Thoracolumbar "
      "exists; the Tier-2 lexicon lacks the customs phrasing. Category alias "
      "promotes these to reference-valid category tier.",
      "ARM15T multi-axis screw, size 6.5x45mm ... Manufacturer: Nuvasive Inc",
      guidance="Phrases are specific to spinal fixation; trauma bone screws "
               "say 'bone screw'/'locking plate' instead.",
      proposal_type="category_alias",
      alias="multiaxial spinal screw; multi-axis screw; spinal fixation "
            "screw; spinal screw",
      target="term_mappings:category_qualifier_map",
      key5=("Cranial & Spinal Technologies (CST)", "Total Spinal",
            "Spinal Fusion Fixation - Thoracolumbar", "", "")),
    P(C("Review - unspecified category", "9021", "Medtronic", "CD Horizon"),
      "add_alias",
      "Medtronic spinal fixation screws already hs_prior-tagged 'CD Horizon' "
      "(the full key CST | Total Spinal | Spinal Fusion Fixation - "
      "Thoracolumbar | Medtronic | CD Horizon IS master-valid). The same "
      "spinal-screw category alias lets these validate at category tier; "
      "family-tier promotion would need invoice confirmation.",
      "Internal locking screw used in spinal fixation, long-term "
      "implantation ... HSX: Medtronic Puerto Rico",
      guidance="Same alias terms as the Nuvasive row (idempotent).",
      proposal_type="category_alias",
      alias="multiaxial spinal screw; spinal fixation screw",
      target="term_mappings:category_qualifier_map",
      key5=("Cranial & Spinal Technologies (CST)", "Total Spinal",
            "Spinal Fusion Fixation - Thoracolumbar", "", "")),
]

DECISIONS: dict[tuple[str, int], list[dict]] = {
    ("Pakistan", 2024): PK24,
    ("Vietnam", 2024): VN24,
}


def build(market: str, fy: int) -> Path:
    decisions = DECISIONS.get((market, fy))
    if not decisions:
        raise SystemExit(f"no adjudications encoded for {market} FY{fy}")

    wb_name = f"{market}_FY{fy}_ML_Map_Mapped.xlsx"
    print(f"[adjudicate] loading {wb_name} RawData ...")
    raw = pd.read_excel(OUT_DIR / wb_name, sheet_name="RawData", dtype=str)
    rev = raw[raw["Output_Tier"].eq("Review_Queue")].copy()
    rev["_val"] = pd.to_numeric(rev["Total_Value_USD"], errors="coerce").fillna(0)

    master = load_master()

    rows = []
    for d in decisions:
        sel = pd.Series(True, index=rev.index)
        for k, v in d["cluster"].items():
            sel &= rev[k].fillna("").eq(v)
        sub = rev[sel]
        key5 = tuple(d.get(f) or "" for f in (
            "Proposed_Segment", "Proposed_Subsegment", "Proposed_Product",
            "Proposed_Player", "Proposed_Family"))
        validated = ""
        if any(key5):
            if key5[3] or key5[4]:  # family-level: full 5-key must exist
                validated = "Y" if (
                    tuple(norm_exact(v) for v in key5) in master["full_exact"]
                    or tuple(norm_loose(v) for v in key5) in master["full_loose"]
                ) else "N"
            else:                    # category-level: triple must exist
                validated = "Y" if (
                    tuple(norm_exact(v) for v in key5[:3]) in master["cat_exact"]
                    or tuple(norm_loose(v) for v in key5[:3]) in master["cat_loose"]
                ) else "N"
            if validated == "N":
                raise AssertionError(
                    f"proposal not master-valid: {key5} ({d['Rationale'][:60]}...)")
        c = d["cluster"]
        rows.append({
            "Market": market, "FY": fy,
            "Cluster_QA_Status": c["QA_Status"],
            "Cluster_Evidence_Group": c["Product_Evidence_Group"],
            "Cluster_Conflict_Group": c["Negative_Conflict_Group"],
            "Cluster_HS4": c["HS4"],
            "Cluster_Manufacturer": c["Manufacturer"],
            "Cluster_Family": c["Family"],
            "Cluster_Rows": int(len(sub)),
            "Cluster_Value_USD": round(float(sub["_val"].sum()), 2),
            "Decision": d["Decision"],
            "Proposal_Type": d["Proposal_Type"],
            "Alias_Term": d["Alias_Term"],
            "Target_Table": d["Target_Table"],
            "Proposed_Segment": key5[0], "Proposed_Subsegment": key5[1],
            "Proposed_Product": key5[2], "Proposed_Player": key5[3],
            "Proposed_Family": key5[4], "Master_Validated": validated,
            "Rationale": d["Rationale"], "Evidence_Quote": d["Evidence_Quote"],
            "Reviewer_Guidance": d["Reviewer_Guidance"],
            "Approved": "", "Reviewer_Notes": "",
        })

    props = pd.DataFrame(rows, columns=PROPOSAL_COLUMNS)
    zero = props[props["Cluster_Rows"].eq(0)]
    if not zero.empty:
        raise AssertionError(
            "cluster selectors matched 0 rows:\n"
            + zero[["Cluster_QA_Status", "Cluster_HS4", "Cluster_Manufacturer",
                    "Cluster_Family"]].to_string())

    summary = (props.groupby("Decision")
               .agg(Proposals=("Decision", "size"),
                    Rows=("Cluster_Rows", "sum"),
                    Value_USD=("Cluster_Value_USD", "sum"))
               .reset_index().sort_values("Value_USD", ascending=False))
    total_review = float(rev["_val"].sum())
    # a cluster can carry several proposal rows — count its value once
    covered = (props.drop_duplicates(
        subset=["Cluster_QA_Status", "Cluster_Evidence_Group",
                "Cluster_Conflict_Group", "Cluster_HS4",
                "Cluster_Manufacturer", "Cluster_Family"])
        ["Cluster_Value_USD"].sum())
    log = pd.DataFrame([{
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Market": market, "FY": fy,
        "Adjudicator": "LLM resolver (Claude, in-session) — proposal-only; "
                       "no mapping changed; human approval required",
        "Review_Value_USD": round(total_review, 2),
        "Adjudicated_Value_USD": round(float(covered), 2),
        "Coverage": f"{covered / total_review:.1%}",
        "Proposals": len(props),
    }])

    out = REPORT_DIR / f"Adjudication_Proposals_{market}_FY{fy}.xlsx"
    with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
        props.to_excel(xw, sheet_name="Adjudication_Proposals", index=False)
        summary.to_excel(xw, sheet_name="Summary", index=False)
        log.to_excel(xw, sheet_name="Change_Log", index=False)
        for name, width in (("Adjudication_Proposals", 28), ("Summary", 18),
                            ("Change_Log", 24)):
            ws = xw.sheets[name]
            ws.freeze_panes(1, 0)
            ws.set_column(0, len(props.columns), width)
    print(f"[adjudicate] {len(props)} proposals covering "
          f"${covered:,.0f} of ${total_review:,.0f} review value "
          f"({covered / total_review:.1%}) -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True)
    ap.add_argument("--fy", type=int, required=True)
    args = ap.parse_args()
    build(args.market, args.fy)


if __name__ == "__main__":
    main()
