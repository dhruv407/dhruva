import os
from pathlib import Path

import pytest
from app.analysis import demand_data, inventory, is_cz
from app.db import SessionLocal
from app.models import SourceRow
from app.optimizer import solve
from app.ornate import inspect_ornate, ornate_preview, planning_rules
from app.rules import fresh_defaults
from sqlalchemy import select

STOCK = Path(
    os.getenv(
        "RG_STOCK_FIXTURE",
        "/workspace/attachments/0ae7ea1d-ce39-43b8-ae6d-cac6b66be35c/ALLSTOCK1410.xls",
    )
)
MASTER = Path(
    os.getenv(
        "RG_MASTER_FIXTURE",
        "/workspace/attachments/ac16237a-d7b3-4ba5-be58-7fb814604e8f/Right Gold — Stock Planning & Reorder.xlsx",
    )
)


@pytest.mark.skipif(
    not STOCK.exists(), reason="Real user stock attachment not available"
)
def test_real_ornate_source_controls_and_unknown_assumptions(client):
    content = STOCK.read_bytes()
    info = inspect_ornate(content)
    assert info["counts"] == {"AR": 2791, "HO": 982, "LN": 3452, "NV": 4264, "RO": 2662}
    assert "IK" not in info["counts"]
    assert info["report_totals"]["report_total_labels"] == 14151
    assert info["report_totals"]["source_controls_verified"]
    with SessionLocal() as db:
        snap = ornate_preview(db, content, STOCK.name, "test")
        db.flush()
        rows = db.scalars(
            select(SourceRow).where(SourceRow.snapshot_id == snap.id)
        ).all()
        assert len(rows) == 14151
        assert not snap.errors
        assert all(r.facts["landed_cost"] is None for r in rows)
        assert all(r.facts["carats"] is None for r in rows)
        assert all(not r.facts["age_verified"] for r in rows)
        assert all(not r.facts["usable"] for r in rows)
        cz = next(r.facts for r in rows if r.facts["variety"] == "CZ")
        assert cz["branch"] == "AR"
        assert cz["received_at"] != cz["voucher_date"]
        assert cz["physical_pieces"] == "2.0"
        db.rollback()


@pytest.mark.skipif(
    not MASTER.exists(), reason="Real user planning attachment not available"
)
def test_real_master_workbook_literals_and_formula_preservation():
    r = planning_rules(MASTER.read_bytes(), fresh_defaults())
    assert len(r["masters"]["lmh"]) == 227
    assert len(r["masters"]["items"]) == 20
    assert r["masters"]["suppliers"] == []
    assert r["master_controls"]["source_sha256"]
    controls = r["master_controls"]["controls"]
    assert any(
        isinstance(v, str) and v.startswith("=")
        for row in controls["Master Rules"]["rows"]
        for v in row
    )
    assert (
        controls["Master Rules"]["formula_policy"] == "source text only; not executed"
    )


@pytest.mark.skipif(
    not STOCK.exists(), reason="Real user stock attachment not available"
)
def test_confirmed_full_export_solves_without_sparse_domain_presolve_timeout(client):
    with SessionLocal() as db:
        snapshot = ornate_preview(
            db, STOCK.read_bytes(), STOCK.name, "test confirmations", True, True, True
        )
        snapshot.coverage = {b: "complete" for b in ["NV", "LN", "AR", "RO", "HO"]}
        snapshot.coverage["IK"] = "confirmed_zero"
        snapshot.coverage["CZ"] = "missing"
        db.flush()
        facts = inventory(db, snapshot)
        result = solve(facts, snapshot, fresh_defaults(), demand_data(db, None))
        assert all(
            d["solver"] in ("OPTIMAL", "FEASIBLE") for d in result["diagnostics"]
        )
        assert len(result["proposals"]) == 749
        assert len(result["priority_recalls"]) == 434
        assert len(result["ho_cz_reuse"]) == 5
        original = {f["label_id"]: f for f in facts}
        for proposal in result["proposals"]:
            assert proposal["route"][0] == "HO"
            for label in proposal["labels"]:
                assert not is_cz(original[label])
                assert (
                    proposal["original_received_at"][label]
                    == original[label]["received_at"]
                )
        assert result["objectives"]["availability"].startswith("unavailable")
        assert not result["excluded"]
        db.rollback()
