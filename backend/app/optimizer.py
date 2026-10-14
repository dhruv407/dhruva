from collections import defaultdict
from datetime import date

from ortools.sat.python import cp_model

from .analysis import is_cz, margin_for, segment, summarize
from .importer import cost_paise
from .rules import BRANCHES, MATERIALS


def solve(facts, snapshot, config, demand):
    missing = [
        b
        for b in BRANCHES + ["HO"]
        if snapshot.coverage.get(b) not in ("complete", "confirmed_zero")
    ]
    if missing:
        raise ValueError(
            "Allocation blocked by missing branch data: " + ", ".join(missing)
        )
    # Rupee hundreds keep arithmetic bounded; every positive cost has at least one unit.
    groups = defaultdict(list)
    for f in facts:
        groups[
            "set:" + f["set_id"] if f.get("set_id") else "label:" + f["label_id"]
        ].append(f)
    before = summarize(facts, snapshot, config, demand)
    after_facts = [dict(f) for f in facts]
    after_by_id = {f["label_id"]: f for f in after_facts}
    proposals, excluded, diagnostics = [], [], []
    all_history = demand["days"] is not None and all(
        demand["coverage"].get(b) in ("complete", "confirmed_zero") for b in BRANCHES
    )
    for material in MATERIALS:
        model = cp_model.CpModel()
        assignments, sizes, age_costs, candidates, segments, target_sizes = (
            {},
            {},
            {},
            {},
            set(),
            {},
        )
        for key, members in groups.items():
            f = members[0]
            if f["material"] != material or f["branch"] not in BRANCHES + ["HO"]:
                continue
            if f["branch"] == "HO" and any(
                not m["usable"] or m.get("reserved") or is_cz(m) for m in members
            ):
                continue
            costs = [cost_paise(m) for m in members]
            if any(c is None for c in costs):
                excluded.append(
                    {
                        "group": key,
                        "labels": [m["label_id"] for m in members],
                        "reason": "Incomplete landed cost",
                    }
                )
                continue
            sizes[key] = max(1, round(sum(costs) / 10000))
            if config.get("target_basis", {}).get(material) == "weight_g":
                if any(m.get("weight_g") is None for m in members):
                    excluded.append(
                        {
                            "group": key,
                            "labels": [m["label_id"] for m in members],
                            "reason": "Weight unknown for weight-based target",
                        }
                    )
                    del sizes[key]
                    continue
                target_sizes[key] = max(
                    1, round(sum(float(m["weight_g"]) for m in members) * 100)
                )
            else:
                target_sizes[key] = sizes[key]
            aged = sum(
                c
                for m, c in zip(members, costs)
                if (
                    date.fromisoformat(snapshot.as_of)
                    - date.fromisoformat(m["received_at"])
                ).days
                >= config["age_days"]
            )
            age_costs[key] = min(sizes[key], round(aged / 10000))
            movable = all(
                m["usable"] and not m.get("reserved") and not is_cz(m) for m in members
            ) and (f["branch"] == "HO" or config["allow_branch_exchange"])
            destinations = [f["branch"]] + (
                [b for b in BRANCHES if b != f["branch"]] if movable else []
            )
            if f["branch"] == "HO" and movable:
                destinations = list(BRANCHES)
            candidates[key] = members
            segments.update(segment(m) for m in members)
            if len(destinations) == 1:
                assignments[key] = {destinations[0]: 1}
            else:
                assignments[key] = {
                    b: model.NewBoolVar(f"{key}:{b}") for b in destinations
                }
                model.AddExactlyOne(assignments[key].values())
        if not candidates:
            diagnostics.append(
                {"material": material, "solver": "NO_ELIGIBLE_STOCK", "groups": 0}
            )
            continue
        total = sum(sizes.values())
        total_target = sum(target_sizes.values())
        # Fixed branch inventory is represented by constants, not thousands of
        # redundant Boolean variables. A whole-group greedy assignment supplies
        # a feasible warm start; CP-SAT still evaluates and optimises the objective.
        hint_destinations = {}
        hint_load = {b: 0 for b in BRANCHES}
        for key, choices in assignments.items():
            source = candidates[key][0]["branch"]
            if source in choices:
                hint_destinations[key] = source
                if source in hint_load:
                    hint_load[source] += target_sizes[key]
        for key in sorted(assignments, key=lambda k: (-target_sizes[k], k)):
            if key in hint_destinations:
                continue
            chosen = max(
                assignments[key],
                key=lambda b: config["targets"][b] * total_target / 100 - hint_load[b],
            )
            hint_destinations[key] = chosen
            hint_load[chosen] += target_sizes[key]
        for key, choices in assignments.items():
            for branch, variable in choices.items():
                if not isinstance(variable, int):
                    model.AddHint(variable, int(branch == hint_destinations[key]))
        total_aged = sum(age_costs.values())
        age_ratio = round(10000 * total_aged / total) if total else 0
        terms = []
        objective_vars = {
            "stock_balance": [],
            "aged_balance": [],
            "availability": [],
            "profitability": [],
            "reactivation": [],
        }
        for b in BRANCHES:
            branch_cost = sum(
                sizes[k] * choices[b]
                for k, choices in assignments.items()
                if b in choices
            )
            branch_age = sum(
                age_costs[k] * choices[b]
                for k, choices in assignments.items()
                if b in choices
            )
            target_value = sum(
                target_sizes[k] * choices[b]
                for k, choices in assignments.items()
                if b in choices
            )
            share_error = (
                target_value * 10000 - round(config["targets"][b] * 100) * total_target
            )
            scaled = model.NewIntVar(0, total_target, f"share_scaled:{b}")
            # Minimise floor(abs(error)/10000) using linear inequalities. This
            # avoids expensive sparse-domain expansion from abs + integer division.
            model.Add(scaled * 10000 + 9999 >= share_error)
            model.Add(scaled * 10000 + 9999 >= -share_error)
            hint_deviation = abs(
                hint_load[b] * 10000 - round(config["targets"][b] * 100) * total_target
            )
            model.AddHint(scaled, hint_deviation // 10000)
            terms.append(-config["weights"]["stock_balance"] * scaled)
            objective_vars["stock_balance"].append(scaled)
            age_error = branch_age * 10000 - branch_cost * age_ratio
            age_scaled = model.NewIntVar(0, total, f"age_scaled:{b}")
            model.Add(age_scaled * 10000 + 9999 >= age_error)
            model.Add(age_scaled * 10000 + 9999 >= -age_error)
            hint_cost = sum(
                sizes[k]
                for k, destination in hint_destinations.items()
                if destination == b
            )
            hint_age = sum(
                age_costs[k]
                for k, destination in hint_destinations.items()
                if destination == b
            )
            hint_age_deviation = abs(hint_age * 10000 - hint_cost * age_ratio)
            model.AddHint(age_scaled, hint_age_deviation // 10000)
            terms.append(-config["weights"]["aged_balance"] * age_scaled)
            objective_vars["aged_balance"].append(age_scaled)
            if all_history:
                for s in segments:
                    required = round(
                        demand["demand"].get((b, s), 0)
                        * 365
                        / demand["days"]
                        / config["annual_turns"]
                    )
                    assigned = sum(
                        sum(segment(m) == s for m in candidates[k]) * choices[b]
                        for k, choices in assignments.items()
                        if b in choices
                    )
                    shortage = model.NewIntVar(0, max(required, 0), f"shortage:{b}:{s}")
                    model.Add(shortage >= required - assigned)
                    terms.append(-100 * config["weights"]["availability"] * shortage)
                    objective_vars["availability"].append(shortage)
                for k, choices in assignments.items():
                    if b not in choices:
                        continue
                    members = candidates[k]
                    observed = sum(
                        demand["demand"].get((b, segment(m)), 0) for m in members
                    )
                    total_observed = sum(
                        demand["demand"].get((branch, segment(m)), 0)
                        for branch in BRANCHES
                        for m in members
                    )
                    reuse = (
                        round(age_costs[k] * observed / total_observed)
                        if total_observed
                        else 0
                    )
                    terms.append(config["weights"]["reactivation"] * reuse * choices[b])
                    objective_vars["reactivation"].append(reuse * choices[b])
                    # A confirmed basis and measured realised economics are both prerequisites.
                    gains = []
                    for m in members:
                        rule = margin_for(m, config)
                        history = demand["profit"].get((b, segment(m)), [])
                        if rule and rule["confirmed"] and rule["basis"] and history:
                            gains.append(round(sum(history) / len(history) / 10000))
                    gain = sum(gains)
                    terms.append(config["weights"]["profitability"] * gain * choices[b])
                    objective_vars["profitability"].append(gain * choices[b])
        # Prefer fewer movements only as a tie break.
        movement = sum(
            v
            for k, choices in assignments.items()
            for b, v in choices.items()
            if b != candidates[k][0]["branch"]
        )
        model.Maximize(sum(terms) * (len(candidates) + 1) - movement)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 15
        solver.parameters.num_search_workers = 2
        solver.parameters.random_seed = 42
        status = solver.Solve(model)
        status_name = solver.StatusName(status)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise ValueError(
                f"Solver did not find a feasible {material} allocation: {status_name}"
            )
        diagnostics.append(
            {
                "material": material,
                "solver": status_name,
                "groups": len(candidates),
                "objective": solver.ObjectiveValue(),
                "best_bound": solver.BestObjectiveBound(),
                "time_limit_seconds": 15,
                "movable_groups": sum(
                    len(choices) > 1 for choices in assignments.values()
                ),
                "components": {
                    name: sum(solver.Value(v) for v in values)
                    for name, values in objective_vars.items()
                },
            }
        )
        for key, choices in assignments.items():
            destination = next(b for b, v in choices.items() if solver.Value(v))
            members = candidates[key]
            source = members[0]["branch"]
            if destination == source:
                continue
            route = (
                [source, destination] if source == "HO" else [source, "HO", destination]
            )
            proposals.append(
                {
                    "group_key": key,
                    "labels": [m["label_id"] for m in members],
                    "route": route,
                    "purpose": "rebalance",
                    "material": material,
                    "cost_paise": sum(cost_paise(m) for m in members),
                    "original_received_at": {
                        m["label_id"]: m["received_at"] for m in members
                    },
                }
            )
            for m in members:
                after_by_id[m["label_id"]]["branch"] = destination
    recalls = [
        {
            "group_key": key,
            "labels": [m["label_id"] for m in members],
            "route": [members[0]["branch"], "HO"],
            "purpose": "priority_recall",
            "material": members[0]["material"],
            "cost_paise": None
            if any(cost_paise(m) is None for m in members)
            else sum(cost_paise(m) for m in members),
            "original_received_at": {m["label_id"]: m["received_at"] for m in members},
        }
        for key, members in groups.items()
        if any(is_cz(m) for m in members)
        and members[0]["branch"] != "HO"
        and not any(m.get("reserved") for m in members)
    ]
    return {
        "proposals": proposals,
        "priority_recalls": recalls,
        "excluded": excluded,
        "before": before,
        "after": summarize(after_facts, snapshot, config, demand),
        "diagnostics": diagnostics,
        "objectives": {
            "availability": "measured historical sales"
            if all_history
            else "unavailable — complete branch sales history required",
            "profitability": "confirmed basis + observed realised profit only; missing segments contribute no profit score",
            "reactivation": "aged cost exposed to measured demand"
            if all_history
            else "unavailable — complete branch sales history required",
            "age_balance": "minimise aged cost fraction differences, including heavy and expensive labels",
        },
        "ho_cz_reuse": [
            f["label_id"] for f in facts if is_cz(f) and f["branch"] == "HO"
        ],
        "limitations": [
            "Cost balancing uses ₹100 units; gold weight targets use 0.01g units; diagnostics retain exact values.",
            "Sales-based turns are an indicative unit proxy, not financial turnover.",
            "Missing costs are excluded from cost-balanced planning.",
            "CZ variety is held out of ordinary redistribution; HO CZ stock is flagged for reuse, not dispatched.",
        ],
    }
