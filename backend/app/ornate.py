"""Narrow adapter for supplied Ornate report; no formulas or macros execute."""

import hashlib
import io
import json
import os
import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import xlrd

from .importer import MAX_BYTES, amount
from .models import Snapshot, SourceRow
from .rules import Rules

REPORT_HEADERS = {
    0: "Label No",
    2: "Vou Date",
    3: "Prefix",
    4: "Carat",
    5: "Days",
    6: "Gross Wt",
    7: "Net Wt",
    8: "Pcs",
    12: "Supplier Name",
    13: "Variety Name",
    19: "Closing Value",
}


def read_report(content):
    if len(content) > MAX_BYTES:
        raise ValueError("Workbook exceeds 15 MB")
    try:
        wb = xlrd.open_workbook(file_contents=content, logfile=io.StringIO())
    except xlrd.XLRDError as e:
        raise ValueError("Provide a valid legacy Ornate .xls stock report") from e
    if wb.nsheets != 1:
        raise ValueError("The verified Ornate profile expects one report sheet")
    ws = wb.sheet_by_index(0)
    if ws.nrows > 30000 or ws.ncols != 22:
        raise ValueError(
            "Ornate report layout differs from the verified 22-column export"
        )
    header_index = next(
        (
            i
            for i in range(min(ws.nrows, 30))
            if all(
                str(ws.cell_value(i, k)).strip() == v for k, v in REPORT_HEADERS.items()
            )
        ),
        None,
    )
    if header_index is None:
        raise ValueError("Ornate report headers do not match the verified profile")
    title = " ".join(str(ws.cell_value(i, 0)) for i in range(header_index))
    match = re.search(r"As On Date\s*:\s*(\d{2})/(\d{2})/(\d{4})", title)
    if not match:
        raise ValueError("Report has no explicit As On Date")
    day, month, year = map(int, match.groups())
    as_of = date(year, month, day).isoformat()
    branch, rows, totals, markers = None, [], {}, []
    for i in range(header_index + 1, ws.nrows):
        values = ws.row_values(i)
        marker = re.search(r"RIGHT GOLD\s*\[([^]]+)\]", str(values[0]), re.I)
        if marker:
            branch = marker.group(1).strip().upper()
            markers.append(branch)
            continue
        if isinstance(values[1], str) and "/" in values[1]:
            if branch is None:
                raise ValueError(f"Row {i + 1}: no branch section")
            rows.append((i + 1, branch, values))
        elif any(values) and values[19] != "":
            if values[2] != "":
                totals.update(
                    report_total_labels=int(values[2]),
                    report_closing_value=str(values[19]),
                    report_net_weight_g=str(values[7]),
                )
            else:
                totals.setdefault("branch_closing_value", {})[branch] = str(values[19])
    if len(rows) != totals.get("report_total_labels"):
        raise ValueError("Parsed label count does not match the report grand total")
    for location in markers:
        closing = sum(Decimal(str(r[19])) for _, b, r in rows if b == location)
        if location not in totals.get("branch_closing_value", {}) or abs(
            closing - Decimal(totals["branch_closing_value"][location])
        ) > Decimal("0.01"):
            raise ValueError(
                f"{location}: source closing-value total does not reconcile"
            )
    net = sum(Decimal(str(r[7])) for _, _, r in rows)
    if abs(net - Decimal(totals["report_net_weight_g"])) > Decimal("0.001"):
        raise ValueError("Source net-weight grand total does not reconcile")
    totals["source_controls_verified"] = True
    return wb, ws, rows, totals, markers, as_of, header_index


def inspect_ornate(content):
    _, ws, rows, totals, markers, as_of, header = read_report(content)
    return {
        "profile": "ornate_closing_stock_v1",
        "sheets": [
            {
                "name": ws.name,
                "headers": [v for v in ws.row_values(header) if v],
                "estimated_rows": len(rows),
            }
        ],
        "as_of": as_of,
        "counts": dict(Counter(b for _, b, _ in rows)),
        "branch_sections": markers,
        "report_totals": totals,
        "notes": [
            "CZ is a variety, not a branch.",
            "Days and Vou Date are retained separately.",
            "Closing Value requires explicit landed-cost confirmation.",
            "Each label remains indivisible irrespective of Pcs.",
        ],
    }


def retain(content, extension):
    digest = hashlib.sha256(content).hexdigest()
    path = (
        Path(os.getenv("RG_DATA_DIR", "/workspace/dhruva/data"))
        / "sources"
        / f"{digest}.{extension}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    return digest, str(path)


def ornate_preview(
    db,
    content,
    filename,
    actor,
    closing_value_is_landed_cost=False,
    reported_days_is_original_age=False,
    ho_is_usable=False,
):
    wb, ws, rows, totals, markers, as_of, header = read_report(content)
    digest, path = retain(content, "xls")
    errors, warnings, parsed, seen = [], [], [], set()
    for number, branch, r in rows:
        label = r[1].strip()
        code = str(r[4]).upper()
        material = (
            "lab_diamond"
            if code in ("14-LG", "18-LG")
            else "natural_diamond"
            if code in ("14K-D", "18K-D")
            else "gold"
            if code in ("9K-G", "14K-G", "18K-G", "22K-G", "999")
            else "out_of_scope"
        )
        karat = re.match(r"(\d+)", code)
        try:
            days = int(r[5])
            if days < 0 or days != float(r[5]):
                raise ValueError("Reported Days must be a nonnegative integer")
            original = (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()
            voucher = xlrd.xldate_as_datetime(r[2], wb.datemode).date().isoformat()
            if label in seen:
                errors.append(
                    {
                        "row": number,
                        "field": "label_id",
                        "message": "Duplicate label identifier",
                    }
                )
            seen.add(label)
            if branch not in ("AR", "HO", "LN", "NV", "RO", "IK"):
                errors.append(
                    {
                        "row": number,
                        "field": "branch",
                        "message": "Unknown branch section",
                    }
                )
            facts = {
                "label_id": label,
                "branch": branch,
                "material": material,
                "item": re.sub(r"\d+$", "", str(r[3])).upper(),
                "karatage": f"{karat.group(1)}KT" if karat else code,
                "variety": str(r[13]).strip() or "UNCLASSIFIED",
                "supplier": str(r[12]).strip() or "UNCLASSIFIED",
                "received_at": original,
                "reported_age_days": days,
                "age_basis": "as_of minus reported Days"
                if reported_days_is_original_age
                else "unverified reported Days",
                "age_verified": reported_days_is_original_age,
                "voucher_date": voucher,
                "usable": ho_is_usable if branch == "HO" else False,
                "usability_verified": ho_is_usable if branch == "HO" else False,
                "set_id": None,
                "set_size": None,
                "physical_pieces": amount(r[8]),
                "weight_g": amount(r[7]),
                "gross_weight_g": amount(r[6]),
                "carats": None,
                "metal_cost": None,
                "stone_cost": None,
                "other_cost": None,
                "landed_cost": amount(r[19]) if closing_value_is_landed_cost else None,
                "source_closing_value": amount(r[19]),
                "selling_price": amount(r[17]),
                "net_sale_value": None,
                "source_stone_weight": amount(r[11]),
                "source_carat_code": str(r[4]),
            }
            parsed.append((number, {str(k): v for k, v in enumerate(r)}, facts))
        except (ValueError, TypeError, OverflowError) as e:
            errors.append({"row": number, "field": "source", "message": str(e)})
    if not reported_days_is_original_age:
        warnings.append(
            {
                "message": "Original label age awaits confirmation; ageing from reported Days is provisional"
            }
        )
    if not closing_value_is_landed_cost:
        warnings.append(
            {
                "message": "Closing Value cost basis unconfirmed; landed cost remains unknown"
            }
        )
    if not ho_is_usable:
        warnings.append(
            {
                "message": "HO commitments/usability unconfirmed; no HO stock automatically available"
            }
        )
    warnings.append(
        {
            "message": "Stone Wt unit and net sale value basis unconfirmed; carats and margin estimates remain unknown"
        }
    )
    warnings.append(
        {
            "message": "Other materials retained out of scope: "
            + str(sum(f["material"] == "out_of_scope" for _, _, f in parsed))
        }
    )
    s = Snapshot(
        kind="stock",
        filename=Path(filename).name,
        sha256=digest,
        blob_path=path,
        as_of=as_of,
        mapping={
            "profile": "ornate_closing_stock_v1",
            "source_columns": {str(k): v for k, v in REPORT_HEADERS.items()},
            "report_totals": totals,
            "branch_sections": markers,
            "confirmed_by": actor,
            "closing_value_is_landed_cost": closing_value_is_landed_cost,
            "reported_days_is_original_age": reported_days_is_original_age,
            "ho_is_usable": ho_is_usable,
        },
        errors=errors,
        warnings=warnings,
        coverage={},
    )
    db.add(s)
    db.flush()
    db.add_all(
        SourceRow(snapshot_id=s.id, row_number=n, raw=r, facts=f) for n, r, f in parsed
    )
    return s


def planning_rules(content, parent_config):
    # Literal inputs only. Formula text is retained for review, never calculated.
    from .importer import workbook

    wb = workbook(content)
    try:
        if not {
            "Master Rules",
            "Weight Master",
            "Karat Mix",
            "Variety Mix",
            "Branch Setup",
        }.issubset(wb.sheetnames):
            raise ValueError("Planning workbook lacks the verified master sheets")
        config = json.loads(json.dumps(parent_config))
        bands, items, karats, varieties = [], set(), set(), set()
        for row in wb["Weight Master"].iter_rows(min_row=2, values_only=True):
            if not row[1]:
                continue
            item, variety, light, medium = row[1:5]
            if not isinstance(light, (int, float)) or not isinstance(
                medium, (int, float)
            ):
                raise ValueError("Weight bands must be literal numbers")
            bands.append(
                {
                    "item": str(item),
                    "variety": str(variety),
                    "light_max_g": light,
                    "medium_max_g": medium,
                    "basis": str(row[5]),
                    "notes": str(row[6] or ""),
                }
            )
            items.add(str(item))
            varieties.add(str(variety))
        for row in wb["Karat Mix"].iter_rows(min_row=5, values_only=True):
            if isinstance(row[2], (int, float)):
                karats.add(f"{int(row[2])}KT")
        controls = {}
        for sheet, first in [
            ("Master Rules", 9),
            ("Karat Mix", 4),
            ("Variety Mix", 4),
            ("Branch Setup", 5),
        ]:
            raw = []
            for row in wb[sheet].iter_rows(min_row=first, values_only=True):
                if any(v is not None for v in row):
                    raw.append(
                        [
                            v.isoformat()
                            if hasattr(v, "isoformat")
                            else v
                            if isinstance(v, (str, int, float, bool, type(None)))
                            else str(v)
                            for v in row
                        ]
                    )
                if len(raw) > 1000:
                    raise ValueError("Master sheet exceeds row limit")
            controls[sheet] = {
                "header_row": first,
                "rows": raw,
                "formula_policy": "source text only; not executed",
            }
        config["masters"] = {
            "items": sorted(items),
            "karatages": sorted(karats),
            "varieties": sorted(varieties),
            "suppliers": [],
            "lmh": bands,
        }
        config["master_controls"] = {
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "controls": controls,
            "notes": "Literal L/M/H bands are provisional. Mix formulas retained for review; supplier master absent. Prior proposals are not execution records.",
        }
        config["notes"] += (
            " Workbook L/M/H bands are provisional; supplier master and current control totals require review."
        )
        return Rules.model_validate(config).model_dump()
    finally:
        wb.close()
