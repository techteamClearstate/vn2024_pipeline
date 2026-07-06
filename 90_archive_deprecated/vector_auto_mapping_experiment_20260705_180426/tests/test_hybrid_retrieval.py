import json
import unittest

import pandas as pd

from pipeline.hybrid_retrieval.objects import OBJECT_COLUMNS
from pipeline.hybrid_retrieval.retrieval import RetrievalConfig, RetrievalEngine


def make_object(**values):
    row = {column: "" for column in OBJECT_COLUMNS}
    row.update(values)
    return row


def test_objects():
    metadata_stapler = {
        "Segment": "Surgical",
        "Sub-segment": "General Surgery",
        "Product": "Surgical Stapling",
        "Player": "Medtronic",
        "Model/ Family Name": "Endo GIA",
    }
    metadata_stent = {
        "Segment": "Cardiovascular",
        "Sub-segment": "Coronary Intervention",
        "Product": "DES",
        "Player": "Abbott",
        "Model/ Family Name": "XIENCE",
    }
    metadata_target = {
        "Segment": "Cardiovascular",
        "Sub-segment": "Peripheral Intervention",
        "Product": "Guidewires",
        "Player": "Boston Scientific",
        "Model/ Family Name": "Target",
    }
    return pd.DataFrame(
        [
            make_object(
                object_id="canonical_tuple:medtronic:endo-gia",
                object_type="canonical_tuple",
                canonical_target_id="surgical|general surgery|surgical stapling|medtronic|endo gia",
                canonical_manufacturer="Medtronic",
                manufacturer_aliases="Covidien;US Surgical;Tyco Healthcare",
                product_family="Endo GIA",
                model="Endo GIA",
                segment_path="Surgical > General Surgery > Surgical Stapling",
                in_scope_flag="Y",
                common_import_terms="surgical stapler reload cartridge linear cutter anvil circular stapler",
                source_reference="fixture",
                reference_version="fixture",
                review_status="approved",
                retrieval_text=(
                    "Object type: canonical_tuple. Canonical manufacturer: Medtronic. "
                    "Manufacturer aliases: Covidien, US Surgical. Brand/product family: Endo GIA. "
                    "Product category: surgical stapler, reload, cartridge, linear cutter."
                ),
                metadata_json=json.dumps(metadata_stapler),
            ),
            make_object(
                object_id="canonical_tuple:abbott:xience",
                object_type="canonical_tuple",
                canonical_target_id="cardiovascular|coronary intervention|des|abbott|xience",
                canonical_manufacturer="Abbott",
                manufacturer_aliases="Abbott Vascular;St Jude Medical",
                product_family="XIENCE",
                model="XIENCE",
                segment_path="Cardiovascular > Coronary Intervention > DES",
                in_scope_flag="Y",
                common_import_terms="drug eluting stent coronary stent system des implantable stent",
                source_reference="fixture",
                reference_version="fixture",
                review_status="approved",
                retrieval_text=(
                    "Object type: canonical_tuple. Canonical manufacturer: Abbott. "
                    "Brand/product family: XIENCE. Product category: DES, drug eluting stent, coronary stent."
                ),
                metadata_json=json.dumps(metadata_stent),
            ),
            make_object(
                object_id="canonical_tuple:bsc:target",
                object_type="canonical_tuple",
                canonical_target_id="cardiovascular|peripheral intervention|guidewires|boston scientific|target",
                canonical_manufacturer="Boston Scientific",
                manufacturer_aliases="BSC",
                product_family="Target",
                model="Target",
                segment_path="Cardiovascular > Peripheral Intervention > Guidewires",
                in_scope_flag="Y",
                common_import_terms="guidewire neurovascular wire",
                source_reference="fixture",
                reference_version="fixture",
                review_status="approved",
                retrieval_text=(
                    "Object type: canonical_tuple. Canonical manufacturer: Boston Scientific. "
                    "Brand/product family: Target. Product category: neurovascular guidewire."
                ),
                metadata_json=json.dumps(metadata_target),
            ),
            make_object(
                object_id="product_family_alias:video-endoscopy",
                object_type="product_family_alias",
                alias_text="video endoscopy system",
                product_family="Video Endoscopy System",
                segment_path="Surgical > MIS > Endoscopy Systems",
                source_reference="fixture",
                reference_version="fixture",
                review_status="proposed",
                retrieval_text=(
                    "Object type: product_family_alias. Alias terms: video endoscopy system, endoscope processor, "
                    "endosurgery equipment. Segment path: Surgical > MIS > Endoscopy Systems."
                ),
            ),
            make_object(
                object_id="hard_exclusion:dental",
                object_type="hard_exclusion_term",
                exclusion_category="dental",
                term="dental orthodontic abutment",
                decision_default="exclude",
                strength="hard",
                retrieval_text="Object type: hard_exclusion_term. Category: dental. Terms: dental orthodontic abutment.",
            ),
            make_object(
                object_id="negative_vector:cosmetic",
                object_type="negative_vector_example",
                exclusion_category="cosmetic_aesthetic",
                source_text="aesthetic filler cannula beauty dermal injection",
                common_import_terms="aesthetic filler cannula beauty dermal injection",
                decision_default="review",
                reason="Cosmetic and aesthetic-use products are outside surgical dashboard scope.",
                retrieval_text=(
                    "Object type: negative_vector_example. Source text: aesthetic filler cannula beauty dermal injection. "
                    "Exclusion category: cosmetic aesthetics."
                ),
            ),
        ]
    )


class HybridRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.engine = RetrievalEngine(
            test_objects(),
            RetrievalConfig(auto_map_threshold=0.46, review_threshold=0.38, auto_exclude_threshold=0.60),
        )

    def test_exact_alias_family_match_can_auto_map(self):
        row = {
            "UniqueID": "1",
            "Detailed_Product": "COVIDIEN ENDO GIA TRI STAPLE RELOAD PURPLE 60MM",
            "Importer": "",
            "Exporter": "",
            "HS_Code": "9018",
        }
        result = self.engine.retrieve_row(row, variant="D")
        self.assertEqual(result["final_decision"], "auto_map")
        self.assertEqual(result["mapped_manufacturer"], "Medtronic")

    def test_manufacturer_only_does_not_auto_map(self):
        row = {
            "UniqueID": "2",
            "Detailed_Product": "COVIDIEN MEDICAL DEVICE SYSTEM ACCESSORY",
            "Importer": "",
            "Exporter": "",
            "HS_Code": "9018",
        }
        result = self.engine.retrieve_row(row, variant="D")
        self.assertNotEqual(result["final_decision"], "auto_map")

    def test_dental_only_exclusion_can_auto_exclude(self):
        row = {
            "UniqueID": "3",
            "Detailed_Product": "orthodontic dental abutment kit",
            "Importer": "",
            "Exporter": "",
            "HS_Code": "9021",
        }
        result = self.engine.retrieve_row(row, variant="D")
        self.assertEqual(result["final_decision"], "auto_exclude")
        self.assertEqual(result["review_reason"], "strong_exclusion_no_surgical_evidence")

    def test_cosmetic_cannula_conflict_routes_to_review(self):
        row = {
            "UniqueID": "4",
            "Detailed_Product": "aesthetic filler cannula dermal injection",
            "Importer": "",
            "Exporter": "",
            "HS_Code": "9018",
        }
        result = self.engine.retrieve_row(row, variant="D")
        self.assertEqual(result["final_decision"], "review_required")
        self.assertEqual(result["review_reason"], "positive_and_negative_scope_conflict")

    def test_generic_family_token_alone_does_not_auto_map(self):
        row = {
            "UniqueID": "5",
            "Detailed_Product": "target medical device kit",
            "Importer": "",
            "Exporter": "",
            "HS_Code": "9018",
        }
        result = self.engine.retrieve_row(row, variant="D")
        self.assertNotEqual(result["final_decision"], "auto_map")

    def test_noncanonical_surgical_alias_becomes_new_target_candidate(self):
        row = {
            "UniqueID": "6",
            "Detailed_Product": "video endoscopy system with endoscope processor",
            "Importer": "",
            "Exporter": "",
            "HS_Code": "9018",
        }
        result = self.engine.retrieve_row(row, variant="D")
        self.assertEqual(result["final_decision"], "new_target_candidate")


if __name__ == "__main__":
    unittest.main()
