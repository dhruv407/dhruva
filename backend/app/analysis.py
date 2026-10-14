from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from .importer import cost_paise
from .models import Simulation, SourceRow, Transfer
from .rules import LOCATIONS, MATERIALS


def segment(f):
    return (f["material"], f["item"], f["karatage"], f["variety"])


def is_cz(f):
    return f.get("variety", "").strip().upper() == "CZ" or f.get("branch") == "CZ"


def grade_for(f, config):
    for rule in config["masters"]["lmh"]:
        if all(
            str(rule.get(k, "*")).upper() in ("*", str(f.get(k, "")).upper())
            for k in ("item", "variety", "karatage", "supplier")
        ):
            if "light_max_g" in rule:
                if f.get("weight_g") is None:
                    return None
                weight = Decimal(f["weight_g"])
                return (
                    "L"
                    if weight <= Decimal(str(rule["light_max_g"]))
                    else "M"
                    if weight <= Decimal(str(rule["medium_max_g"]))
                    else "H"
                )
            return rule.get("class")
    return None


def inventory(db, snapshot):
    facts = [
        dict(r.facts)
        for r in db.scalars(
            select(SourceRow).where(SourceRow.snapshot_id == snapshot.id)
        )
    ]
    by_label = {f["label_id"]: f for f in facts}
    transfers = db.scalars(
        select(Transfer)
        .join(Simulation)
        .where(Simulation.snapshot_id == snapshot.id, Transfer.status != "proposed")
        .order_by(Transfer.id)
    ).all()
    for t in transfers:
        location = (
            "IN_TRANSIT"
            if t.status == "dispatched"
            else (t.route[-1] if t.status == "received" else t.route[t.leg])
        )
        for label in t.labels:
            if label in by_label:
                by_label[label]["branch"] = location
                if t.status in ("approved", "dispatched", "at_ho"):
                    by_label[label]["reserved"] = True
    return facts


def demand_data(db, sales):
    demand, profit = defaultdict(int), defaultdict(list)
    if sales is None:
        return {"days": None, "demand": demand, "profit": profit, "coverage": {}}
    days = (
        date.fromisoformat(sales.as_of)
        - date.fromisoformat(sales.reconciliation["history_start"])
    ).days + 1
    for row in db.scalars(select(SourceRow).where(SourceRow.snapshot_id == sales.id)):
        f = row.facts
        key = (f["branch"], segment(f))
        demand[key] += 1
        if f.get("buying_cost") is not None:
            profit[key].append(
                int((Decimal(f["selling_price"]) - Decimal(f["buying_cost"])) * 100)
            )
    return {
        "days": days,
        "demand": demand,
        "profit": profit,
        "coverage": sales.coverage,
    }


def margin_for(f, config):
    matches = [
        r
        for r in config["margins"]
        if r["material"] == f["material"]
        and r["karatage"] in ("*", f["karatage"])
        and r["variety"].lower() == f["variety"].lower()
    ]
    return matches[0] if matches else None


def estimated_margin_paise(f, config):
    r = margin_for(f, config)
    if not r or not r["confirmed"] or not r["basis"]:
        return None
    pct = Decimal(str(r["percent"])) / 100
    cost = cost_paise(f)
    if r["basis"] == "net_sale_value":
        return (
            None
            if f.get("net_sale_value") is None
            else int(Decimal(f["net_sale_value"]) * 100 * pct)
        )
    if r["basis"] == "cost_markup":
        return None if cost is None else int(Decimal(cost) * pct)
    return (
        None
        if f.get("selling_price") is None
        else int(Decimal(f["selling_price"]) * 100 * pct)
    )


def summarize(facts, snapshot, config, demand):
    locations = LOCATIONS + ["IN_TRANSIT"]
    result = []
    for material in MATERIALS:
        known = [
            f
            for f in facts
            if f["material"] == material and f["branch"] in config["targets"]
        ]
        denominator = sum(cost_paise(f) or 0 for f in known)
        weight_denominator = sum(Decimal(f.get("weight_g") or "0") for f in known)
        for location in locations:
            selected = [
                f
                for f in facts
                if f["branch"] == location and f["material"] == material
            ]
            status = snapshot.coverage.get(
                location, "complete" if location == "IN_TRANSIT" else "missing"
            )
            source_coverage = status
            if selected and status == "confirmed_zero":
                status = "complete"
            if status == "missing":
                result.append(
                    {
                        "branch": location,
                        "material": material,
                        "coverage": status,
                        "labels": None,
                        "cost_paise": None,
                        "aged_cost_paise": None,
                        "aged_percent": None,
                        "actual_share": None,
                        "unknown_cost_labels": None,
                        "weight_g": None,
                        "carats": None,
                        "unit_turns_proxy": None,
                        "sales_history": demand["coverage"].get(location, "missing"),
                    }
                )
                continue
            costs = [cost_paise(f) for f in selected]
            cost = sum(v for v in costs if v is not None)
            weight = sum(Decimal(f.get("weight_g") or "0") for f in selected)
            aged = [
                f
                for f in selected
                if (
                    date.fromisoformat(snapshot.as_of)
                    - date.fromisoformat(f["received_at"])
                ).days
                >= config["age_days"]
            ]
            aged_cost = sum(cost_paise(f) or 0 for f in aged)
            unknown = sum(v is None for v in costs)
            history_known = demand["coverage"].get(location) in (
                "complete",
                "confirmed_zero",
            )
            annual = (
                sum(
                    v
                    for (b, s), v in demand["demand"].items()
                    if b == location and s[0] == material
                )
                * 365
                / demand["days"]
                if demand["days"] and history_known
                else None
            )
            result.append(
                {
                    "branch": location,
                    "material": material,
                    "coverage": status,
                    "labels": len(selected),
                    "source_coverage": source_coverage,
                    "cost_paise": None if unknown else cost,
                    "known_cost_paise": cost,
                    "aged_labels": len(aged),
                    "aged_cost_paise": None
                    if any(cost_paise(f) is None for f in aged)
                    else aged_cost,
                    "aged_percent": round(100 * aged_cost / cost, 2)
                    if cost and not unknown
                    else None,
                    "actual_share": (
                        round(float(100 * weight / weight_denominator), 2)
                        if weight_denominator
                        and all(f.get("weight_g") is not None for f in known)
                        and all(
                            snapshot.coverage.get(b) != "missing"
                            for b in config["targets"]
                        )
                        else None
                    )
                    if config.get("target_basis", {}).get(material) == "weight_g"
                    else (
                        round(100 * cost / denominator, 2)
                        if denominator
                        and not any(cost_paise(f) is None for f in known)
                        and all(
                            snapshot.coverage.get(b) != "missing"
                            for b in config["targets"]
                        )
                        else None
                    ),
                    "target_basis": config.get("target_basis", {}).get(
                        material, "cost"
                    ),
                    "unknown_cost_labels": unknown,
                    "weight_g": None
                    if any(f.get("weight_g") is None for f in selected)
                    else str(sum(Decimal(f.get("weight_g") or "0") for f in selected)),
                    "carats": None
                    if any(f.get("carats") is None for f in selected)
                    else str(sum(Decimal(f.get("carats") or "0") for f in selected)),
                    "unit_turns_proxy": round(annual / len(selected), 2)
                    if annual is not None and selected
                    else None,
                    "sales_history": demand["coverage"].get(location, "missing"),
                }
            )
    return result


def ageing_rows(facts, snapshot, config):
    result = []
    for f in facts:
        age = (
            date.fromisoformat(snapshot.as_of) - date.fromisoformat(f["received_at"])
        ).days
        cost = cost_paise(f)
        result.append(
            {
                **f,
                "age_days": age,
                "age_bucket": "0–90"
                if age <= 90
                else "91–180"
                if age <= 180
                else "181–365"
                if age <= 365
                else "365+",
                "cost_paise": cost,
                "priority": "CZ recall / reuse"
                if is_cz(f)
                else "Aged"
                if age >= config["age_days"]
                else "Current",
                "lmh_class": grade_for(f, config),
                "margin_estimate_paise": estimated_margin_paise(f, config),
            }
        )
    return sorted(
        result, key=lambda f: (not is_cz(f), -f["age_days"], -(f["cost_paise"] or 0))
    )
