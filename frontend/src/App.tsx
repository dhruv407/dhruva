import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  FileSpreadsheet,
  Gem,
  History,
  LayoutDashboard,
  LoaderCircle,
  Plus,
  RefreshCw,
  Scale,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Truck,
  X,
} from "lucide-react";
import {
  api,
  branches,
  locations,
  materialNames,
  money,
  download,
  Json,
} from "./api";

type View = "overview" | "imports" | "ageing" | "rules" | "proposals" | "audit";
const nav: [View, string, typeof Boxes][] = [
  ["overview", "Stock overview", LayoutDashboard],
  ["imports", "Data & imports", FileSpreadsheet],
  ["ageing", "Ageing & reactivation", History],
  ["rules", "Planning rules", Settings2],
  ["proposals", "Rebalance proposals", Scale],
  ["audit", "Activity & traceability", ClipboardCheck],
];
const titles: Record<View, [string, string]> = {
  overview: [
    "A clearer view of your stock.",
    "Every label. Every branch. One informed decision.",
  ],
  imports: [
    "Good decisions start with good data.",
    "Import, validate and reconcile before planning.",
  ],
  ageing: [
    "Give old stock a new opportunity.",
    "Original label age stays with the stock, wherever it goes.",
  ],
  rules: [
    "Your business. Your planning rules.",
    "Version every assumption. Test every change.",
  ],
  proposals: [
    "The right stock, in the right place.",
    "Review whole-set allocations before any stock moves.",
  ],
  audit: [
    "A record behind every decision.",
    "Source snapshots, rule versions and actions stay traceable.",
  ],
};

function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
function Empty({
  icon: Icon = FileSpreadsheet,
  title,
  children,
  action,
}: {
  icon?: typeof Boxes;
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={29} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("overview"),
    [material, setMaterial] = useState("gold"),
    [branch, setBranch] = useState("all");
  const [data, setData] = useState<Json | null>(null),
    [snapshots, setSnapshots] = useState<Json[]>([]),
    [rules, setRules] = useState<Json[]>([]),
    [simulations, setSimulations] = useState<Json[]>([]),
    [audit, setAudit] = useState<Json[]>([]);
  const [stockId, setStockId] = useState(""),
    [ruleId, setRuleId] = useState(""),
    [salesId, setSalesId] = useState("");
  const [actor, setActor] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [command, setCommand] = useState("");
  const [explanation, setExplanation] = useState("");
  const [aiConfigured, setAiConfigured] = useState(false);
  const [useAi, setUseAi] = useState(false);
  useEffect(() => {
    api("/assistant/status")
      .then((s) => setAiConfigured(s.configured))
      .catch(() => {});
  }, []);
  async function refresh() {
    const query = new URLSearchParams();
    if (stockId) query.set("snapshot_id", stockId);
    if (ruleId) query.set("rule_id", ruleId);
    if (salesId) query.set("sales_snapshot_id", salesId);
    const [d, s, r, p, a] = await Promise.all([
      api("/dashboard?" + query),
      api("/snapshots"),
      api("/rules"),
      api("/simulations"),
      api("/audit"),
    ]);
    setData(d);
    setSnapshots(s);
    setRules(r);
    setSimulations(p);
    setAudit(a);
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [stockId, ruleId, salesId]);
  async function perform(
    fn: () => Promise<unknown>,
    success = "Saved successfully",
  ) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
      await refresh();
      setMessage(success);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const selectedRule =
    rules.find((r) => r.id === Number(ruleId || data?.rule_id)) || rules[0];
  const selectedStock = data?.snapshot_id;
  const known = (data?.branches || []).filter(
    (r: Json) => r.material === material && branches.includes(r.branch),
  );
  const labels =
    known.every((r: Json) => r.labels !== null) && known.length === 5
      ? known.reduce((n: number, r: Json) => n + r.labels, 0)
      : null;
  const completeCost =
    labels !== null && known.every((r: Json) => !r.unknown_cost_labels);
  const totalCost = completeCost
    ? known.reduce((n: number, r: Json) => n + r.cost_paise, 0)
    : null;
  const agedCost = completeCost
    ? known.reduce((n: number, r: Json) => n + r.aged_cost_paise, 0)
    : null;
  const cz = (data?.ageing || []).filter(
    (r: Json) => r.branch === "CZ" && r.material === material,
  );
  const provenance = data?.snapshot_id
    ? `Stock #${data.snapshot_id} · ${data.as_of} · Rule v${data.rule_id} (${data.rule_state})${data.sales_snapshot_id ? " · Sales #" + data.sales_snapshot_id : " · No sales history"}`
    : "No reconciled stock snapshot";
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("overview");
          }}
        >
          <span className="brand-mark">
            RG<span>✦</span>
          </span>
          <span>
            RIGHT GOLD<small>STOCK ENGINE</small>
          </span>
        </a>
        <div className="workspace-label">INVENTORY WORKSPACE</div>
        <nav>
          {nav.map(([key, label, Icon]) => (
            <button
              key={key}
              className={view === key ? "nav-item active" : "nav-item"}
              onClick={() => setView(key)}
            >
              <Icon size={18} />
              <span>{label}</span>
              {key === "proposals" && simulations.length > 0 && (
                <b>{simulations.length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={20} />
          <strong>Built for considered decisions</strong>
          <p>Proposals stay separate from dispatches and receipts.</p>
        </div>
        <div className="sidebar-foot">
          <div className="avatar">RG</div>
          <div>
            Right Gold<small>Internal planning workspace</small>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />{" "}
            <span>{nav.find((n) => n[0] === view)?.[1]}</span>
          </div>
          <div className="top-actions">
            <span className="local-tag">
              <span />{" "}
              {import.meta.env.VITE_DEPLOYMENT_MODE === "staging"
                ? "Private test workspace"
                : "Development workspace"}
            </span>
            <button
              className="icon-button"
              aria-label="Refresh workspace"
              onClick={() => perform(async () => {}, "Workspace refreshed")}
            >
              <RefreshCw size={17} />
            </button>
            <span className="avatar light">RG</span>
          </div>
        </header>
        <main>
          {import.meta.env.VITE_DEPLOYMENT_MODE === "staging" && (
            <div className="alert success">
              Test workspace: approvals and movement records apply to this
              isolated test copy.
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">RIGHT GOLD / INVENTORY INTELLIGENCE</div>
              <h1>{titles[view][0]}</h1>
              <p>{titles[view][1]}</p>
            </div>
            <button
              className="primary"
              onClick={() =>
                setView(view === "imports" ? "overview" : "imports")
              }
            >
              {view === "imports" ? (
                <LayoutDashboard size={16} />
              ) : (
                <Plus size={17} />
              )}{" "}
              {view === "imports" ? "View stock" : "Import stock"}
            </button>
          </div>
          {error && (
            <div role="alert" className="alert error">
              <CircleHelp size={17} />
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {message && (
            <div role="status" className="alert success">
              <Check size={17} />
              {message}
              <button
                onClick={() => setMessage("")}
                aria-label="Dismiss notification"
              >
                <X size={16} />
              </button>
            </div>
          )}
          <div className="context-bar">
            <div className="material-tabs">
              {Object.entries(materialNames).map(([key, label]) => (
                <button
                  className={material === key ? "selected" : ""}
                  key={key}
                  onClick={() => setMaterial(key)}
                >
                  <Gem size={14} />
                  {label}
                </button>
              ))}
            </div>
            <label className="snapshot-select">
              Snapshot{" "}
              <select
                aria-label="Stock snapshot"
                value={stockId}
                onChange={(e) => setStockId(e.target.value)}
              >
                <option value="">Latest reconciled</option>
                {snapshots
                  .filter(
                    (s) => s.kind === "stock" && s.status === "reconciled",
                  )
                  .map((s) => (
                    <option value={s.id} key={s.id}>
                      #{s.id} · {s.as_of}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          {view === "overview" && (
            <>
              <div className="stats">
                <Stat
                  title="BRANCH INVENTORY VALUE"
                  value={money(totalCost)}
                  note={
                    completeCost
                      ? "Complete landed cost · all five branches"
                      : "Awaiting complete branch and cost data"
                  }
                  icon={Boxes}
                />
                <Stat
                  title="LABELS IN BRANCHES"
                  value={labels === null ? "—" : labels.toLocaleString("en-IN")}
                  note="Whole labels · sets preserved"
                  icon={Gem}
                />
                <Stat
                  title="AGED INVENTORY VALUE"
                  value={money(agedCost)}
                  note={`${selectedRule?.config.age_days || 180}+ days · original label age`}
                  icon={History}
                />
                <Stat
                  title="ANNUAL TURNS TARGET"
                  value={String(selectedRule?.config.annual_turns || 4) + "×"}
                  note="Measured demand, never inferred from age"
                  icon={RefreshCw}
                />
              </div>
              <div className="overview-grid">
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Branch allocation</h2>
                      <p>
                        Net gold weight / diamond value against your targets
                      </p>
                    </div>
                    <Badge tone="gold">5 branches</Badge>
                  </div>
                  <div className="allocation-legend">
                    <span>
                      <i className="actual" />
                      Actual share
                    </span>
                    <span>
                      <i className="target" />
                      Target share
                    </span>
                  </div>
                  <div className="allocation-rows">
                    {branches.map((b) => {
                      const row = known.find((r: Json) => r.branch === b);
                      const target =
                        data?.targets?.[b] ||
                        { NV: 24, LN: 16, AR: 19, RO: 19, IK: 22 }[b as "NV"];
                      return (
                        <div className="allocation-row" key={b}>
                          <div className="branch-logo">{b}</div>
                          <div className="allocation-detail">
                            <div>
                              <strong>{b}</strong>
                              <span>
                                {row?.coverage === "missing" || !row
                                  ? "Data missing"
                                  : row.coverage === "confirmed_zero"
                                    ? "Confirmed zero inventory"
                                    : money(row.cost_paise)}
                              </span>
                            </div>
                            <div className="bar-track">
                              <div
                                className="target-bar"
                                style={{ width: target * 2 + "%" }}
                              />
                              <div
                                className="actual-bar"
                                style={{
                                  width: (row?.actual_share || 0) * 2 + "%",
                                }}
                              />
                            </div>
                          </div>
                          <div className="share">
                            <strong>
                              {row?.actual_share == null
                                ? "—"
                                : row.actual_share + "%"}
                            </strong>
                            <small>Target {target}%</small>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="panel-footer">
                    <ShieldCheck size={14} /> Missing branch data is never
                    counted as zero inventory.
                  </div>
                </section>
                <section className="panel planning-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Planning priorities</h2>
                      <p>Three objectives. One balanced plan.</p>
                    </div>
                    <Sparkles size={19} />
                  </div>
                  <div className="priority">
                    <span className="priority-number">01</span>
                    <div>
                      <h3>Fast-seller availability</h3>
                      <p>
                        Use historical label sales to put proven demand first.
                      </p>
                      <Badge>
                        {data?.sales_snapshot_id
                          ? "Sales history linked"
                          : "Needs sales history"}
                      </Badge>
                    </div>
                  </div>
                  <div className="priority">
                    <span className="priority-number">02</span>
                    <div>
                      <h3>Profitability</h3>
                      <p>
                        Confirmed margin bases and observed realised economics.
                      </p>
                      <Badge>Net sale value basis recorded</Badge>
                    </div>
                  </div>
                  <div className="priority">
                    <span className="priority-number">03</span>
                    <div>
                      <h3>Stuck-stock reactivation</h3>
                      <p>
                        Balance aged cost exposure, including heavy, expensive
                        stock.
                      </p>
                      <Badge tone="gold">CZ · priority recall / reuse</Badge>
                    </div>
                  </div>
                </section>
              </div>
              <section className="panel branch-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Stock health, branch by branch</h2>
                    <p>
                      {materialNames[material]} · values are kept separate from
                      other materials
                    </p>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setView("ageing")}
                  >
                    Explore ageing <ArrowUpRight size={16} />
                  </button>
                </div>
                <BranchTable rows={known} targets={data?.targets} />
              </section>
              {!selectedStock && (
                <section className="onboarding-card">
                  <div className="onboarding-icon">
                    <FileSpreadsheet size={28} />
                  </div>
                  <div>
                    <h3>Your stock story starts here.</h3>
                    <p>
                      Upload your latest Ornate export, map the columns and
                      reconcile branch totals. Your first dashboard will be
                      built from validated data.
                    </p>
                  </div>
                  <button
                    className="primary"
                    onClick={() => setView("imports")}
                  >
                    Import your first snapshot <ArrowRight size={16} />
                  </button>
                </section>
              )}
              {data?.warnings?.map((w: string) => (
                <div className="quiet-note" key={w}>
                  <CircleHelp size={14} />
                  {w}
                </div>
              ))}
              <section className="assistant-box">
                <Sparkles size={22} />
                <div>
                  <h3>Explore your inventory in plain language</h3>
                  <p>
                    Try “show old gold at NV” or “review CZ recall”. The
                    interpreter navigates; code calculates.
                  </p>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      perform(async () => {
                        const x = await api(
                          useAi ? "/assistant/ai" : "/assistant/interpret",
                          {
                            command,
                          },
                        );
                        setView(x.view);
                        if (x.branch) setBranch(x.branch);
                        if (x.material) setMaterial(x.material);
                        setExplanation(x.explanation);
                      }, "Command interpreted");
                    }}
                  >
                    <input
                      value={command}
                      onChange={(e) => setCommand(e.target.value)}
                      required
                      placeholder="What would you like to explore?"
                      aria-label="Inventory command"
                    />
                    <button type="submit" aria-label="Interpret command">
                      <ArrowRight size={18} />
                    </button>
                  </form>
                  {explanation && <small>{explanation}</small>}
                </div>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={useAi}
                    disabled={!aiConfigured}
                    onChange={(e) => setUseAi(e.target.checked)}
                  />
                  {aiConfigured
                    ? "Use AI explanation"
                    : "Local interpreter · AI key needed"}
                </label>
              </section>
            </>
          )}
          {view === "imports" && (
            <Imports
              snapshots={snapshots}
              actor={actor}
              busy={busy}
              perform={perform}
            />
          )}
          {view === "ageing" && (
            <Ageing
              data={data}
              material={material}
              branch={branch}
              setBranch={setBranch}
            />
          )}
          {view === "rules" && (
            <RuleEditor
              rules={rules}
              selected={selectedRule}
              setRuleId={setRuleId}
              actor={actor}
              busy={busy}
              perform={perform}
            />
          )}
          {view === "proposals" && (
            <Proposals
              simulations={simulations}
              data={data}
              selectedRule={selectedRule}
              rules={rules}
              setRuleId={setRuleId}
              snapshots={snapshots}
              salesId={salesId}
              setSalesId={setSalesId}
              actor={actor}
              busy={busy}
              material={material}
              perform={perform}
            />
          )}
          {view === "audit" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Decision & movement ledger</h2>
                  <p>Append-only events, newest first</p>
                </div>
                <button
                  className="secondary"
                  onClick={() => download(audit, "rg-audit.json")}
                >
                  <ArrowDownToLine size={15} />
                  Export
                </button>
              </div>
              {audit.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Event</th>
                        <th>Record</th>
                        <th>Actor</th>
                        <th>Time</th>
                        <th>Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {audit.map((a) => (
                        <tr key={a.id}>
                          <td>
                            <Badge>{a.action}</Badge>
                          </td>
                          <td>
                            {a.entity} #{a.entity_id}
                          </td>
                          <td>{a.actor}</td>
                          <td>{new Date(a.at).toLocaleString()}</td>
                          <td>
                            <code>{JSON.stringify(a.details)}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No activity yet">
                  Your import, rule and movement actions will appear here.
                </Empty>
              )}
            </section>
          )}
          <footer className="page-footer">
            <span>
              <ShieldCheck size={13} />
              {provenance}
            </span>
            <label>
              Operator{" "}
              <input
                placeholder="Your name (required for actions)"
                aria-label="Operator identity"
                value={actor}
                onChange={(e) => setActor(e.target.value)}
              />
            </label>
          </footer>
        </main>
      </div>
      {busy && (
        <div className="working" role="status">
          <LoaderCircle className="spin" size={17} /> Working…
        </div>
      )}
    </div>
  );
}

function Stat({
  title,
  value,
  note,
  icon: Icon,
}: {
  title: string;
  value: string;
  note: string;
  icon: typeof Boxes;
}) {
  return (
    <section className="stat">
      <div className="stat-top">
        <span>{title}</span>
        <Icon size={17} />
      </div>
      <strong>{value}</strong>
      <p>{note}</p>
    </section>
  );
}
function BranchTable({ rows, targets }: { rows: Json[]; targets?: Json }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Branch</th>
            <th>Coverage</th>
            <th>Labels</th>
            <th>Net gold weight</th>
            <th>Landed cost</th>
            <th>Aged cost %</th>
            <th>Target share</th>
            <th>Actual share</th>
            <th>Annual unit turns*</th>
          </tr>
        </thead>
        <tbody>
          {branches.map((b) => {
            const r = rows.find((r) => r.branch === b);
            return (
              <tr key={b}>
                <td>
                  <strong>{b}</strong>
                </td>
                <td>
                  <Badge
                    tone={
                      r?.coverage === "complete"
                        ? "green"
                        : r?.coverage === "confirmed_zero"
                          ? "gold"
                          : "neutral"
                    }
                  >
                    {r?.coverage?.replace("_", " ") || "Data missing"}
                  </Badge>
                </td>
                <td>{r?.labels ?? "—"}</td>
                <td>
                  {r?.weight_g == null
                    ? "—"
                    : Number(r.weight_g).toLocaleString("en-IN", {
                        maximumFractionDigits: 3,
                      }) + " g"}
                </td>
                <td>
                  {money(r?.cost_paise)}
                  {r?.unknown_cost_labels > 0 && (
                    <small className="cell-note">
                      {r?.unknown_cost_labels} costs unknown
                    </small>
                  )}
                </td>
                <td>{r?.aged_percent == null ? "—" : r.aged_percent + "%"}</td>
                <td>{targets?.[b] ?? "—"}%</td>
                <td>{r?.actual_share == null ? "—" : r.actual_share + "%"}</td>
                <td>
                  {r?.unit_turns_proxy == null ? "—" : r.unit_turns_proxy + "×"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

type ActionProps = {
  actor: string;
  busy: boolean;
  perform: (fn: () => Promise<unknown>, message?: string) => Promise<void>;
};
function Imports({
  snapshots,
  actor,
  busy,
  perform,
}: ActionProps & { snapshots: Json[] }) {
  const [kind, setKind] = useState("stock"),
    [file, setFile] = useState<File | null>(null),
    [inspect, setInspect] = useState<Json | null>(null),
    [sheet, setSheet] = useState(""),
    [mapping, setMapping] = useState<Json>({}),
    [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10)),
    [current, setCurrent] = useState<Json | null>(null),
    [coverage, setCoverage] = useState<Json>(
      Object.fromEntries(locations.map((b) => [b, "missing"])),
    ),
    [counts, setCounts] = useState<Json>({}),
    [costs, setCosts] = useState<Json>({}),
    [note, setNote] = useState(""),
    [historyStart, setHistoryStart] = useState(""),
    [ack, setAck] = useState(false),
    [costConfirmed, setCostConfirmed] = useState(false),
    [ageConfirmed, setAgeConfirmed] = useState(false),
    [hoConfirmed, setHoConfirmed] = useState(false);
  const headers =
    inspect?.sheets.find((s: Json) => s.name === sheet)?.headers || [];
  const required = inspect?.[kind + "_required"] || [],
    optional = inspect?.[kind + "_optional"] || [];
  function chooseSheet(name: string, info = inspect, type = kind) {
    setSheet(name);
    const h = info?.sheets.find((s: Json) => s.name === name)?.headers || [];
    const fields = [
      ...(info?.[type + "_required"] || []),
      ...(info?.[type + "_optional"] || []),
    ];
    setMapping(
      Object.fromEntries(
        fields.filter((f) => h.includes(f)).map((f) => [f, f]),
      ),
    );
  }
  function selectCurrent(s: Json) {
    setCurrent(s);
    setCoverage(Object.fromEntries(locations.map((b) => [b, "missing"])));
    setCounts({});
    setCosts({});
    setNote("");
  }
  return (
    <>
      <div className="workflow-strip">
        {[
          "Upload export",
          "Map & validate",
          "Reconcile totals",
          "Confirm snapshot",
        ].map((v, i) => (
          <div key={v}>
            <span>{i + 1}</span>
            {v}
            {i < 3 && <ChevronRight size={15} />}
          </div>
        ))}
      </div>
      <div className="import-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Import an Ornate workbook</h2>
              <p>Explicit mapping. No assumed column meanings.</p>
            </div>
            <FileSpreadsheet size={20} />
          </div>
          <div className="panel-body">
            <div className="form-row">
              <label>
                Export type
                <select
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value);
                    setCurrent(null);
                    if (inspect) chooseSheet(sheet, inspect, e.target.value);
                  }}
                >
                  <option value="stock">Stock by label</option>
                  <option value="sales">Historical label sales</option>
                </select>
              </label>
              <label>
                Snapshot / history end date
                <input
                  type="date"
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                  required
                />
              </label>
            </div>
            <label className="upload-area">
              <ArrowDownToLine size={24} />
              <strong>{file?.name || "Choose your Excel export"}</strong>
              <span>.xlsx / verified Ornate .xls · up to 15 MB</span>
              <input
                type="file"
                accept=".xlsx,.xls"
                aria-label="Excel workbook"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  setFile(f);
                  setInspect(null);
                  setCurrent(null);
                  perform(async () => {
                    const form = new FormData();
                    form.append("file", f);
                    const info = await api("/imports/inspect", form);
                    setInspect(info);
                    if (info.profile) {
                      setKind("stock");
                      setAsOf(info.as_of);
                    }
                    chooseSheet(info.sheets[0].name, info);
                  }, "Workbook inspected");
                }}
              />
            </label>
            <div className="template-links">
              <a href={"/api/imports/template/" + kind}>
                <ArrowDownToLine size={13} /> Download blank canonical template
              </a>
              <span>No business data is included</span>
            </div>
            {inspect?.profile && (
              <div className="ornate-confirmations">
                <Badge tone="gold">Verified Ornate report layout</Badge>
                <p className="helper">
                  {inspect.sheets[0].estimated_rows} labels · {inspect.as_of} ·
                  sections: {inspect.branch_sections.join(", ")}. IK coverage is
                  not inferred.
                </p>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={costConfirmed}
                    onChange={(e) => setCostConfirmed(e.target.checked)}
                  />
                  Closing Value is confirmed full landed buying cost.
                </label>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={ageConfirmed}
                    onChange={(e) => setAgeConfirmed(e.target.checked)}
                  />
                  Days is confirmed original label age.
                </label>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={hoConfirmed}
                    onChange={(e) => setHoConfirmed(e.target.checked)}
                  />
                  All reported HO stock is usable and uncommitted.
                </label>
                <p className="helper">
                  Unchecked assumptions remain unknown. Each label/pair stays
                  indivisible; physical pieces are retained separately. CZ
                  varieties are held for recall.
                </p>
                <button
                  className="primary full"
                  disabled={busy || !actor.trim()}
                  onClick={() =>
                    perform(async () => {
                      const f = new FormData();
                      f.append("file", file!);
                      f.append("actor", actor);
                      f.append(
                        "closing_value_is_landed_cost",
                        String(costConfirmed),
                      );
                      f.append(
                        "reported_days_is_original_age",
                        String(ageConfirmed),
                      );
                      f.append("ho_is_usable", String(hoConfirmed));
                      selectCurrent(await api("/imports/ornate", f));
                    }, "Ornate report parsed; review branch reconciliation")
                  }
                >
                  Validate Ornate report
                </button>
              </div>
            )}
            {inspect && !inspect.profile && (
              <>
                <label>
                  Worksheet
                  <select
                    value={sheet}
                    onChange={(e) => chooseSheet(e.target.value)}
                  >
                    {inspect.sheets.map((s: Json) => (
                      <option key={s.name}>{s.name}</option>
                    ))}
                  </select>
                </label>
                <div className="mapping-list">
                  <div className="mapping-heading">
                    <strong>Canonical field</strong>
                    <strong>Your export column</strong>
                  </div>
                  {[...required, ...optional].map((f: string) => (
                    <label className="mapping-row" key={f}>
                      <span>
                        {f}
                        {required.includes(f) && <b> *</b>}
                      </span>
                      <select
                        value={mapping[f] || ""}
                        onChange={(e) =>
                          setMapping({ ...mapping, [f]: e.target.value })
                        }
                      >
                        <option value="">
                          {required.includes(f)
                            ? "Select column"
                            : "Not provided (unknown)"}
                        </option>
                        {headers.filter(Boolean).map((h: string) => (
                          <option key={h}>{h}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <button
                  className="primary full"
                  disabled={
                    busy || !file || required.some((f: string) => !mapping[f])
                  }
                  onClick={() =>
                    perform(async () => {
                      const f = new FormData();
                      f.append("file", file!);
                      f.append("kind", kind);
                      f.append("sheet", sheet);
                      f.append("as_of", asOf);
                      f.append(
                        "mapping",
                        JSON.stringify(
                          Object.fromEntries(
                            Object.entries(mapping).filter(([, v]) => v),
                          ),
                        ),
                      );
                      selectCurrent(await api("/imports/preview", f));
                    }, "Validation complete; review reconciliation before confirming")
                  }
                >
                  <ShieldCheck size={16} /> Validate & preview
                </button>
              </>
            )}
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Reconciliation gate</h2>
              <p>Check against independently supplied report totals</p>
            </div>
            <ClipboardCheck size={20} />
          </div>
          {!current ? (
            <Empty title="Validate a workbook first">
              Row errors, source counts and branch coverage will appear here.
              Missing and confirmed zero are distinct.
            </Empty>
          ) : (
            <div className="panel-body">
              <div className="snapshot-summary">
                <Badge tone="gold">Snapshot #{current.id}</Badge>
                <strong>{current.row_count} rows</strong>
                <span>
                  {current.error_count} errors · {current.warning_count}{" "}
                  warnings
                </span>
              </div>
              <code className="hash">SHA-256 {current.sha256}</code>
              {current.errors.map((e: Json, i: number) => (
                <div className="validation-error" key={i}>
                  Row {e.row} · {e.field}: {e.message}
                </div>
              ))}
              {current.error_count > 500 && (
                <p>Showing first 500 errors; re-export corrected data.</p>
              )}
              {current.warning_count > 0 && (
                <div className="quiet-note">
                  {current.warning_count} warnings.{" "}
                  {current.warnings[0]?.message}
                </div>
              )}
              <div className="coverage-grid">
                <div>Location</div>
                <div>Coverage</div>
                <div>Report count</div>
                <div>Cost total ₹</div>
                {locations.map((b) => (
                  <div className="coverage-row" key={b}>
                    <strong>
                      {b}
                      <small>Imported: {current.counts[b] || 0}</small>
                    </strong>
                    <select
                      aria-label={b + " coverage"}
                      value={coverage[b]}
                      onChange={(e) =>
                        setCoverage({ ...coverage, [b]: e.target.value })
                      }
                    >
                      <option value="missing">Missing</option>
                      <option value="complete">Complete</option>
                      <option value="confirmed_zero">Confirmed zero</option>
                    </select>
                    <input
                      aria-label={b + " report count"}
                      type="number"
                      min="0"
                      value={counts[b] ?? ""}
                      placeholder="Required"
                      onChange={(e) =>
                        setCounts({ ...counts, [b]: e.target.value })
                      }
                    />
                    <input
                      aria-label={b + " cost control total"}
                      type="number"
                      min="0"
                      step="0.01"
                      disabled={current.kind === "sales"}
                      value={costs[b] ?? ""}
                      placeholder="Optional"
                      onChange={(e) =>
                        setCosts({ ...costs, [b]: e.target.value })
                      }
                    />
                  </div>
                ))}
              </div>
              {current.kind === "sales" && (
                <label>
                  Sales history starts
                  <input
                    type="date"
                    value={historyStart}
                    onChange={(e) => setHistoryStart(e.target.value)}
                  />
                </label>
              )}
              <label>
                Reconciliation note
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Report source, totals checked and discrepancies resolved"
                  rows={3}
                />
              </label>
              {current.kind === "stock" &&
                snapshots.some(
                  (s) => s.kind === "stock" && s.status === "reconciled",
                ) && (
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={ack}
                      onChange={(e) => setAck(e.target.checked)}
                    />
                    This export is the new physical stock baseline.
                  </label>
                )}
              <button
                className="primary full"
                disabled={
                  busy ||
                  !!current.error_count ||
                  !actor.trim() ||
                  !note.trim() ||
                  current.status === "reconciled"
                }
                onClick={() =>
                  perform(async () => {
                    const s = await api(
                      "/snapshots/" + current.id + "/reconcile",
                      {
                        actor,
                        coverage,
                        expected_counts: Object.fromEntries(
                          Object.entries(counts)
                            .filter(([, v]) => v !== "")
                            .map(([k, v]) => [k, Number(v)]),
                        ),
                        expected_costs: Object.fromEntries(
                          Object.entries(costs)
                            .filter(([, v]) => v !== "")
                            .map(([k, v]) => [k, Number(v)]),
                        ),
                        note,
                        history_start:
                          current.kind === "sales" ? historyStart : null,
                        acknowledge_new_baseline: ack,
                      },
                    );
                    setCurrent(s);
                  }, "Snapshot reconciled and retained")
                }
              >
                <Check size={16} /> Confirm reconciled snapshot
              </button>
              <small className="helper">
                Enter your operator name in the footer to record approval.
              </small>
              <details>
                <summary>Inspect source-row preview</summary>
                <pre>{JSON.stringify(current.sample_rows, null, 2)}</pre>
              </details>
            </div>
          )}
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Source snapshots</h2>
            <p>Original workbooks and validated rows are retained</p>
          </div>
        </div>
        {snapshots.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Snapshot</th>
                  <th>File</th>
                  <th>Kind</th>
                  <th>As of</th>
                  <th>Rows</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {snapshots.map((s) => (
                  <tr key={s.id}>
                    <td>#{s.id}</td>
                    <td>{s.filename}</td>
                    <td>{s.kind}</td>
                    <td>{s.as_of}</td>
                    <td>{s.row_count}</td>
                    <td>
                      <Badge
                        tone={s.status === "reconciled" ? "green" : "gold"}
                      >
                        {s.status}
                      </Badge>
                    </td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => selectCurrent(s)}
                      >
                        Review <ChevronRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No snapshots imported">
            Your original sources will be listed here after validation.
          </Empty>
        )}
      </section>
    </>
  );
}

function Ageing({
  data,
  material,
  branch,
  setBranch,
}: {
  data: Json | null;
  material: string;
  branch: string;
  setBranch: (v: string) => void;
}) {
  const [search, setSearch] = useState(""),
    [onlyAged, setOnlyAged] = useState(false),
    [page, setPage] = useState(0);
  const rows = (data?.ageing || []).filter(
    (f: Json) =>
      f.material === material &&
      (branch === "all" || f.branch === branch) &&
      (!onlyAged ||
        f.age_days >= data?.assumptions.age_days ||
        f.priority === "CZ recall / reuse") &&
      [f.label_id, f.item, f.variety, f.supplier, f.set_id]
        .join(" ")
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  useEffect(() => setPage(0), [search, branch, material, onlyAged]);
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Label ageing register</h2>
          <p>CZ appears first. Heavy and expensive old stock stays visible.</p>
        </div>
        <button
          className="secondary"
          disabled={!data?.snapshot_id}
          onClick={() =>
            download(
              { ...data, ageing: rows },
              "rg-ageing-snapshot-" + data?.snapshot_id + ".json",
            )
          }
        >
          <ArrowDownToLine size={15} />
          Export with provenance
        </button>
      </div>
      <div className="table-toolbar">
        <div className="search-box">
          <Search size={16} />
          <input
            aria-label="Search labels"
            placeholder="Search labels, items, sets…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          aria-label="Branch filter"
          value={branch}
          onChange={(e) => setBranch(e.target.value)}
        >
          <option value="all">All locations</option>
          {[...locations, "IN_TRANSIT"].map((b) => (
            <option key={b}>{b}</option>
          ))}
        </select>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={onlyAged}
            onChange={(e) => setOnlyAged(e.target.checked)}
          />
          Aged & CZ only
        </label>
        <Badge>{rows.length} labels</Badge>
      </div>
      {rows.length ? (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Label / set</th>
                  <th>Location</th>
                  <th>Item</th>
                  <th>Karat / variety</th>
                  <th>Original age</th>
                  <th>Weight / carats</th>
                  <th>Landed cost</th>
                  <th>Margin estimate*</th>
                  <th>Priority</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(page * 50, (page + 1) * 50).map((r: Json) => (
                  <tr key={r.label_id}>
                    <td>
                      <strong>{r.label_id}</strong>
                      <small className="cell-note">
                        {r.set_id ? "Set " + r.set_id : "Single label"}
                      </small>
                    </td>
                    <td>{r.branch}</td>
                    <td>
                      {r.item}
                      <small className="cell-note">{r.supplier}</small>
                    </td>
                    <td>
                      {r.karatage}
                      <small className="cell-note">
                        {r.variety}
                        {r.lmh_class ? " · " + r.lmh_class : ""}
                      </small>
                    </td>
                    <td>
                      <strong>{r.age_days} days</strong>
                      <small className="cell-note">
                        {r.received_at}
                        {r.age_verified === false ? " · provisional" : ""}
                      </small>
                    </td>
                    <td>
                      {r.weight_g ?? "—"} g
                      <small className="cell-note">{r.carats ?? "—"} ct</small>
                    </td>
                    <td>{money(r.cost_paise)}</td>
                    <td>{money(r.margin_estimate_paise)}</td>
                    <td>
                      <Badge
                        tone={
                          r.priority === "CZ recall / reuse"
                            ? "gold"
                            : r.priority === "Aged"
                              ? "rose"
                              : "green"
                        }
                      >
                        {r.priority}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span>
              Showing {page * 50 + 1}–{Math.min((page + 1) * 50, rows.length)}{" "}
              of {rows.length}
            </span>
            <button
              className="secondary"
              disabled={!page}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </button>
            <button
              className="secondary"
              disabled={(page + 1) * 50 >= rows.length}
              onClick={() => setPage(page + 1)}
            >
              Next
            </button>
          </div>
        </>
      ) : (
        <Empty
          icon={History}
          title={
            data?.snapshot_id
              ? "No labels match these filters"
              : "Ageing starts with validated stock"
          }
        >
          Upload original label dates to analyse stuck stock. Younger inventory
          is never assumed to sell faster.
        </Empty>
      )}
      <div className="panel-footer">
        *Margin estimates are separate from realised profit. Net sale value must
        be explicitly supplied; stone profit is not inferred.
      </div>
    </section>
  );
}

function RuleEditor({
  rules,
  selected,
  setRuleId,
  actor,
  busy,
  perform,
}: ActionProps & {
  rules: Json[];
  selected: Json | undefined;
  setRuleId: (v: string) => void;
}) {
  const [draft, setDraft] = useState<Json | null>(null),
    [name, setName] = useState(""),
    [masters, setMasters] = useState(""),
    [masterFile, setMasterFile] = useState<File | null>(null),
    [masterInfo, setMasterInfo] = useState<Json | null>(null),
    [sheet, setSheet] = useState(""),
    [mapping, setMapping] = useState<Json>({});
  useEffect(() => {
    if (selected) {
      setDraft(JSON.parse(JSON.stringify(selected.config)));
      setName(selected.name + " · revision");
      setMasters(JSON.stringify(selected.config.masters, null, 2));
    }
  }, [selected?.id]);
  if (!draft || !selected)
    return (
      <Empty title="Loading planning rules">
        The API creates the initial draft from your supplied assumptions.
      </Empty>
    );
  return (
    <>
      <div className="rule-top">
        <label>
          Selected rule version
          <select
            value={selected.id}
            onChange={(e) => setRuleId(e.target.value)}
          >
            {rules.map((r) => (
              <option value={r.id} key={r.id}>
                v{r.id} · {r.name} ({r.state})
              </option>
            ))}
          </select>
        </label>
        <div className="lifecycle">
          {["draft", "simulated", "compared", "approved", "active"].map(
            (s, i) => (
              <span className={s === selected.state ? "current" : ""} key={s}>
                {i > 0 && <ChevronRight size={13} />} {s}
              </span>
            ),
          )}
        </div>
      </div>
      <div className="rule-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Allocation & objectives</h2>
              <p>Edits create a new draft; existing versions are immutable</p>
            </div>
            <Badge tone="gold">
              v{selected.id} · {selected.state}
            </Badge>
          </div>
          <div className="panel-body">
            <label>
              New draft name
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <div className="target-inputs">
              {branches.map((b) => (
                <label key={b}>
                  {b} target %
                  <input
                    type="number"
                    min="1"
                    max="100"
                    step="0.1"
                    value={draft.targets[b]}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        targets: {
                          ...draft.targets,
                          [b]: Number(e.target.value),
                        },
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <div className="form-row">
              <label>
                Aged threshold (days)
                <input
                  type="number"
                  min="1"
                  value={draft.age_days}
                  onChange={(e) =>
                    setDraft({ ...draft, age_days: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Annual turns target
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={draft.annual_turns}
                  onChange={(e) =>
                    setDraft({ ...draft, annual_turns: Number(e.target.value) })
                  }
                />
              </label>
            </div>
            <h3 className="form-subtitle">Objective weights</h3>
            <h3 className="form-subtitle">Allocation target basis</h3>
            {Object.entries(materialNames).map(([key, label]) => (
              <label className="weight-input" key={key}>
                <span>{label}</span>
                <select
                  value={draft.target_basis?.[key] || "cost"}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      target_basis: {
                        ...draft.target_basis,
                        [key]: e.target.value,
                      },
                    })
                  }
                >
                  <option value="weight_g">Net gold weight</option>
                  <option value="cost">Landed cost</option>
                </select>
              </label>
            ))}
            {Object.entries(draft.weights).map(([k, v]) => (
              <label className="weight-input" key={k}>
                <span>{k.replaceAll("_", " ")}</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={String(v)}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      weights: {
                        ...draft.weights,
                        [k]: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
            ))}
            <label className="checkbox">
              <input
                type="checkbox"
                checked={draft.allow_branch_exchange}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    allow_branch_exchange: e.target.checked,
                  })
                }
              />
              Allow branch exchanges through HO
            </label>
            <p className="helper">
              Default: allocate usable HO stock. CZ always stays outside
              ordinary allocation.
            </p>
            <label>
              Assumptions / notes
              <textarea
                rows={3}
                value={draft.notes}
                onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              />
            </label>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Margins & stone economics</h2>
              <p>Provisional costs remain separate from label buying costs</p>
            </div>
            <Gem size={19} />
          </div>
          <div className="panel-body">
            {draft.margins.map((m: Json, i: number) => (
              <div className="margin-card" key={i}>
                <strong>
                  {m.karatage} · {m.variety} · {materialNames[m.material]}
                </strong>
                <div className="form-row">
                  <label>
                    Margin %
                    <input
                      type="number"
                      step="0.01"
                      value={m.percent}
                      onChange={(e) => {
                        const margins = [...draft.margins];
                        margins[i] = { ...m, percent: Number(e.target.value) };
                        setDraft({ ...draft, margins });
                      }}
                    />
                  </label>
                  <label>
                    Basis
                    <select
                      value={m.basis || ""}
                      onChange={(e) => {
                        const margins = [...draft.margins];
                        margins[i] = { ...m, basis: e.target.value || null };
                        setDraft({ ...draft, margins });
                      }}
                    >
                      <option value="">Unconfirmed</option>
                      <option value="net_sale_value">Net sale value</option>
                      <option value="cost_markup">Cost markup</option>
                      <option value="revenue_margin">Revenue margin</option>
                    </select>
                  </label>
                </div>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={m.confirmed}
                    onChange={(e) => {
                      const margins = [...draft.margins];
                      margins[i] = { ...m, confirmed: e.target.checked };
                      setDraft({ ...draft, margins });
                    }}
                  />
                  Basis confirmed
                </label>
              </div>
            ))}
            <div className="quiet-note">
              Net sale value = gold weight × current RG rate + making. Supply
              that exact value in the export mapping.
            </div>
            <div className="form-row">
              <label>
                Natural diamond ₹/ct
                <input
                  type="number"
                  value={draft.stone_economics.natural_diamond_cost_per_carat}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      stone_economics: {
                        ...draft.stone_economics,
                        natural_diamond_cost_per_carat: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
              <label>
                Lab-grown diamond ₹/ct
                <input
                  type="number"
                  value={draft.stone_economics.lab_diamond_cost_per_carat}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      stone_economics: {
                        ...draft.stone_economics,
                        lab_diamond_cost_per_carat: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
            </div>
            <Badge tone="gold">
              Provisional · not substituted into landed cost
            </Badge>
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Editable master rules</h2>
            <p>
              Items, karatages, varieties, suppliers and L/M/H classifications
            </p>
          </div>
        </div>
        <div className="panel-body">
          <label>
            Master definitions (JSON)
            <textarea
              className="code-editor"
              rows={12}
              value={masters}
              onChange={(e) => setMasters(e.target.value)}
            />
          </label>
          <p className="helper">
            L/M/H entries require item plus class, or light_max_g and
            medium_max_g weight bands; optional karatage, variety and supplier
            match exactly. L/M/H is a master classification, not evidence of
            sales velocity.
          </p>
          <button
            className="primary"
            disabled={busy || !actor.trim() || !name.trim()}
            onClick={() =>
              perform(async () => {
                const r = await api("/rules", {
                  actor,
                  name,
                  parent_id: selected.id,
                  config: { ...draft, masters: JSON.parse(masters) },
                });
                setRuleId(String(r.id));
              }, "New draft saved; simulate and compare before approval")
            }
          >
            <Plus size={16} /> Save as new draft
          </button>
          <div className="rule-actions">
            <button
              className="secondary"
              disabled={busy || !actor.trim() || selected.state !== "compared"}
              onClick={() =>
                perform(
                  () => api("/rules/" + selected.id + "/approve", { actor }),
                  "Rule approved",
                )
              }
            >
              Approve compared rule
            </button>
            <button
              className="primary"
              disabled={busy || !actor.trim() || selected.state !== "approved"}
              onClick={() =>
                perform(
                  () => api("/rules/" + selected.id + "/activate", { actor }),
                  "Rule activated",
                )
              }
            >
              Activate approved rule
            </button>
          </div>
          <details>
            <summary>Import supplied planning workbook</summary>
            <p>
              Imports literal Weight Master bands into a new draft and retains
              target/mix source cells for review. Formulas and older proposals
              never execute.
            </p>
            <input
              type="file"
              accept=".xlsx"
              aria-label="Right Gold planning workbook"
              disabled={busy || !actor.trim()}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                perform(async () => {
                  const form = new FormData();
                  form.append("file", f);
                  form.append("actor", actor);
                  const r = await api(
                    "/rules/" + selected.id + "/planning-workbook",
                    form,
                  );
                  setRuleId(String(r.id));
                }, "Planning workbook retained; provisional bands imported into a new draft");
              }}
            />
          </details>
          <details>
            <summary>
              Import canonical masters from Excel into a new draft
            </summary>
            <a href="/api/imports/template/masters">
              Download blank masters template
            </a>
            <input
              type="file"
              accept=".xlsx"
              aria-label="Master rules workbook"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setMasterFile(f);
                perform(async () => {
                  const form = new FormData();
                  form.append("file", f);
                  const info = await api("/imports/inspect", form);
                  setMasterInfo(info);
                  setSheet(info.sheets[0].name);
                  const headers = info.sheets[0].headers;
                  setMapping(
                    Object.fromEntries(
                      [
                        "type",
                        "value",
                        "item",
                        "class",
                        "karatage",
                        "variety",
                        "supplier",
                      ]
                        .filter((k) => headers.includes(k))
                        .map((k) => [k, k]),
                    ),
                  );
                }, "Master workbook inspected");
              }}
            />
            {masterInfo && (
              <>
                <label>
                  Sheet
                  <select
                    value={sheet}
                    onChange={(e) => {
                      setSheet(e.target.value);
                      setMapping({});
                    }}
                  >
                    {masterInfo.sheets.map((s: Json) => (
                      <option key={s.name}>{s.name}</option>
                    ))}
                  </select>
                </label>
                {[
                  "type",
                  "value",
                  "item",
                  "class",
                  "karatage",
                  "variety",
                  "supplier",
                ].map((k) => (
                  <label className="mapping-row" key={k}>
                    {k}
                    <select
                      value={mapping[k] || ""}
                      onChange={(e) =>
                        setMapping({ ...mapping, [k]: e.target.value })
                      }
                    >
                      <option value="">Not mapped</option>
                      {masterInfo.sheets
                        .find((s: Json) => s.name === sheet)
                        ?.headers.filter(Boolean)
                        .map((h: string) => (
                          <option key={h}>{h}</option>
                        ))}
                    </select>
                  </label>
                ))}
                <button
                  className="secondary"
                  disabled={
                    busy || !actor.trim() || !mapping.type || !mapping.value
                  }
                  onClick={() =>
                    perform(async () => {
                      const f = new FormData();
                      f.append("file", masterFile!);
                      f.append("sheet", sheet);
                      f.append("actor", actor);
                      f.append(
                        "mapping",
                        JSON.stringify(
                          Object.fromEntries(
                            Object.entries(mapping).filter(([, v]) => v),
                          ),
                        ),
                      );
                      const r = await api(
                        "/rules/" + selected.id + "/masters",
                        f,
                      );
                      setRuleId(String(r.id));
                    }, "Master-source workbook retained and new rule draft saved")
                  }
                >
                  Import master rules
                </button>
              </>
            )}
          </details>
        </div>
      </section>
    </>
  );
}

function Proposals({
  simulations,
  data,
  selectedRule,
  rules,
  setRuleId,
  snapshots,
  salesId,
  setSalesId,
  actor,
  busy,
  material,
  perform,
}: ActionProps & {
  simulations: Json[];
  data: Json | null;
  selectedRule: Json | undefined;
  rules: Json[];
  setRuleId: (v: string) => void;
  snapshots: Json[];
  salesId: string;
  setSalesId: (v: string) => void;
  material: string;
}) {
  const [simId, setSimId] = useState(""),
    [reference, setReference] = useState("");
  const current =
    simulations.find((s) => String(s.id) === simId) || simulations[0];
  return (
    <>
      <section className="simulation-banner">
        <div>
          <Scale size={26} />
          <div>
            <h2>Simulate before you move.</h2>
            <p>
              Usable HO stock by default. Whole sets preserved. Branch exchanges
              always route through HO.
            </p>
          </div>
        </div>
        <div className="simulation-form">
          <label>
            Rule version
            <select
              value={selectedRule?.id || ""}
              onChange={(e) => setRuleId(e.target.value)}
            >
              {rules.map((r) => (
                <option value={r.id} key={r.id}>
                  v{r.id} · {r.state}
                </option>
              ))}
            </select>
          </label>
          <label>
            Historical sales
            <select
              value={salesId}
              onChange={(e) => setSalesId(e.target.value)}
            >
              <option value="">No sales history selected</option>
              {snapshots
                .filter((s) => s.kind === "sales" && s.status === "reconciled")
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    #{s.id} · through {s.as_of}
                  </option>
                ))}
            </select>
          </label>
          <button
            className="primary"
            disabled={
              busy || !data?.snapshot_id || !selectedRule || !actor.trim()
            }
            onClick={() =>
              perform(async () => {
                const sim = await api("/simulations", {
                  snapshot_id: data!.snapshot_id,
                  sales_snapshot_id: salesId ? Number(salesId) : null,
                  rule_id: selectedRule!.id,
                  actor,
                });
                setSimId(String(sim.id));
              }, "Simulation saved; review and compare its results")
            }
          >
            <Sparkles size={16} />
            Run simulation
          </button>
        </div>
        <p className="helper">
          No sales history: availability, realised-profit and demand-led
          reactivation cannot be scored. Cost and aged-cost balancing remain
          available.
        </p>
      </section>
      {!current ? (
        <section className="panel">
          <Empty icon={Scale} title="Your first proposal is a simulation away">
            Reconcile all five branches and HO, choose a rule version and run
            the solver. CZ is flagged separately for priority recall.
          </Empty>
        </section>
      ) : (
        <>
          <div className="simulation-selector">
            <label>
              Saved simulation
              <select
                value={current.id}
                onChange={(e) => setSimId(e.target.value)}
              >
                {simulations.map((s) => (
                  <option value={s.id} key={s.id}>
                    #{s.id} · Stock #{s.snapshot_id} · Rule v{s.rule_id}
                  </option>
                ))}
              </select>
            </label>
            <Badge tone="green">{current.status}</Badge>
            <button
              className="secondary"
              onClick={() =>
                download(current, "rg-simulation-" + current.id + ".json")
              }
            >
              <ArrowDownToLine size={15} />
              Export full decision record
            </button>
            <button
              className="secondary"
              disabled={busy || !actor.trim()}
              onClick={() =>
                perform(
                  () =>
                    api("/simulations/" + current.id + "/compare", { actor }),
                  "Comparison saved on identical source snapshots",
                )
              }
            >
              Compare against active rules
            </button>
          </div>
          <div className="notice-box">
            <ShieldCheck size={18} />
            <div>
              <strong>
                Simulation #{current.id} · Stock #{current.snapshot_id} · Rule v
                {current.rule_id}
              </strong>
              <p>
                {current.assumptions.pool} · age basis:{" "}
                {current.assumptions.age_basis} ·{" "}
                {current.sales_snapshot_id
                  ? "Sales #" + current.sales_snapshot_id
                  : "Sales history unavailable"}
              </p>
            </div>
          </div>
          <div className="objective-notes">
            {Object.entries(current.result.objectives).map(([k, v]) => (
              <div key={k}>
                <strong>{k.replaceAll("_", " ")}</strong>
                <p>{String(v)}</p>
              </div>
            ))}
          </div>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Projected branch health</h2>
                <p>
                  After proposals · {materialNames[material]} · no physical
                  stock has moved
                </p>
              </div>
              <Badge>{current.result.proposals.length} proposed groups</Badge>
            </div>
            <BranchTable
              rows={current.result.after.filter(
                (r: Json) => r.material === material,
              )}
              targets={current.assumptions.rules.targets}
            />
            <details className="panel-body">
              <summary>Before allocation</summary>
              <BranchTable
                rows={current.result.before.filter(
                  (r: Json) => r.material === material,
                )}
                targets={current.assumptions.rules.targets}
              />
            </details>
            {current.comparison && (
              <details className="panel-body" open>
                <summary>
                  Compared with {current.comparison.baseline_name}
                </summary>
                <p>
                  Proposal-count difference:{" "}
                  {current.comparison.proposal_count_delta}. Same stock #
                  {current.comparison.same_stock_snapshot} and sales{" "}
                  {current.comparison.same_sales_snapshot ?? "unavailable"}.
                </p>
                <BranchTable
                  rows={current.comparison.baseline_result.after.filter(
                    (r: Json) => r.material === material,
                  )}
                  targets={current.comparison.baseline_config.targets}
                />
              </details>
            )}
          </section>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Label-level movement proposals</h2>
                <p>
                  Approve execution separately, then record each dispatch and
                  receipt.
                </p>
              </div>
              <Truck size={20} />
            </div>
            <div className="table-toolbar">
              <label className="reference-input">
                Dispatch / receipt reference
                <input
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                  placeholder="Document or approval reference"
                />
              </label>
              <small>Operator name is required for every action.</small>
            </div>
            {current.transfers.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Group / labels</th>
                      <th>Purpose</th>
                      <th>Route</th>
                      <th>Original ages</th>
                      <th>Status</th>
                      <th>Next action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.transfers
                      .filter((t: Json) => {
                        const p = [
                          ...current.result.proposals,
                          ...current.result.priority_recalls,
                        ].find((p: Json) => p.group_key === t.group_key);
                        return p?.material === material;
                      })
                      .map((t: Json) => {
                        const p = [
                          ...current.result.proposals,
                          ...current.result.priority_recalls,
                        ].find((p: Json) => p.group_key === t.group_key);
                        const action =
                          t.status === "proposed"
                            ? "approve"
                            : ["approved", "at_ho"].includes(t.status)
                              ? "dispatch"
                              : t.status === "dispatched"
                                ? "receive"
                                : null;
                        return (
                          <tr key={t.id}>
                            <td>
                              <strong>{t.group_key}</strong>
                              <small className="cell-note">
                                {t.labels.join(", ")}
                              </small>
                              <small className="cell-note">
                                {money(p?.cost_paise)}
                              </small>
                            </td>
                            <td>
                              <Badge
                                tone={
                                  t.purpose === "priority_recall"
                                    ? "gold"
                                    : "neutral"
                                }
                              >
                                {t.purpose.replace("_", " ")}
                              </Badge>
                            </td>
                            <td>
                              {t.route.join(" → ")}
                              <small className="cell-note">
                                Leg {t.leg + 1} / {t.route.length - 1}
                              </small>
                            </td>
                            <td>
                              {Object.entries(
                                p?.original_received_at || {},
                              ).map(([k, v]) => (
                                <small className="cell-note" key={k}>
                                  {k}: {String(v)}
                                </small>
                              ))}
                            </td>
                            <td>
                              <Badge
                                tone={
                                  t.status === "received" ? "green" : "neutral"
                                }
                              >
                                {t.status.replace("_", " ")}
                              </Badge>
                            </td>
                            <td>
                              {action ? (
                                <button
                                  className="secondary"
                                  disabled={
                                    busy || !actor.trim() || !reference.trim()
                                  }
                                  onClick={() =>
                                    perform(
                                      () =>
                                        api("/transfers/" + t.id + "/action", {
                                          actor,
                                          action,
                                          reference,
                                        }),
                                      action + " recorded",
                                    )
                                  }
                                >
                                  {action}
                                </button>
                              ) : (
                                <span>Complete</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty icon={Check} title="No movements proposed">
                The solver retained the current placement under these rules.
              </Empty>
            )}
          </section>
          {current.result.excluded.length > 0 && (
            <div className="alert error">
              <CircleHelp size={17} />
              {current.result.excluded.length} groups excluded due to incomplete
              landed costs. See the full decision export for labels.
            </div>
          )}
          <details className="panel">
            <summary className="panel-body">
              Solver diagnostics & limitations
            </summary>
            <pre>
              {JSON.stringify(
                {
                  diagnostics: current.result.diagnostics,
                  limitations: current.result.limitations,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      )}
    </>
  );
}
