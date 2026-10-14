# RG Stock Engine — first-version contract

Source workbooks are retained by SHA-256 on disk; raw rows, explicit mappings and validated facts are retained in PostgreSQL. A stock snapshot is a point-in-time report, not a mutable stock ledger. Snapshot date is explicitly supplied by the operator. No source format is claimed as verified until the latest Ornate files are supplied.

| Entity | Purpose |
| --- | --- |
| snapshots | Workbook hash, kind, original filename, import date, as-of date, branch coverage, errors, warnings, reconciliation and approval status |
| source_rows | Original Excel row number, raw cells and canonical facts; never overwritten |
| rule_versions | Full immutable rules, parent version and lifecycle state |
| simulations | Stock and sales snapshot IDs, exact rule version, assumptions, objective components, solver outcome and comparison |
| transfers | Whole-set label groups, purpose, HO route and execution state |
| movement_events | Append-only dispatch/receipt record for each route leg, reference, actor and timestamp |
| audit_events | Import approvals, rule transitions, comparisons and transfer actions |

## Stock import

1. Inspect workbook sheets and headers. Select a sheet and map headers explicitly to canonical fields. Exact canonical headers are suggested; no Ornate aliases are guessed.
2. Preview and validate all rows: unique labels, dates, material, location, nonnegative values, usable status and complete sets. Generic `.xlsx` formula cells are rejected because cached calculations cannot be trusted. Legacy `.xls` is supported only by the verified Ornate report adapter described below; other formats must be exported to `.xlsx`. Workbook and row limits bound resource use.
3. Declare each location as `complete`, `confirmed_zero` or `missing`. A report containing some branch rows is not automatically a complete branch report. Missing data stays unknown; confirmed zero contradicting rows is rejected.
4. Reconcile label counts for each known location against independently supplied report totals; optional cost totals use ₹0.01 tolerance. Blocking errors cannot be waived. Confirm with an operator identity and a reconciliation note.
5. The resulting snapshot is immutable. Corrections require a new workbook/snapshot. Movements are recorded separately; accepting a newer stock snapshot requires explicit acknowledgement that it is the current physical baseline, and is blocked while any dispatch is in transit.

Canonical stock fields: `label_id`, `branch`, `material` (`gold`, `natural_diamond`, `lab_diamond`), `item`, `karatage`, `variety`, `supplier`, `received_at` (original label age date), `usable` (true/false), optional `set_id` with required `set_size`, `weight_g`, `carats`, `metal_cost`, `stone_cost`, `other_cost`, `landed_cost`, `selling_price`, `net_sale_value`. Full landed cost, when explicitly supplied, takes precedence over its component fields. Costs and prices are rupees; blank cost is unknown, never zero. Label IDs must be text to preserve leading zeros. Labels in a set must share location/material/usability and all members must be present. Original age is retained on every transfer. Imported file contents, master values and user notes are data, never instructions.

The supplied legacy Ornate `.xls` adapter recognises its 22-column closing-stock layout and branch sections case-insensitively. It parses 14,151 labels and checks the report grand count. `Days` is preserved separately from `Vou Date`; ageing is provisional until its original-age meaning is confirmed. `Closing Value` is retained as a source value and becomes landed cost only after explicit confirmation. `Stone Wt` is not automatically called carats. One tag remains an indivisible saleable unit irrespective of `Pcs`. Other materials (silver/platinum/gems etc.) remain `out_of_scope`, never converted into gold or diamond inventory. The planning workbook's old snapshots do not replace this new physical source.

## Sales and demand

Canonical sales fields: `sale_id`, `label_id`, `branch`, `material`, `item`, `karatage`, `variety`, `sold_at`, `selling_price`, optional `buying_cost`. Explicit history start/end and covered branches distinguish observed zero sales from missing history. Reconciliation requires row count. Realised profit uses supplied buying cost, never tentative margins. Demand groups by material/item/karatage/variety and location. Age does not imply demand. Unit turns are a **proxy** using annualised historical units/current units, not accounting inventory turnover; four turns is the planning target. Historical average inventory and COGS are needed for actual financial turnover.

## Rules and planning

Draft → simulate → compare against active rule on the same source snapshots → approve → activate. Rule contents freeze on first simulation; edits clone a new draft. Approval requires a feasible compared simulation. A single active version is enforced using a database lock. Editable masters can be entered as JSON or imported from a mapped Excel sheet. Empty masters mean unverified classifications, disclosed in results.

Each material is optimised independently with OR-Tools CP-SAT. Default source is usable HO stock, assigned across retail branches; committed, unusable and CZ HO labels are held out. Optional branch exchanges always use source → HO → destination. CZ **varieties**, at any location, are excluded from ordinary allocation and listed for priority recall/reuse. Missing branch/HO coverage blocks allocation. Whole sets are indivisible. Original label ages do not reset. The objective is a weighted blend of measured-demand availability, verified historical realised profit, aged stock exposure to measured demand, target share deviation and aged cost percentage deviation. Gold targets default to net weight; diamonds default to separate cost targets. Exact source costs use integer paise; the solver uses ₹100 cost / 0.01g weight units. Groups missing a complete landed cost are excluded from cost-balanced proposals and explicitly reported. Target bases and objective weights are versioned assumptions.

Profit is only scored when the relevant margin basis is confirmed and historical realised profit exists; provisional stone economics are never inserted into costs. Heavy/expensive aged labels remain eligible, appear in diagnostics and contribute full cost to aged balancing. All objective scores and before/after cost percentages are retained; solver output is a proposal requiring human execution approval.

Transfer proposal → approved → dispatched → received, one HO route leg at a time. Proposals do not change inventory. Dispatch is in transit; receipt changes the effective location. Duplicate execution of a label across simulations is rejected. Re-imports never silently reconcile live movements. Pending proposals on older physical baselines cannot be executed.

## Boundaries

This is an internal local-development first version. Actor fields are attribution, not authentication. Production deployment requires SSO/RBAC, durable encrypted source storage, migrations, backups and reviewed reconciliation/dispatch permissions. The default command interpreter is deterministic and local. Optional OpenAI structured interpretation uses `RG_AI_API_KEY` and `RG_AI_MODEL` (default `gpt-4.1-mini`); it receives only the command, provenance, rules and computed branch/solver summaries. It has no tools, execution permissions or calculation authority. AI output is schema-validated and cannot mutate the engine. All calculations run in Python. No fabricated business inventory or master rules are seeded.
