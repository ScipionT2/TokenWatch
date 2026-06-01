"""Export endpoint tests — CSV and JSON export of request history."""

import csv
import io
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from main import app
from src.services.request_logger import request_logger, RequestEntry


client = TestClient(app)


class TestExportJSON:
    def setup_method(self):
        request_logger.clear()
        for i in range(5):
            request_logger.log(RequestEntry(
                model=f"gpt-5" if i % 2 == 0 else "gpt-5-mini",
                prompt_tokens=100 * (i + 1),
                completion_tokens=50 * (i + 1),
                total_tokens=150 * (i + 1),
                cost_usd=0.001 * (i + 1),
                timestamp=datetime(2026, 4, 27, 10, i),
                request_id=f"req-{i}",
            ))

    def test_export_json_returns_all(self):
        r = client.get("/api/v1/export/json")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 5
        assert len(data["entries"]) == 5

    def test_export_json_filter_by_model(self):
        r = client.get("/api/v1/export/json", params={"model": "gpt-5-mini"})
        data = r.json()
        assert data["count"] == 2
        for entry in data["entries"]:
            assert "gpt-5-mini" in entry["model"]

    def test_export_json_filter_by_date_range(self):
        r = client.get("/api/v1/export/json", params={
            "start_date": "2026-04-27T10:01:00",
            "end_date": "2026-04-27T10:03:00",
        })
        data = r.json()
        assert data["count"] == 3

    def test_export_json_empty(self):
        request_logger.clear()
        r = client.get("/api/v1/export/json")
        data = r.json()
        assert data["count"] == 0
        assert data["entries"] == []

    def test_export_json_entry_fields(self):
        r = client.get("/api/v1/export/json")
        entry = r.json()["entries"][0]
        assert "model" in entry
        assert "prompt_tokens" in entry
        assert "completion_tokens" in entry
        assert "total_tokens" in entry
        assert "cost_usd" in entry
        assert "timestamp" in entry
        assert "request_id" in entry


class TestExportCSV:
    def setup_method(self):
        request_logger.clear()
        for i in range(3):
            request_logger.log(RequestEntry(
                model="gpt-5",
                prompt_tokens=100 * (i + 1),
                completion_tokens=50 * (i + 1),
                total_tokens=150 * (i + 1),
                cost_usd=0.001 * (i + 1),
                timestamp=datetime(2026, 4, 27, 10, i),
                request_id=f"csv-{i}",
            ))

    def test_export_csv_status(self):
        r = client.get("/api/v1/export/csv")
        assert r.status_code == 200

    def test_export_csv_content_type(self):
        r = client.get("/api/v1/export/csv")
        assert "text/csv" in r.headers["content-type"]

    def test_export_csv_content_disposition(self):
        r = client.get("/api/v1/export/csv")
        assert "attachment" in r.headers["content-disposition"]
        assert "tokenwatch_export.csv" in r.headers["content-disposition"]

    def test_export_csv_has_header(self):
        r = client.get("/api/v1/export/csv")
        reader = csv.reader(io.StringIO(r.text))
        header = next(reader)
        assert "model" in header
        assert "prompt_tokens" in header
        assert "cost_usd" in header
        assert "timestamp" in header

    def test_export_csv_has_data_rows(self):
        r = client.get("/api/v1/export/csv")
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        # 1 header + 3 data rows
        assert len(rows) == 4

    def test_export_csv_filter_by_model(self):
        # Add a different model
        request_logger.log(RequestEntry(
            model="o3", prompt_tokens=100, completion_tokens=50,
            total_tokens=150, cost_usd=0.002,
            timestamp=datetime(2026, 4, 27, 11, 0),
        ))
        r = client.get("/api/v1/export/csv", params={"model": "o3"})
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == 2  # header + 1 data row

    def test_export_csv_empty(self):
        request_logger.clear()
        r = client.get("/api/v1/export/csv")
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == 1  # header only

    def test_export_csv_parseable(self):
        """Ensure CSV is well-formed and parseable by DictReader."""
        r = client.get("/api/v1/export/csv")
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == 3
        for row in rows:
            assert row["model"] == "gpt-5"
            assert float(row["cost_usd"]) > 0
