import io
import tempfile
import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from evidence_seed import seed
from evidence_maintenance import attach_snapshot, maintenance_report
from evidence_store import evidence_db
from main import app

BASE = "/api/admin/evidence"
HEADERS = {"X-Admin-Request": "evidence-admin"}


class EvidenceAdminTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {
            "AGRIRAG_DB_PATH": str(Path(directory) / "test.sqlite3"),
            "AGRIRAG_ADMIN_USER": "reviewer",
            "AGRIRAG_ADMIN_PASSWORD": "test-password",
        }))
        self.client = self.enterContext(TestClient(app))
        self.client.auth = ("reviewer", "test-password")

    def published(self, district="krishna", on_date="2026-11-24"):
        response = self.client.get("/api/evidence", params={
            "state_id": "andhra-pradesh", "district_id": district, "on_date": on_date,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def change(self, method, path, **params):
        return self.client.request(method, path, headers=HEADERS, **params)

    def test_admin_page_and_data_require_credentials_and_mutation_header(self):
        with TestClient(app) as unauthenticated:
            for route in ("/admin", BASE, f"{BASE}/example/original", "/api/admin/maintenance"):
                self.assertEqual(unauthenticated.get(route).status_code, 401)
            self.assertEqual(unauthenticated.get("/static/admin.html").status_code, 404)
        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(self.client.post(BASE, files={"file": ("x.txt", b"text")}).status_code, 403)

    def test_maintenance_expiry_and_verified_snapshot(self):
        seed(None)
        forecast_rows = maintenance_report(date(2026, 11, 28))["forecast_review"]
        self.assertEqual([(row["district_id"], row["status"]) for row in forecast_rows],
                         [("lgd-484", "expiring"), ("krishna", "expiring"), ("west-godavari", "expiring")])
        self.assertEqual({row["status"] for row in maintenance_report(date(2026, 11, 29))["forecast_review"]}, {"expired"})
        response = self.client.get("/api/admin/maintenance")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(row["id"] == "imd-value-added-ap-94-2026" and row["has_checksum"]
                            for row in response.json()["missing_snapshots"]))
        original = b"audited exact bytes"
        with evidence_db(write=True) as connection:
            connection.execute("UPDATE source_documents SET sha256 = ? WHERE id = ?",
                               (sha256(original).hexdigest(), "imd-value-added-ap-94-2026"))
        path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "forecast.pdf"
        path.write_bytes(b"replacement bytes")
        with self.assertRaises(ValueError):
            attach_snapshot("imd-value-added-ap-94-2026", path)
        path.write_bytes(original)
        attach_snapshot("imd-value-added-ap-94-2026", path)
        self.assertEqual(self.client.get(f"{BASE}/imd-value-added-ap-94-2026/original").content, original)

    def test_maintenance_counts_sessions_without_exposing_questions(self):
        request = {"state_id": "andhra-pradesh", "district_id": "krishna", "crop": "paddy",
                   "language": "en", "question": "What is my selling price? Private example."}
        result = self.client.post("/api/advisories", json=request).json()
        self.assertEqual(result["status"], "insufficient_evidence")
        translated = self.client.post("/api/advisories", json={
            "session_id": result["session_id"], "translate_advisory_id": result["advisory_id"], "language": "te",
        })
        self.assertEqual(translated.status_code, 200)
        report = self.client.get("/api/admin/maintenance")
        self.assertNotIn("Private example", report.text)
        self.assertEqual(report.json()["coverage_gaps"], [{
            "state_id": "andhra-pradesh", "district_id": "krishna", "crop": "paddy", "crop_stage": "unknown",
            "topic": "unclassified", "sessions": 1,
        }])

    def test_inventory_separates_statewide_crop_guidance_and_district_forecasts(self):
        seed(None)
        report = maintenance_report(date(2026, 11, 25))["national_coverage"]
        districts = {row["district_id"]: row for state in report["states"] for row in state["districts"]}
        self.assertEqual(report["summary"]["state_count"], 36)
        self.assertEqual(report["summary"]["district_count"], len(districts))
        self.assertEqual(report["summary"]["districts_with_local_crop_guidance"], 3)
        self.assertEqual(report["summary"]["districts_with_reviewed_rainfall"], 3)
        self.assertEqual(districts["lgd-484"]["reviewed_rainfall"], "reviewed")
        self.assertEqual(districts["lgd-484"]["local_crop_ids"], ["paddy"])
        self.assertEqual(districts["lgd-569"]["local_crop_ids"], [])
        self.assertIn("tomato", districts["lgd-569"]["usable_crop_ids"])
        with evidence_db(write=True) as connection:
            connection.execute("UPDATE source_documents SET status = 'archived' WHERE id = 'imd-nagpur-2026-11-23'")
        archived = maintenance_report(date(2026, 11, 25))["national_coverage"]["summary"]
        self.assertEqual(archived["districts_with_local_crop_guidance"], 2)
        self.assertEqual(archived["districts_with_reviewed_rainfall"], 2)
        expired = maintenance_report(date(2026, 11, 29))["national_coverage"]["summary"]
        self.assertEqual(expired["districts_with_reviewed_rainfall"], 0)

    def test_scanned_pdf_remains_draft_and_original_is_preserved(self):
        pdf = PdfWriter()
        pdf.add_blank_page(width=200, height=200)
        output = io.BytesIO()
        pdf.write(output)
        data = output.getvalue()
        response = self.change("POST", BASE, files={"file": ("scan.pdf", data, "application/pdf")})
        self.assertEqual(response.status_code, 201, response.text)
        source = response.json()
        passage = source["passages"][0]
        self.assertEqual(passage["page_number"], 1)
        self.assertEqual(passage["extracted_text"], "")
        self.assertIn("transcribe", passage["extraction_note"])
        self.assertFalse(passage["reviewed"])
        path = f'{BASE}/{source["id"]}'
        self.assertEqual(self.client.get(path + "/original").content, data)
        self.assertEqual(self.change("POST", path + "/publish", json={"revision": source["revision"]}).status_code, 422)

    def test_draft_edit_review_publish_and_archive(self):
        upload = self.change("POST", BASE, files={"file": ("evidence.txt", "పొలం".encode("utf-8"), "text/plain")})
        self.assertEqual(upload.status_code, 201, upload.text)
        source = upload.json()
        path = f'{BASE}/{source["id"]}'
        payload = {
            "revision": source["revision"],
            "metadata": {
                "publisher": "Test extension office", "title": "Test paddy note",
                "original_url": "https://example.org/paddy", "language": "te", "state_id": "andhra-pradesh",
                "issue_date": "2026-11-20", "valid_from": "2026-11-23", "valid_until": "2026-11-25",
                "geographic_scope": "Krishna only", "version": "1", "source_verified": True,
                "review_notes": "Original and metadata checked for test.",
            },
            "passages": [{
                "id": source["passages"][0]["id"], "district_id": "krishna", "kind": "advisory",
                "crop": "paddy", "topic": "irrigation", "crop_stage": "Milk to grain hardening",
                "section": "Example section", "content": "Reviewed Telugu passage paraphrase",
                "include": True, "reviewed": False, "review_notes": "Checked the original page.",
            }],
        }
        draft = self.change("PUT", path, json=payload)
        self.assertEqual(draft.status_code, 200, draft.text)
        revision = draft.json()["revision"]
        self.assertEqual(self.published()["passages"], [])
        self.assertEqual(self.change("POST", path + "/publish", json={"revision": revision}).status_code, 422)
        self.assertEqual(self.change("PUT", path, json=payload).status_code, 409)
        payload["revision"] = revision
        payload["passages"][0]["reviewed"] = True
        draft = self.change("PUT", path, json=payload)
        approved = self.change("POST", path + "/publish", json={"revision": draft.json()["revision"]})
        self.assertEqual(approved.status_code, 200, approved.text)
        evidence = self.published()
        self.assertFalse(evidence["covered"])
        self.assertEqual(evidence["passages"][0]["section"], "Example section")
        self.assertEqual(evidence["passages"][0]["language"], "te")
        self.assertEqual(self.published("west-godavari")["passages"], [])
        archived = self.change("POST", path + "/archive", json={"revision": approved.json()["revision"]})
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(self.published()["passages"], [])
        self.assertEqual(self.client.get(path).json()["passages"][0]["status"], "approved")
        self.assertEqual(self.client.get(path + "/original").status_code, 200)

    def test_reviewed_seed_covers_only_verified_date_overlap(self):
        seed(None)
        seed(None)
        sources = self.client.get(BASE).json()
        self.assertEqual(sum(source["state_id"] == "andhra-pradesh" for source in sources), 3)
        for district in ("krishna", "west-godavari"):
            for on_date, expected in (("2026-11-23", False), ("2026-11-24", True), ("2026-11-25", True), ("2026-11-26", False)):
                with self.subTest(district=district, on_date=on_date):
                    result = self.published(district, on_date)
                    self.assertEqual(result["covered"], expected)
                    self.assertTrue(all(p["district_id"] == district and p["page_number"] for p in result["passages"]))
        source = self.client.get(BASE + "/imd-value-added-ap-94-2026").json()
        response = self.change("POST", BASE + "/imd-value-added-ap-94-2026/archive", json={"revision": source["revision"]})
        self.assertEqual(response.status_code, 200, response.text)
        seed(None)
        self.assertFalse(self.published()["covered"])
