from app.rules import fresh_defaults
from test_workflow import confirm, fact, import_data


def test_branch_exchange_requires_both_ho_legs_and_prevents_double_reservation(client):
    facts = [fact("EXCHANGE", "LN")]
    stock = import_data(client, facts)
    assert confirm(client, stock, facts).status_code == 200
    config = fresh_defaults()
    config["allow_branch_exchange"] = True
    rule = client.post(
        "/api/rules",
        json={
            "actor": "test",
            "name": "HO exchange test",
            "parent_id": 1,
            "config": config,
        },
    ).json()
    request = {"snapshot_id": stock["id"], "rule_id": rule["id"], "actor": "test"}
    first = client.post("/api/simulations", json=request).json()
    competing = client.post("/api/simulations", json=request).json()
    transfer = first["transfers"][0]
    assert transfer["route"] == ["LN", "HO", "NV"]
    assert (
        client.post(
            f"/api/simulations/{first['id']}/compare", json={"actor": "test"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/rules/{rule['id']}/approve", json={"actor": "test"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/rules/{rule['id']}/activate", json={"actor": "test"}
        ).status_code
        == 200
    )

    def act(t, action):
        return client.post(
            f"/api/transfers/{t['id']}/action",
            json={"actor": "test", "reference": "HO-LEG", "action": action},
        )

    assert act(transfer, "approve").status_code == 200
    assert act(competing["transfers"][0], "approve").status_code == 422
    assert act(transfer, "dispatch").status_code == 200
    receipt = act(transfer, "receive")
    assert receipt.status_code == 200
    assert receipt.json()["status"] == "at_ho" and receipt.json()["leg"] == 1
    assert client.get("/api/dashboard").json()["ageing"][0]["branch"] == "HO"
    other = import_data(client, facts)
    assert (
        confirm(client, other, facts, acknowledge_new_baseline=True).status_code == 422
    )
    assert act(transfer, "dispatch").status_code == 200
    assert client.get("/api/dashboard").json()["ageing"][0]["branch"] == "IN_TRANSIT"
    assert act(transfer, "receive").json()["status"] == "received"
    label = client.get("/api/dashboard").json()["ageing"][0]
    assert label["branch"] == "NV" and label["received_at"] == "2024-01-01"
