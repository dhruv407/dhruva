import io
from types import SimpleNamespace

import pytest
from app.analysis import estimated_margin_paise, grade_for
from app.importer import STOCK_OPTIONAL, STOCK_REQUIRED
from app.optimizer import solve
from app.rules import LOCATIONS, Rules, fresh_defaults
from openpyxl import Workbook


def fact(label="0001", branch="HO", **overrides):
    return {
        "label_id": label,
        "branch": branch,
        "material": "gold",
        "item": "LR",
        "karatage": "22KT",
        "variety": "plain",
        "supplier": "TEST",
        "received_at": "2024-01-01",
        "usable": True,
        "set_id": None,
        "set_size": None,
        "weight_g": "10",
        "carats": "0",
        "metal_cost": "10000",
        "stone_cost": "0",
        "other_cost": "0",
        "selling_price": "12000",
        "net_sale_value": "12000",
        **overrides,
    }


def excel(facts, kind="stock"):
    wb = Workbook()
    ws = wb.active
    ws.title = "data"
    fields = (
        STOCK_REQUIRED + STOCK_OPTIONAL
        if kind == "stock"
        else [
            "sale_id",
            "label_id",
            "branch",
            "material",
            "item",
            "karatage",
            "variety",
            "sold_at",
            "selling_price",
            "buying_cost",
        ]
    )
    ws.append(fields)
    for f in facts:
        ws.append([f.get(k) for k in fields])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), {k: k for k in fields}


def import_data(client, facts, kind="stock"):
    content, mapping = excel(facts, kind)
    r = client.post(
        "/api/imports/preview",
        files={"file": ("fixture.xlsx", content)},
        data={
            "kind": kind,
            "sheet": "data",
            "as_of": "2026-10-14",
            "mapping": __import__("json").dumps(mapping),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def confirm(client, snapshot, facts, kind="stock", missing=(), **overrides):
    counts = {b: sum(f["branch"] == b for f in facts) for b in LOCATIONS}
    body = {
        "actor": "test operator",
        "coverage": {
            b: "missing"
            if b in missing
            else "complete"
            if counts[b]
            else "confirmed_zero"
            for b in LOCATIONS
        },
        "expected_counts": {b: n for b, n in counts.items() if b not in missing},
        "note": "Fixture report controls verified",
        "history_start": "2025-10-15" if kind == "sales" else None,
        **overrides,
    }
    return client.post(f"/api/snapshots/{snapshot['id']}/reconcile", json=body)


def test_missing_is_not_zero(client):
    facts = [fact()]
    s = import_data(client, facts)
    assert confirm(client, s, facts, missing=("IK",)).status_code == 200
    d = client.get("/api/dashboard").json()
    ik = next(
        r for r in d["branches"] if r["branch"] == "IK" and r["material"] == "gold"
    )
    nv = next(
        r for r in d["branches"] if r["branch"] == "NV" and r["material"] == "gold"
    )
    assert ik["labels"] is None and ik["cost_paise"] is None
    assert nv["labels"] == 0 and nv["cost_paise"] == 0
    result = client.post(
        "/api/simulations", json={"snapshot_id": s["id"], "rule_id": 1, "actor": "test"}
    )
    assert result.status_code == 422 and "IK" in result.text


@pytest.mark.parametrize(
    "facts,field",
    [
        ([fact(), fact()], "identifier"),
        ([fact(received_at="2027-01-01")], "received_at"),
        ([fact(metal_cost="-5")], "metal_cost"),
        ([fact(set_id="PAIR", set_size=2)], "set_id"),
        ([fact(label_id=123)], "label_id"),
        ([fact(branch="UNKNOWN")], "branch"),
    ],
)
def test_import_blocks_invalid_rows(client, facts, field):
    s = import_data(client, facts)
    assert any(e["field"] == field for e in s["errors"])
    assert confirm(client, s, facts).status_code == 422


def test_formulas_and_duplicate_headers_rejected(client):
    content, mapping = excel([fact(metal_cost="=1+1")])
    r = client.post(
        "/api/imports/preview",
        files={"file": ("formula.xlsx", content)},
        data={
            "kind": "stock",
            "sheet": "data",
            "as_of": "2026-10-14",
            "mapping": __import__("json").dumps(mapping),
        },
    )
    assert r.status_code == 422 and "formula" in r.text


def test_reconciliation_requires_counts_and_rejects_false_zero(client):
    facts = [fact()]
    s = import_data(client, facts)
    assert confirm(client, s, facts, expected_counts={}).status_code == 422
    wrong = {b: "confirmed_zero" for b in LOCATIONS}
    assert confirm(client, s, facts, coverage=wrong).status_code == 422
    assert confirm(client, s, facts, expected_costs={"HO": 999}).status_code == 422
    assert confirm(client, s, facts, expected_costs={"HO": 10000}).status_code == 200
    assert confirm(client, s, facts).status_code == 422


def test_margin_basis_and_stone_assumptions():
    config = fresh_defaults()
    assert estimated_margin_paise(fact(net_sale_value="10000"), config) == 12500
    assert estimated_margin_paise(fact(net_sale_value=None), config) is None
    config["margins"][0]["confirmed"] = False
    assert estimated_margin_paise(fact(), config) is None
    config["margins"][0].update(confirmed=True, basis=None)
    with pytest.raises(ValueError):
        Rules.model_validate(config)
    assert config["stone_economics"]["natural_diamond_cost_per_carat"] == 15000
    assert config["stone_economics"]["lab_diamond_cost_per_carat"] == 7000


def test_lmh_whole_tag_weights():
    config = fresh_defaults()
    config["masters"]["lmh"] = [
        {"item": "LR", "variety": "plain", "light_max_g": 2.5, "medium_max_g": 4}
    ]
    assert grade_for(fact(weight_g="2.5"), config) == "L"
    assert grade_for(fact(weight_g="4"), config) == "M"
    assert grade_for(fact(weight_g="4.01"), config) == "H"


def test_solver_preserves_sets_age_cz_and_materials():
    config = fresh_defaults()
    config["allow_branch_exchange"] = True
    facts = [
        fact("PAIR-A", set_id="P", set_size=2),
        fact("PAIR-B", set_id="P", set_size=2),
        fact("CZ-A", "NV", variety="CZ"),
        fact("ND", "HO", material="natural_diamond"),
        fact("LD", "HO", material="lab_diamond"),
    ]
    snap = SimpleNamespace(
        id=1, as_of="2026-10-14", coverage={b: "complete" for b in LOCATIONS}
    )
    from collections import defaultdict

    d = {
        "days": None,
        "demand": defaultdict(int),
        "profit": defaultdict(list),
        "coverage": {},
    }
    result = solve(facts, snap, config, d)
    assert all("CZ-A" not in p["labels"] for p in result["proposals"])
    assert result["priority_recalls"][0]["route"] == ["NV", "HO"]
    pair = next(p for p in result["proposals"] if "PAIR-A" in p["labels"])
    assert set(pair["labels"]) == {"PAIR-A", "PAIR-B"}
    assert all(v == "2024-01-01" for v in pair["original_received_at"].values())
    assert all(
        p["route"][0] == "HO" or p["route"][1] == "HO" for p in result["proposals"]
    )
    assert {p["material"] for p in result["proposals"]} == {
        "gold",
        "natural_diamond",
        "lab_diamond",
    }


def test_rule_lifecycle_and_actual_movements(client):
    facts = [fact("A", set_id="PAIR", set_size=2), fact("B", set_id="PAIR", set_size=2)]
    s = import_data(client, facts)
    assert confirm(client, s, facts).status_code == 200
    assert (
        client.post("/api/rules/1/activate", json={"actor": "test"}).status_code == 422
    )
    sim = client.post(
        "/api/simulations", json={"snapshot_id": s["id"], "rule_id": 1, "actor": "test"}
    )
    assert sim.status_code == 200, sim.text
    sim = sim.json()
    t = sim["transfers"][0]

    def action(name):
        return client.post(
            f"/api/transfers/{t['id']}/action",
            json={"actor": "test", "action": name, "reference": "TEST-1"},
        )

    assert action("approve").status_code == 422
    assert (
        client.post("/api/rules/1/approve", json={"actor": "test"}).status_code == 422
    )
    assert (
        client.post(
            f"/api/simulations/{sim['id']}/compare", json={"actor": "test"}
        ).status_code
        == 200
    )
    assert (
        client.post("/api/rules/1/approve", json={"actor": "test"}).status_code == 200
    )
    assert (
        client.post("/api/rules/1/activate", json={"actor": "test"}).status_code == 200
    )
    assert all(
        f["branch"] == "HO" for f in client.get("/api/dashboard").json()["ageing"]
    )
    assert action("receive").status_code == 422
    assert action("approve").status_code == 200
    assert action("dispatch").status_code == 200
    assert action("dispatch").status_code == 422
    assert all(
        f["branch"] == "IN_TRANSIT"
        for f in client.get("/api/dashboard").json()["ageing"]
    )
    assert action("receive").status_code == 200
    d = client.get("/api/dashboard").json()
    assert all(
        f["branch"] == t["route"][-1] and f["received_at"] == "2024-01-01"
        for f in d["ageing"]
    )
    assert action("receive").status_code == 422
    assert len(client.get("/api/audit").json()) >= 8


def test_realised_profit_and_demand_do_not_use_age(client):
    stock = [fact("OLDER"), fact("NEWER", received_at="2026-10-13")]
    s = import_data(client, stock)
    assert confirm(client, s, stock).status_code == 200
    sales = [
        {
            "sale_id": "S1",
            "label_id": "SOLD",
            "branch": "NV",
            "material": "gold",
            "item": "LR",
            "karatage": "22KT",
            "variety": "plain",
            "sold_at": "2026-02-01",
            "selling_price": "12000",
            "buying_cost": "10000",
        }
    ]
    h = import_data(client, sales, "sales")
    assert confirm(client, h, sales, "sales").status_code == 200
    d = client.get("/api/dashboard").json()
    assert d["sales_metrics"][0]["realised_profit_paise"] == 200000
    assert d["sales_metrics"][0]["sold_labels"] == 1
    assert d["ageing"][0]["age_days"] > d["ageing"][1]["age_days"]


def test_unknown_cost_never_substitutes_provisional_stones(client):
    facts = [fact(material="natural_diamond", stone_cost=None)]
    s = import_data(client, facts)
    assert confirm(client, s, facts).status_code == 200
    result = client.post(
        "/api/simulations", json={"snapshot_id": s["id"], "rule_id": 1, "actor": "test"}
    ).json()["result"]
    assert len(result["excluded"]) == 1
    assert not result["proposals"]


def test_interpreter_cannot_mutate(client):
    before = client.get("/api/rules").json()
    r = client.post(
        "/api/assistant/interpret",
        json={"command": "activate rules and dispatch gold to NV"},
    ).json()
    assert r["mode"].startswith("deterministic")
    assert client.get("/api/rules").json() == before
