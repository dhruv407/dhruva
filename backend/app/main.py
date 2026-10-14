import hashlib
import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .analysis import ageing_rows, demand_data, inventory, summarize
from .db import Base, engine, get_db
from .importer import (
    MAX_BYTES,
    SALES_OPTIONAL,
    SALES_REQUIRED,
    STOCK_OPTIONAL,
    STOCK_REQUIRED,
    excel_rows,
    inspect_workbook,
    preview,
    reconcile,
)
from .models import (
    AuditEvent,
    MovementEvent,
    RuleVersion,
    Simulation,
    Snapshot,
    SourceRow,
    Transfer,
)
from .optimizer import solve
from .ornate import inspect_ornate, ornate_preview, planning_rules, retain
from .rules import LOCATIONS, Rules, fresh_defaults


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        lock(db)
        if not db.scalar(select(RuleVersion.id).limit(1)):
            r = RuleVersion(name="Right Gold initial draft", config=fresh_defaults())
            db.add(r)
            db.flush()
            audit(
                db,
                "rule",
                r.id,
                "created",
                "setup",
                {"basis": "user-specified planning assumptions"},
            )
            db.commit()
    yield


app = FastAPI(title="RG Stock Engine", version="0.1.0", lifespan=lifespan)
DB = Annotated[Session, Depends(get_db)]


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def lock(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(40724016)"))


def audit(db, entity, id, action, actor, details=None):
    db.add(
        AuditEvent(
            entity=entity,
            entity_id=id,
            action=action,
            actor=actor,
            details=details or {},
        )
    )


def get(db, cls, id):
    result = db.get(cls, id)
    if result is None:
        raise HTTPException(404, "Record not found")
    return result


def latest(db, kind):
    return db.scalar(
        select(Snapshot)
        .where(Snapshot.kind == kind, Snapshot.status == "reconciled")
        .order_by(Snapshot.id.desc())
    )


def source(db, id, kind):
    s = get(db, Snapshot, id)
    if s.kind != kind or s.status != "reconciled":
        raise ValueError(f"Choose a reconciled {kind} snapshot")
    return s


def rules_for(db, id=None):
    return (
        get(db, RuleVersion, id)
        if id
        else (
            db.scalar(select(RuleVersion).where(RuleVersion.state == "active"))
            or db.scalar(select(RuleVersion).order_by(RuleVersion.id))
        )
    )


def snap_out(db, s):
    rows = db.scalars(select(SourceRow).where(SourceRow.snapshot_id == s.id)).all()
    counts = {}
    for r in rows:
        b = r.facts.get("branch", "invalid")
        counts[b] = counts.get(b, 0) + 1
    return {
        "id": s.id,
        "kind": s.kind,
        "filename": s.filename,
        "sha256": s.sha256,
        "as_of": s.as_of,
        "status": s.status,
        "mapping": s.mapping,
        "coverage": s.coverage,
        "errors": s.errors[:500],
        "error_count": len(s.errors),
        "warnings": s.warnings[:100],
        "warning_count": len(s.warnings),
        "row_count": len(rows),
        "counts": counts,
        "reconciliation": s.reconciliation,
        "sample_rows": [{"row": r.row_number, "facts": r.facts} for r in rows[:10]],
    }


def rule_out(r):
    return {
        "id": r.id,
        "parent_id": r.parent_id,
        "name": r.name,
        "state": r.state,
        "config": r.config,
    }


def sim_out(db, s):
    return {
        "id": s.id,
        "snapshot_id": s.snapshot_id,
        "sales_snapshot_id": s.sales_snapshot_id,
        "rule_id": s.rule_id,
        "status": s.status,
        "assumptions": s.assumptions,
        "result": s.result,
        "comparison": s.comparison,
        "transfers": [
            transfer_out(t)
            for t in db.scalars(
                select(Transfer)
                .where(Transfer.simulation_id == s.id)
                .order_by(Transfer.id)
            )
        ],
    }


def transfer_out(t):
    return {
        "id": t.id,
        "simulation_id": t.simulation_id,
        "group_key": t.group_key,
        "labels": t.labels,
        "route": t.route,
        "purpose": t.purpose,
        "leg": t.leg,
        "status": t.status,
    }


async def file_bytes(file, legacy=False):
    if (
        not (file.filename or "")
        .lower()
        .endswith((".xlsx", ".xls") if legacy else ".xlsx")
    ):
        raise ValueError("Upload .xlsx, or a verified Ornate stock .xls report")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("Workbook exceeds 15 MB")
    return content


class Actor(BaseModel):
    actor: str = Field(min_length=1, max_length=160)


class Reconciliation(Actor):
    coverage: dict[str, str]
    expected_counts: dict[str, int]
    expected_costs: dict[str, float] = {}
    note: str = Field(min_length=1, max_length=2000)
    history_start: str | None = None
    acknowledge_new_baseline: bool = False


class NewRules(Actor):
    name: str = Field(min_length=1, max_length=160)
    parent_id: int | None = None
    config: Rules


class SimulationRequest(Actor):
    snapshot_id: int
    sales_snapshot_id: int | None = None
    rule_id: int


class Movement(Actor):
    action: str
    reference: str = Field(min_length=1, max_length=160)


@app.get("/api/health")
def health(db: DB):
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": db.bind.dialect.name,
        "solver": "OR-Tools CP-SAT",
    }


@app.post("/api/imports/inspect")
async def inspect(file: UploadFile):
    if (file.filename or "").lower().endswith(".xls"):
        return inspect_ornate(await file_bytes(file, legacy=True))
    return inspect_workbook(await file_bytes(file))


@app.post("/api/imports/ornate")
async def import_ornate(
    db: DB,
    file: UploadFile,
    actor: Annotated[str, Form()],
    closing_value_is_landed_cost: Annotated[bool, Form()] = False,
    reported_days_is_original_age: Annotated[bool, Form()] = False,
    ho_is_usable: Annotated[bool, Form()] = False,
):
    if not actor.strip():
        raise ValueError("Operator identity is required for adapter assumptions")
    content = await file_bytes(file, legacy=True)
    lock(db)
    s = ornate_preview(
        db,
        content,
        file.filename,
        actor,
        closing_value_is_landed_cost,
        reported_days_is_original_age,
        ho_is_usable,
    )
    audit(db, "snapshot", s.id, "ornate_previewed", actor, s.mapping)
    db.commit()
    return snap_out(db, s)


@app.get("/api/imports/template/{kind}")
def template(kind: str):
    if kind not in ("stock", "sales", "masters"):
        raise ValueError("Unknown template kind")
    wb = Workbook()
    ws = wb.active
    ws.title = kind
    ws.append(
        STOCK_REQUIRED + STOCK_OPTIONAL
        if kind == "stock"
        else SALES_REQUIRED + SALES_OPTIONAL
        if kind == "sales"
        else ["type", "value", "item", "class", "karatage", "variety", "supplier"]
    )
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="rg-{kind}-template.xlsx"'
        },
    )


@app.post("/api/imports/preview")
async def import_preview(
    db: DB,
    file: UploadFile,
    kind: Annotated[str, Form()],
    sheet: Annotated[str, Form()],
    mapping: Annotated[str, Form()],
    as_of: Annotated[str, Form()],
):
    content = await file_bytes(file)
    lock(db)
    s = preview(db, content, file.filename, kind, sheet, json.loads(mapping), as_of)
    audit(db, "snapshot", s.id, "previewed", "import", {"sha256": s.sha256})
    db.commit()
    return snap_out(db, s)


@app.get("/api/snapshots")
def snapshots(db: DB):
    return [
        snap_out(db, s)
        for s in db.scalars(select(Snapshot).order_by(Snapshot.id.desc()))
    ]


@app.post("/api/snapshots/{id}/reconcile")
def confirm_snapshot(id: int, body: Reconciliation, db: DB):
    lock(db)
    s = get(db, Snapshot, id)
    if s.kind == "stock":
        in_transit = db.scalar(
            select(Transfer.id)
            .where(Transfer.status.in_(["dispatched", "at_ho"]))
            .limit(1)
        )
        if in_transit:
            raise ValueError(
                "Resolve all in-transit/HO-staged transfers before accepting a new physical baseline"
            )
        previous = latest(db, "stock")
        if previous and s.as_of < previous.as_of:
            raise ValueError("A physical baseline cannot supersede a newer stock date")
        if previous and not body.acknowledge_new_baseline:
            raise ValueError(
                "Acknowledge that this snapshot supersedes the physical baseline"
            )
    reconcile(
        s,
        db.scalars(select(SourceRow).where(SourceRow.snapshot_id == id)).all(),
        body.coverage,
        body.expected_counts,
        body.expected_costs,
        body.note,
        body.history_start,
    )
    audit(
        db,
        "snapshot",
        id,
        "reconciled",
        body.actor,
        {"note": body.note, "new_baseline": body.acknowledge_new_baseline},
    )
    db.commit()
    return snap_out(db, s)


@app.get("/api/rules")
def rule_list(db: DB):
    return [
        rule_out(r)
        for r in db.scalars(select(RuleVersion).order_by(RuleVersion.id.desc()))
    ]


@app.post("/api/rules")
def create_rule(body: NewRules, db: DB):
    lock(db)
    if body.parent_id:
        get(db, RuleVersion, body.parent_id)
    r = RuleVersion(
        parent_id=body.parent_id, name=body.name, config=body.config.model_dump()
    )
    db.add(r)
    db.flush()
    audit(db, "rule", r.id, "created", body.actor)
    db.commit()
    return rule_out(r)


@app.post("/api/rules/{id}/masters")
async def import_masters(
    id: int,
    db: DB,
    file: UploadFile,
    sheet: Annotated[str, Form()],
    mapping: Annotated[str, Form()],
    actor: Annotated[str, Form()],
):
    content = await file_bytes(file)
    columns = json.loads(mapping)
    headers, rows = excel_rows(content, sheet)
    if (
        not columns.get("type")
        or not columns.get("value")
        or any(v not in headers for v in columns.values())
    ):
        raise ValueError("Map type and value; L/M/H also uses item and class")
    lock(db)
    parent = get(db, RuleVersion, id)
    config = json.loads(json.dumps(parent.config))
    master = {k: [] for k in config["masters"]}
    for n, raw in rows:
        row = {k: raw.get(v) for k, v in columns.items()}
        kind = str(row.get("type", "")).strip()
        if kind not in master:
            raise ValueError(
                f"Row {n}: type must be items/karatages/varieties/suppliers/lmh"
            )
        if kind == "lmh":
            master[kind].append(
                {
                    k: str(v).strip()
                    for k, v in row.items()
                    if k not in ("type", "value") and v is not None
                }
            )
        else:
            if row.get("value") is None:
                raise ValueError(f"Row {n}: value is required")
            master[kind].append(str(row["value"]).strip())
    config["masters"] = master
    config = Rules.model_validate(config).model_dump()
    r = RuleVersion(parent_id=id, name=f"Masters import from v{id}", config=config)
    db.add(r)
    db.flush()
    # Retain the source workbook and its explicit mapping, without treating it as inventory.
    import os
    from pathlib import Path

    digest = hashlib.sha256(content).hexdigest()
    path = (
        Path(os.getenv("RG_DATA_DIR", "/workspace/dhruva/data"))
        / "sources"
        / f"{digest}.xlsx"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    audit(
        db,
        "rule",
        r.id,
        "masters_imported",
        actor,
        {"sha256": digest, "sheet": sheet, "mapping": columns, "rows": len(rows)},
    )
    db.commit()
    return rule_out(r)


@app.get("/api/dashboard")
def dashboard(
    db: DB,
    snapshot_id: int | None = None,
    rule_id: int | None = None,
    sales_snapshot_id: int | None = None,
):
    stock = source(db, snapshot_id, "stock") if snapshot_id else latest(db, "stock")
    r = rules_for(db, rule_id)
    if not stock:
        return {
            "snapshot_id": None,
            "rule_id": r.id,
            "rule_state": r.state,
            "targets": r.config["targets"],
            "branches": [],
            "ageing": [],
            "notice": "Import and reconcile stock to begin. Missing inventory is unknown, not zero.",
        }
    sales = (
        source(db, sales_snapshot_id, "sales")
        if sales_snapshot_id
        else latest(db, "sales")
    )
    facts = inventory(db, stock)
    d = demand_data(db, sales)
    warnings = [
        "Turnover is an annualised unit proxy, not financial turnover.",
        "Margin estimates use confirmed net sale value only; stone profit is not estimated.",
    ]
    unverified = [k for k, v in r.config["masters"].items() if not v]
    if unverified:
        warnings.append("Master rules not supplied: " + ", ".join(unverified))
    if not sales:
        warnings.append(
            "Historical sales unavailable; no fast-seller inference is made from label age."
        )
    warnings.extend(w["message"] for w in stock.warnings if "message" in w)
    master_fields = {
        "items": "item",
        "karatages": "karatage",
        "varieties": "variety",
        "suppliers": "supplier",
    }
    violations = [
        {"label_id": f["label_id"], "field": field, "value": f[field]}
        for key, field in master_fields.items()
        if r.config["masters"][key]
        for f in facts
        if f[field] not in r.config["masters"][key]
    ]
    return {
        "snapshot_id": stock.id,
        "source_sha256": stock.sha256,
        "as_of": stock.as_of,
        "sales_snapshot_id": sales.id if sales else None,
        "rule_id": r.id,
        "rule_state": r.state,
        "targets": r.config["targets"],
        "annual_turns_target": r.config["annual_turns"],
        "branches": summarize(facts, stock, r.config, d),
        "ageing": ageing_rows(facts, stock, r.config),
        "warnings": warnings,
        "master_violations": violations,
        "assumptions": r.config,
        "sales_metrics": [
            {
                "branch": b,
                "material": seg[0],
                "item": seg[1],
                "karatage": seg[2],
                "variety": seg[3],
                "sold_labels": n,
                "annualised_units": round(n * 365 / d["days"], 2),
                "realised_profit_paise": sum(d["profit"][(b, seg)])
                if len(d["profit"][(b, seg)]) == n
                else None,
                "cost_known_sales": len(d["profit"][(b, seg)]),
                "window_days": d["days"],
            }
            for (b, seg), n in d["demand"].items()
        ],
    }


@app.post("/api/rules/{id}/planning-workbook")
async def planning_workbook(
    id: int, db: DB, file: UploadFile, actor: Annotated[str, Form()]
):
    content = await file_bytes(file)
    lock(db)
    parent = get(db, RuleVersion, id)
    config = planning_rules(content, parent.config)
    digest, path = retain(content, "xlsx")
    r = RuleVersion(
        parent_id=id, name=f"Planning workbook masters · parent v{id}", config=config
    )
    db.add(r)
    db.flush()
    audit(
        db,
        "rule",
        r.id,
        "planning_workbook_imported",
        actor,
        {
            "sha256": digest,
            "source_file": file.filename,
            "literal_band_count": len(config["masters"]["lmh"]),
            "formula_policy": "not executed",
        },
    )
    db.commit()
    return rule_out(r)


@app.post("/api/simulations")
def simulate(body: SimulationRequest, db: DB):
    lock(db)
    stock = source(db, body.snapshot_id, "stock")
    if stock.id != latest(db, "stock").id:
        raise ValueError("Use the current physical stock snapshot for proposals")
    sales = (
        source(db, body.sales_snapshot_id, "sales") if body.sales_snapshot_id else None
    )
    if sales and sales.as_of > stock.as_of:
        raise ValueError(
            "Sales history ends after the stock snapshot; choose an aligned snapshot"
        )
    rule = get(db, RuleVersion, body.rule_id)
    facts = inventory(db, stock)
    if any(f.get("age_verified") is False for f in facts):
        raise ValueError(
            "Original label-age basis is unconfirmed; re-import after confirming reported Days"
        )
    for f in facts:
        for key, field in {
            "items": "item",
            "karatages": "karatage",
            "varieties": "variety",
            "suppliers": "supplier",
        }.items():
            if (
                rule.config["masters"][key]
                and f[field] not in rule.config["masters"][key]
            ):
                raise ValueError(
                    f"Label {f['label_id']}: {field} absent from selected rule master"
                )
    result = solve(facts, stock, rule.config, demand_data(db, sales))
    assumptions = {
        "rules": rule.config,
        "stock_sha256": stock.sha256,
        "sales_sha256": sales.sha256 if sales else None,
        "as_of": stock.as_of,
        "age_basis": "original received_at",
        "pool": "HO usable stock + branches"
        if rule.config["allow_branch_exchange"]
        else "HO usable stock only",
        "net_sale_margin_basis": "gold weight × current RG rate + making, from explicitly mapped net_sale_value",
        "stone_costs": "exported landed costs only; provisional ₹15k/₹7k per carat not substituted",
        "inventory_at_simulation": facts,
    }
    sim = Simulation(
        snapshot_id=stock.id,
        sales_snapshot_id=sales.id if sales else None,
        rule_id=rule.id,
        status="simulated",
        assumptions=assumptions,
        result=result,
    )
    db.add(sim)
    db.flush()
    for proposal in result["proposals"] + result["priority_recalls"]:
        db.add(
            Transfer(
                simulation_id=sim.id,
                group_key=proposal["group_key"],
                labels=proposal["labels"],
                route=proposal["route"],
                purpose=proposal["purpose"],
            )
        )
    if rule.state == "draft":
        rule.state = "simulated"
    audit(db, "simulation", sim.id, "simulated", body.actor)
    db.commit()
    return sim_out(db, sim)


@app.get("/api/simulations")
def simulations(db: DB):
    return [
        sim_out(db, s)
        for s in db.scalars(select(Simulation).order_by(Simulation.id.desc()))
    ]


@app.post("/api/simulations/{id}/compare")
def compare(id: int, body: Actor, db: DB):
    lock(db)
    sim = get(db, Simulation, id)
    active = db.scalar(select(RuleVersion).where(RuleVersion.state == "active"))
    stock = source(db, sim.snapshot_id, "stock")
    sales = (
        source(db, sim.sales_snapshot_id, "sales") if sim.sales_snapshot_id else None
    )
    base_config = active.config if active else fresh_defaults()
    baseline = solve(
        sim.assumptions["inventory_at_simulation"],
        stock,
        base_config,
        demand_data(db, sales),
    )
    sim.comparison = {
        "baseline_rule_id": active.id if active else None,
        "baseline_name": active.name
        if active
        else "Initial user-specified defaults (bootstrap baseline)",
        "baseline_config": base_config,
        "baseline_result": baseline,
        "candidate_rule_id": sim.rule_id,
        "proposal_count_delta": len(sim.result["proposals"])
        - len(baseline["proposals"]),
        "same_stock_snapshot": sim.snapshot_id,
        "same_sales_snapshot": sim.sales_snapshot_id,
    }
    sim.status = "compared"
    rule = get(db, RuleVersion, sim.rule_id)
    if rule.state in ("draft", "simulated"):
        rule.state = "compared"
    audit(
        db,
        "simulation",
        id,
        "compared",
        body.actor,
        {"baseline_rule_id": sim.comparison["baseline_rule_id"]},
    )
    db.commit()
    return sim_out(db, sim)


@app.post("/api/rules/{id}/{action}")
def transition_rule(id: int, action: str, body: Actor, db: DB):
    lock(db)
    r = get(db, RuleVersion, id)
    if action == "approve":
        compared = db.scalar(
            select(Simulation)
            .where(Simulation.rule_id == id, Simulation.status == "compared")
            .order_by(Simulation.id.desc())
        )
        if r.state != "compared" or not compared:
            raise ValueError("Simulate and compare this version before approval")
        if compared.snapshot_id != latest(db, "stock").id:
            raise ValueError(
                "Stock baseline changed; simulate and compare again before approval"
            )
        active = db.scalar(select(RuleVersion).where(RuleVersion.state == "active"))
        if compared.comparison["baseline_rule_id"] != (active.id if active else None):
            raise ValueError("Active baseline changed; compare again before approval")
        r.state = "approved"
    elif action == "activate":
        if r.state != "approved":
            raise ValueError("Approve this version before activation")
        compared = db.scalar(
            select(Simulation)
            .where(Simulation.rule_id == id, Simulation.status == "compared")
            .order_by(Simulation.id.desc())
        )
        active = db.scalar(select(RuleVersion).where(RuleVersion.state == "active"))
        if not compared or compared.comparison["baseline_rule_id"] != (
            active.id if active else None
        ):
            raise ValueError(
                "Active baseline changed; clone and compare the rule again"
            )
        if active:
            active.state = "retired"
        r.state = "active"
    else:
        raise ValueError("Action must be approve or activate")
    audit(db, "rule", id, action, body.actor)
    db.commit()
    return rule_out(r)


@app.get("/api/transfers")
def transfers(db: DB):
    return [
        transfer_out(t)
        for t in db.scalars(select(Transfer).order_by(Transfer.id.desc()))
    ]


@app.post("/api/transfers/{id}/action")
def movement(id: int, body: Movement, db: DB):
    lock(db)
    t = get(db, Transfer, id)
    sim = get(db, Simulation, t.simulation_id)
    stock = source(db, sim.snapshot_id, "stock")
    if body.action != "cancel" and latest(db, "stock").id != stock.id:
        raise ValueError("Proposal belongs to a superseded physical baseline")
    if body.action == "approve":
        if t.status != "proposed":
            raise ValueError("Transfer is already approved")
        if get(db, RuleVersion, sim.rule_id).state != "active":
            raise ValueError(
                "Activate the simulated rule version before approving execution"
            )
        pending = db.scalars(
            select(Transfer).where(
                Transfer.status.in_(["approved", "dispatched", "at_ho"])
            )
        ).all()
        if any(set(t.labels) & set(p.labels) for p in pending):
            raise ValueError("A label is reserved by another transfer")
        by_label = {f["label_id"]: f for f in inventory(db, stock)}
        original = {
            f["label_id"]: f for f in sim.assumptions["inventory_at_simulation"]
        }
        if any(
            label not in by_label
            or by_label[label]["branch"] != t.route[0]
            or by_label[label]["received_at"] != original[label]["received_at"]
            for label in t.labels
        ):
            raise ValueError("Physical inventory changed; simulate again")
        t.status = "approved"
    elif body.action == "dispatch":
        if t.status not in ("approved", "at_ho"):
            raise ValueError("Approve transfer or receive its HO leg before dispatch")
        t.status = "dispatched"
    elif body.action == "receive":
        if t.status != "dispatched":
            raise ValueError("Record dispatch before receipt")
        if t.leg == len(t.route) - 2:
            t.status = "received"
        else:
            t.leg += 1
            t.status = "at_ho"
    elif body.action == "cancel":
        if t.status not in ("proposed", "approved"):
            raise ValueError("Only undispatched transfers can be cancelled")
        t.status = "cancelled"
    else:
        raise ValueError("Action must be approve, dispatch, receive or cancel")
    event_leg = t.leg - 1 if body.action == "receive" and t.status == "at_ho" else t.leg
    db.add(
        MovementEvent(
            transfer_id=id,
            action=body.action,
            leg=event_leg,
            reference=body.reference,
            actor=body.actor,
        )
    )
    audit(
        db,
        "transfer",
        id,
        body.action,
        body.actor,
        {"reference": body.reference, "leg": event_leg},
    )
    db.commit()
    return transfer_out(t)


@app.get("/api/audit")
def audit_trail(db: DB):
    return [
        {
            "id": a.id,
            "entity": a.entity,
            "entity_id": a.entity_id,
            "action": a.action,
            "actor": a.actor,
            "details": a.details,
            "at": a.created_at.isoformat(),
        }
        for a in db.scalars(
            select(AuditEvent).order_by(AuditEvent.id.desc()).limit(500)
        )
    ]


class Command(BaseModel):
    command: str = Field(min_length=1, max_length=1000)


@app.get("/api/assistant/status")
def assistant_status():
    import os

    return {"configured": bool(os.getenv("RG_AI_API_KEY")), "local_interpreter": True}


@app.post("/api/assistant/ai")
async def ai_interpret(body: Command, db: DB):
    from .assistant import interpret_ai

    stock = latest(db, "stock")
    rule = rules_for(db)
    sales = latest(db, "sales")
    sim = db.scalar(select(Simulation).order_by(Simulation.id.desc()))
    context = {
        "provenance": {
            "snapshot_id": stock.id if stock else None,
            "source_sha256": stock.sha256 if stock else None,
            "sales_snapshot_id": sales.id if sales else None,
            "rule_id": rule.id,
            "rule_state": rule.state,
            "assumptions": rule.config,
        },
        "coverage": stock.coverage if stock else {},
        "source_warnings": stock.warnings if stock else [],
        "branch_health": summarize(
            inventory(db, stock), stock, rule.config, demand_data(db, sales)
        )
        if stock
        else [],
        "latest_simulation": {
            "id": sim.id,
            "snapshot_id": sim.snapshot_id,
            "rule_id": sim.rule_id,
            "objectives": sim.result["objectives"],
            "diagnostics": sim.result["diagnostics"],
            "limitations": sim.result["limitations"],
        }
        if sim
        else None,
    }
    return await interpret_ai(body.command, context)


@app.post("/api/assistant/interpret")
def interpret(body: Command):
    c = body.command.lower()
    view = (
        "ageing"
        if any(w in c for w in ("aged", "ageing", "old", "stuck", "cz"))
        else "proposals"
        if any(w in c for w in ("rebalance", "allocate", "transfer", "proposal"))
        else "rules"
        if "rule" in c
        else "imports"
        if "import" in c
        else "overview"
    )
    return {
        "view": view,
        "branch": next((b for b in LOCATIONS if b.lower() in c.split()), None),
        "material": "lab_diamond"
        if "lab" in c
        else "natural_diamond"
        if "diamond" in c
        else "gold"
        if "gold" in c
        else None,
        "explanation": "This local intent interpreter only navigates and filters. Python calculates inventory and OR-Tools simulates allocations. It cannot approve rules, dispatch stock or change source data.",
        "mode": "deterministic intent interpreter; external AI not connected",
    }


# Deployment serves the built React bundle and API on one origin. Development
# continues to use Vite; API routes are registered before the static mount.
web_dir = os.getenv("RG_WEB_DIR")
if web_dir:
    if not (Path(web_dir) / "index.html").is_file():
        raise RuntimeError("RG_WEB_DIR must contain the built frontend index.html")
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="frontend")
