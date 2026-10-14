"use client";
import { FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, type NewsEvent, type NewsFeasibility, type NewsHistory, type SymbolRow } from "@/lib/api";
import { LESSONS, type Lesson } from "@/lib/lessons";

type Health = { ok: boolean; auto_trading_enabled: boolean; sessions: number };
type Status = {
  current_session: string; next_event_type: string | null; next_event_time: string | null;
  ai_learning: {
    status: "learning" | "active" | "paused" | "error";
    reason: string; learning_bar: number; threshold: number; trades_analyzed: number;
    model_version: string | null; wf_passed: boolean;
  } | null;
};
type AccountSummary = {
  currency: string; balance: number; equity: number; free_margin: number;
  floating_profit: number; floating_loss: number; net_floating_pnl: number;
  realized_today: number; open_positions: number;
};
type SetupState = "signal" | "near" | "watching" | "closed";
type EngulfingVote = { timeframe: string; vote: "BUY" | "SELL" | "NO SIGNAL"; reason: string };
type HigherTimeframeVote = {
  timeframe: string; trend: "BUY" | "SELL" | "NEUTRAL" | "UNAVAILABLE"; aligned: boolean;
};
type Setup = {
  symbol: string; strategy: string; score: number; threshold: number; direction: string | null;
  state: SetupState; live: boolean; reason: string; updated_at: string; has_open_position: boolean;
  pinned: boolean; priority: number; market_closed?: boolean; engulfing_votes?: EngulfingVote[];
  higher_timeframe_votes?: HigherTimeframeVote[];
};
type Position = {
  symbol: string; side: string; volume: number; entry: number; stop_loss: number | null;
  take_profit: number | null; floating_profit: number; strategy: string;
};
type Line = { id: number; ts: string; level: string; symbol: string | null; text: string };

function usePoll(fn: () => void | Promise<void>, ms: number) {
  const ref = useRef(fn); ref.current = fn;
  useEffect(() => { ref.current(); const t = setInterval(() => ref.current(), ms); return () => clearInterval(t); }, [ms]);
}

function TopBar({ health, refresh, connected, session, onDisconnect }: {
  health: Health | null; refresh: () => void; connected: boolean; session: string | null;
  onDisconnect: () => void;
}) {
  const [key, setKey] = useState(""); const [busy, setBusy] = useState(false); const [msg, setMsg] = useState("");
  const killed = health && !health.auto_trading_enabled;
  const run = async (path: string, ask: string) => {
    if (!key || !confirm(ask)) return;
    setBusy(true); setMsg("");
    try {
      const r = await api<{ positions_closed?: number; fully_flat?: boolean }>(path, { method: "POST", key });
      setMsg(r.positions_closed !== undefined ? `closed ${r.positions_closed} · ${r.fully_flat ? "flat" : "NOT FLAT - check broker"}` : "re-armed");
      refresh();
    } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <header className="top">
      <span className="brand">SOUL</span>
      <span className={`pill ${!health ? "na" : killed ? "off" : "on"}`}><i />{!health ? "OFFLINE" : killed ? "KILLED" : "ACTIVE"}</span>
      <div className="kill">
        {connected && <span className="session-indicator">SESSION <strong>{session ?? "--"}</strong></span>}
        {connected && <button className="btn disconnect" title="Disconnect this dashboard view; open trades are not closed."
          onClick={onDisconnect}>DISCONNECT VIEW</button>}
        <input type="password" placeholder="shutdown key" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
        {killed
          ? <button className="btn go" disabled={busy || !key} onClick={() => run("/api/v1/system/resume", "Re-arm auto-trading?")}>RE-ARM</button>
          : <button className="btn danger" disabled={busy || !key} onClick={() => run("/api/v1/system/emergency-shutdown", "Disable auto-trading and CLOSE ALL open trades now?")}>EMERGENCY SHUTDOWN</button>}
        <span className="dim">{msg}</span>
      </div>
    </header>
  );
}

function Gauge({ setup }: { setup: Setup }) {
  const v = Math.max(0, Math.min(100, setup.score)); const L = 251.3;
  const hot = setup.state === "signal"; const col = hot ? "var(--green)" : "#7B8AA8";
  return (
    <div className="gauge">
      <div className="sym">{setup.symbol}</div>
      <svg viewBox="0 0 180 100">
        <path d="M10 90 A80 80 0 0 1 170 90" fill="none" stroke="#1E293B" strokeWidth="12" strokeLinecap="round" />
        <path d="M10 90 A80 80 0 0 1 170 90" fill="none" stroke={col} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={`${(L * v) / 100} ${L}`} style={{ filter: hot ? "drop-shadow(0 0 6px #00FF9C)" : "none", transition: "all .6s" }} />
      </svg>
      <div className="val" style={{ color: col }}>{v.toFixed(0)}%</div>
      <div className="why">{setup.score.toFixed(0)} / {setup.threshold.toFixed(0)} threshold</div>
    </div>
  );
}

function Countdown({ iso, label }: { iso: string | null; label: string | null }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  if (!iso) return <div className="dim">No high-impact event scheduled</div>;
  const s = Math.max(0, Math.floor((new Date(iso).getTime() - now) / 1000));
  const p = (n: number) => String(n).padStart(2, "0"); const d = Math.floor(s / 86400);
  return (<>
    <div className="dim" style={{ marginBottom: 6 }}>{label} · {new Date(iso).toLocaleString()}</div>
    <div className={`count ${s < 300 ? "soon" : ""}`}>{d > 0 ? `${d}d ` : ""}{p(Math.floor((s % 86400) / 3600))}:{p(Math.floor((s % 3600) / 60))}:{p(s % 60)}</div>
  </>);
}

function LearningBar({ status }: { status: Status["ai_learning"] | undefined }) {
  if (status === undefined) {
    return <div className="card learning-card"><h3>AI LEARNING</h3><div className="dim">Waiting for AI status…</div></div>;
  }
  if (status === null) {
    return <div className="card learning-card"><h3>AI LEARNING</h3>
      <div className="dim">AI meta-layer is not configured.</div></div>;
  }
  const progress = Math.max(0, Math.min(100, status.learning_bar));
  const target = Math.max(0, Math.min(100, status.threshold));
  return (
    <section className={`card learning-card learning-${status.status}`} aria-label="AI learning progress">
      <div className="learning-head">
        <h3>AI LEARNING</h3>
        <span className={`badge learning-badge learning-badge-${status.status}`}>{status.status}</span>
      </div>
      <div className="learning-track" role="progressbar" aria-valuenow={progress}
        aria-valuemin={0} aria-valuemax={100} aria-label="Model learning bar">
        <div className="learning-fill" style={{ width: `${progress}%` }} />
        <div className="learning-threshold" style={{ left: `${target}%` }} />
      </div>
      <div className="learning-stats">
        <strong>{progress.toFixed(1)}%</strong>
        <span>{status.trades_analyzed} labeled trades</span>
        <span>activation target {target.toFixed(0)}%</span>
      </div>
      <div className="dim learning-reason">{status.reason}</div>
      <div className="dim learning-model">
        Model {status.model_version ?? "not trained yet"} · walk-forward {status.wf_passed ? "passed" : "pending"}
      </div>
    </section>
  );
}

const LEVELS = ["event", "signal", "skip", "learn", "risk", "close", "error", "info"] as const;

function Terminal({ lines }: { lines: Line[] }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState<Set<string>>(new Set());
  const [follow, setFollow] = useState(true);
  const end = useRef<HTMLDivElement>(null);

  const q = query.trim().toLowerCase();
  const filtered = lines.filter((l) => {
    if (active.size && !active.has(l.level)) return false;
    if (q && !(`${l.text} ${l.symbol ?? ""} ${l.level}`.toLowerCase().includes(q))) return false;
    return true;
  });

  useEffect(() => { if (follow) end.current?.scrollIntoView({ block: "end" }); }, [filtered.length, follow]);

  const toggleLevel = (lv: string) =>
    setActive((prev) => { const n = new Set(prev); n.has(lv) ? n.delete(lv) : n.add(lv); return n; });

  return (
    <div className="explainer">
      <div className="explainer-toolbar">
        <input className="explainer-search" placeholder="Search the feed…" value={query}
          onChange={(e) => setQuery(e.target.value)} aria-label="Search Soul Explainer" />
        <div className="explainer-filters">
          {LEVELS.map((lv) => (
            <button key={lv} className={`lvchip lv-${lv} ${active.has(lv) ? "is-on" : ""}`}
              onClick={() => toggleLevel(lv)} title={`Toggle ${lv}`}>{lv}</button>
          ))}
          {active.size > 0 && <button className="lvchip clear" onClick={() => setActive(new Set())}>clear</button>}
        </div>
        <label className="explainer-follow">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow
        </label>
        <span className="explainer-count">{filtered.length}/{lines.length}</span>
      </div>
      <pre className="term">
        {lines.length === 0 && <div className="dim">$ waiting for the engine to explain itself…</div>}
        {lines.length > 0 && filtered.length === 0 &&
          <div className="dim">$ no lines match the current filter.</div>}
        {filtered.map((l) => (
          <div key={l.id} className={`lv-${l.level}`}>
            <span className="ts">{new Date(l.ts).toLocaleTimeString()}</span>
            <span className={`lvtag lv-${l.level}`}>{l.level}</span>
            {l.symbol && <span className="lvsym">{l.symbol}</span>}
            <span className="lvtext">{l.text}</span>
          </div>
        ))}
        <div ref={end} />
      </pre>
    </div>
  );
}

function EngulfingVotes({ votes }: { votes?: EngulfingVote[] }) {
  if (!votes?.length) return null;
  return (
    <div className="engulfing-votes" aria-label="Engulfing strategy votes">
      <span className="engulfing-votes-title">ENGULFING VOTE</span>
      {votes.map((item) => (
        <span className={`engulf-vote ${item.vote.toLowerCase().replace(" ", "-")}`}
          key={item.timeframe} title={item.reason}>
          {item.timeframe} <strong>{item.vote}</strong>
        </span>
      ))}
    </div>
  );
}

function HigherTimeframeVotes({ votes }: { votes?: HigherTimeframeVote[] }) {
  if (!votes?.length) return null;
  return (
    <div className="engulfing-votes" aria-label="Higher timeframe trend context">
      <span className="engulfing-votes-title">HTF TREND</span>
      {votes.map((item) => (
        <span className={`engulf-vote ${item.aligned ? "buy" : ""}`}
          key={item.timeframe}>
          {item.timeframe} <strong>{item.trend}{item.aligned ? " · +5" : ""}</strong>
        </span>
      ))}
    </div>
  );
}

function LessonCard({ lesson }: { lesson: Lesson }) {
  return (
    <div className="lesson-body">
      <div className="lesson-edge">{lesson.edge}</div>
      <div className="lesson-block">
        <span className="lesson-label">WHAT TO LOOK FOR</span>
        <ul className="lesson-list">
          {lesson.watch.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      </div>
      <div className="lesson-row"><span className="lesson-label">ENTRY</span><span>{lesson.entry}</span></div>
      <div className="lesson-row"><span className="lesson-label">EXIT</span><span>{lesson.exit}</span></div>
      <div className="lesson-row"><span className="lesson-label">SESSION</span><span>{lesson.session}</span></div>
      <div className="lesson-row"><span className="lesson-label">RISK NOTE</span><span>{lesson.risk}</span></div>
    </div>
  );
}

/* Teaches one strategy at a time, and jumps into a live "brief" whenever a
   symbol has an open position or an active/near setup. */
function StrategyTutor({ setups, positions }: { setups: Setup[]; positions: Position[] }) {
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const order = useMemo(() => Object.keys(LESSONS), []);

  // Highest-priority live subject: open position > signal > near.
  const live = useMemo(() => {
    const ranked = setups
      .filter((s) => s.live && (s.has_open_position || s.state === "signal" || s.state === "near"))
      .sort((a, b) => a.priority - b.priority);
    return ranked[0] ?? null;
  }, [setups]);

  const openPos = live ? positions.find((p) => symbolMatches(p, live.symbol)) : undefined;

  useEffect(() => {
    if (live || paused) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % order.length), 8000);
    return () => clearInterval(t);
  }, [live, paused, order.length]);

  const lessonSymbol = live ? live.symbol : order[idx % order.length];
  const lesson = LESSONS[lessonSymbol] ?? LESSONS[order[0]];
  const step = (d: number) => setIdx((i) => (i + d + order.length) % order.length);

  const stateLabel = live
    ? live.has_open_position ? "OPEN POSITION" : live.state === "signal" ? "LIVE SIGNAL" : "NEAR SETUP"
    : "STRATEGY LESSON";
  const stateClass = live
    ? live.has_open_position ? "open" : live.state === "signal" ? "signal" : "near"
    : "lesson";

  return (
    <section className="card tutor-section" aria-label="Strategy tutor">
      <div className="tutor-head">
        <h3>STRATEGY TUTOR</h3>
        <span className={`tutor-state tutor-${stateClass}`}>{stateLabel}</span>
      </div>

      {live && (
        <div className="tutor-livebar">
          <span className="tutor-sym">{live.symbol}</span>
          <span className="tutor-score">{live.score.toFixed(0)}/{live.threshold.toFixed(0)}</span>
          {live.direction && <span className={`tutor-dir ${live.direction.toLowerCase()}`}>{live.direction}</span>}
          <span className="tutor-reason">{live.reason}</span>
        </div>
      )}
      {live && <EngulfingVotes votes={live.engulfing_votes} />}
      {live && <HigherTimeframeVotes votes={live.higher_timeframe_votes} />}
      {openPos && (
        <div className="tutor-pos">
          <span>{openPos.side} {openPos.volume}</span>
          <span>entry <strong>{openPos.entry}</strong></span>
          <span>SL <strong className="neg">{openPos.stop_loss ?? "—"}</strong></span>
          <span>TP <strong className="pos">{openPos.take_profit ?? "—"}</strong></span>
          <span className={openPos.floating_profit >= 0 ? "pos" : "neg"}>{openPos.floating_profit}</span>
        </div>
      )}

      <div className="tutor-titlebar">
        <div className="tutor-name"><strong>{lessonSymbol}</strong><span>{lesson.name}</span></div>
        {!live && (
          <div className="tutor-controls">
            <button onClick={() => step(-1)} title="Previous strategy">‹</button>
            <button onClick={() => setPaused((p) => !p)} title={paused ? "Resume tour" : "Pause tour"}>
              {paused ? "▶" : "❚❚"}
            </button>
            <button onClick={() => step(1)} title="Next strategy">›</button>
            <span className="tutor-count">{(idx % order.length) + 1}/{order.length}</span>
          </div>
        )}
      </div>
      <LessonCard lesson={lesson} />
    </section>
  );
}

function AccountCards({ account, error }: { account: AccountSummary | null; error: string }) {
  const money = (value: number) => new Intl.NumberFormat(undefined, {
    style: "currency", currency: account?.currency ?? "USD",
  }).format(value);
  const cards = [
    { label: "BALANCE", value: account ? money(account.balance) : "--", className: "" },
    {
      label: "OPEN P/L",
      value: account ? money(account.net_floating_pnl) : "--",
      className: account && account.net_floating_pnl < 0 ? "negative" : "positive",
    },
    {
      label: "REALIZED TODAY",
      value: account ? money(account.realized_today) : "--",
      className: account && account.realized_today < 0 ? "negative" : "positive",
    },
  ];
  return (
    <section className="account-cards" aria-label="Account balance and open trade profit and loss">
      {cards.map((card) => (
        <article className="account-card card" key={card.label}>
          <h3>{card.label}</h3>
          <div className={`account-value ${card.className}`}>{card.value}</div>
          <div className="dim">
            {card.label === "BALANCE"
              ? account ? `Equity ${money(account.equity)}` : error || "Waiting for local MT5 account"
              : card.label === "OPEN P/L"
                ? error || (account ? `${account.open_positions} open position(s)` : "Waiting for local MT5 account")
                : "Closed trades today"}
          </div>
        </article>
      ))}
    </section>
  );
}

function TabBar({ tab, setTab, badges }: {
  tab: "overview" | "trade" | "symbols" | "news";
  setTab: (t: "overview" | "trade" | "symbols" | "news") => void;
  badges: { trade?: number; news?: number };
}) {
  const tabs: { key: typeof tab; label: string; badge?: number; alert?: boolean }[] = [
    { key: "overview", label: "Overview" },
    { key: "trade", label: "Trade", badge: badges.trade },
    { key: "symbols", label: "Symbols" },
    { key: "news", label: "News", badge: badges.news, alert: (badges.news ?? 0) > 0 },
  ];
  return (
    <nav className="tabbar" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={tab === t.key}
          className={`tabbtn ${tab === t.key ? "is-active" : ""}`}
          onClick={() => setTab(t.key)}>
          {t.label}
          {t.badge ? <span className={`tabbadge ${t.alert ? "alert" : ""}`}>{t.badge}</span> : null}
        </button>
      ))}
    </nav>
  );
}

function NewsEventsPanel({ events, token, halted, onAction }: {
  events: NewsEvent[];
  token: string | null;
  halted: boolean;
  onAction: (eventKey: string, symbol: string, action: "confirm" | "skip") => void;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const zar = (v: number) => `R${Math.round(v).toLocaleString()}`;

  if (!events.length) {
    return (
      <section className="card news-card">
        <div className="symbols-heading"><h3>NEWS EVENTS</h3></div>
        <div className="empty">No upcoming high-impact events scheduled.</div>
      </section>
    );
  }

  return (
    <section className="card news-card">
      <div className="symbols-heading">
        <h3>NEWS EVENTS</h3>
        {halted && <span className="symbol-halted-banner">KILL SWITCH · CONFIRM DISABLED</span>}
      </div>
      {events.map((ev) => {
        const ms = new Date(ev.event_time).getTime() - now;
        const mins = ms / 60000;
        const inWindow = mins <= 6 && mins > -0.02;   // CONFIRM visible from T-6m
        const passed = ms <= 0;
        const cd = passed ? "RELEASED"
          : `${String(Math.floor(mins)).padStart(2, "0")}:${String(Math.floor((-ms) % 60000 / 1000)).padStart(2, "0")}`;
        return (
          <article className="news-event" key={ev.event_key}>
            <div className="news-event-head">
              <div>
                <strong>{ev.event_type}</strong> <span className="dim">{ev.title}</span>
              </div>
              <span className={`news-countdown ${inWindow && !passed ? "soon" : ""}`}>{cd}</span>
            </div>
            <div className="dim news-meta">
              {ev.currency} · forecast {ev.forecast ?? "--"} · previous {ev.previous ?? "--"}
            </div>
            {ev.symbols.length === 0 && <div className="empty">Bias not generated yet (regenerates at T-30/T-15/T-6).</div>}
            {ev.symbols.map((sp) => {
              const f = sp.feasibility || ({} as NewsFeasibility);
              const progress = sp.achieved_target_zar != null
                ? Math.min(100, (sp.achieved_target_zar / 15000) * 100) : 0;
              return (
                <div className={`news-sym ${sp.direction === "BUY" ? "buy" : sp.direction === "SELL" ? "sell" : ""}`} key={sp.symbol}>
                  <div className="news-sym-head">
                    <strong>{sp.symbol}</strong>
                    <span className={`badge state-${sp.direction === "BUY" ? "signal" : sp.direction === "SELL" ? "near" : "watching"}`}>{sp.direction}</span>
                    {sp.dry_run && <span className="badge">DRY-RUN</span>}
                    {sp.confirmed && <span className="badge state-signal">CONFIRMED</span>}
                    {sp.skipped && <span className="badge">SKIPPED</span>}
                    <span className="dim">{sp.status}</span>
                  </div>
                  {sp.direction !== "NO_TRADE" && (
                    <>
                      <div className="news-plan-grid">
                        <span><small>REF</small> {f.reference_price ?? "--"}</span>
                        <span><small>TARGET</small> {sp.target_level ?? "--"}</span>
                        <span><small>BUFFER</small> {f.spike_buffer_points ?? 0} pts</span>
                        <span><small>ORDERS</small> {f.orders_needed ?? sp.orders.length}</span>
                        <span><small>MOVE→T</small> {f.required_move_points ?? 0} pts{f.required_move_pct_of_p80 != null ? ` (${Math.round(f.required_move_pct_of_p80 * 100)}% of p80)` : ""}</span>
                        <span><small>WORST</small> {zar(f.worst_case_loss_zar ?? 0)}</span>
                      </div>
                      {f.above_p80 && <div className="err">⚠ Required move exceeds the historical p80 move.</div>}
                      <div className="news-target-bar" aria-label="R15k target progress">
                        <span style={{ width: `${progress}%` }} />
                        <em>{zar(sp.achieved_target_zar ?? 0)} / R15,000</em>
                      </div>
                      <div className="news-orders">
                        {sp.orders.map((o, i) => (
                          <span key={i} className="dim">{o.order_type} @ {o.entry_price} · {o.lots} lots · +{Math.round(o.profit_at_target_zar)}</span>
                        ))}
                      </div>
                      {inWindow && !passed && !sp.confirmed && !sp.skipped && (
                        <div className="news-actions">
                          <button className="btn news-confirm" disabled={halted || !token}
                            onClick={() => onAction(ev.event_key, sp.symbol, "confirm")}>
                            CONFIRM
                          </button>
                          <button className="btn danger" disabled={!token}
                            onClick={() => onAction(ev.event_key, sp.symbol, "skip")}>
                            SKIP
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </article>
        );
      })}
    </section>
  );
}

function NewsHistoryCard({ token }: { token: string | null }) {
  const [hist, setHist] = useState<NewsHistory | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!token) { setHist(null); return; }
    let alive = true;
    const load = () => api<NewsHistory>("/api/v1/news-events/history", { token })
      .then((h) => { if (alive) { setHist(h); setError(""); } })
      .catch((e: unknown) => {
        if (!alive) return;
        setError(e instanceof ApiError ? e.message : String(e));
      });
    load();
    const t = setInterval(load, 30000);
    return () => { alive = false; clearInterval(t); };
  }, [token]);

  const acc = hist?.accuracy ?? { correct: 0, total: 0, accuracy: 0 };
  const accPct = acc.total ? Math.round(acc.accuracy * 100) : 0;
  const when = (iso: string) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso
      : d.toLocaleString(undefined, {
          day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
          timeZone: "Africa/Johannesburg", timeZoneName: "short",
        });
  };
  const dirBadge = (dir: NewsHistory["recent"][number]["direction"]) =>
    dir === "BUY" ? "state-signal" : dir === "SELL" ? "state-near" : "state-closed";

  return (
    <section className="card news-card">
      <div className="symbols-heading">
        <h3>EVENT HISTORY</h3>
        <span className="badge state-watching">
          ACCURACY {acc.correct}/{acc.total}{acc.total ? ` · ${accPct}%` : ""}
        </span>
      </div>
      {error && <div className="err">{error}</div>}
      {!hist && !error && <div className="empty">Loading prediction history…</div>}
      {hist && hist.recent.length === 0 && (
        <div className="empty">
          No event predictions logged yet. Each high-impact call is recorded here and scored
          once the event passes, so this card becomes the running accuracy of the bias engine.
        </div>
      )}
      {hist && hist.recent.length > 0 && (
        <div className="news-event hist-list">
          <div className="hist-row hist-head">
            <span>EVENT</span><span>CALL</span><span>WHAT HAPPENED</span>
          </div>
          {hist.recent.map((r, i) => (
            <div className="hist-row" key={`${r.event_type}-${r.event_time}-${r.symbol}-${i}`}>
              <span className="hist-ev">
                <strong>{r.event_type}</strong>
                <span className="dim">{r.symbol}</span>
                <small className="dim">{when(r.event_time)}</small>
              </span>
              <span className="hist-call">
                <span className={`badge ${dirBadge(r.direction)}`}>{r.direction}</span>
                <span className="dim">{Math.round(r.probability_pct)}%</span>
              </span>
              <span className="hist-res">
                {r.actual_direction === null || r.actual_direction === undefined ? (
                  <span className="dim">awaiting outcome</span>
                ) : (
                  <>
                    <span className={`hist-move ${
                      r.actual_direction === "BUY" ? "up" :
                      r.actual_direction === "SELL" ? "down" : "flat"}`}>
                      {r.actual_direction === "BUY" ? "▲ up"
                        : r.actual_direction === "SELL" ? "▼ down" : "● flat"}
                      {r.actual_move_points != null
                        ? ` ${Math.round(r.actual_move_points)} pts` : ""}
                    </span>
                    {r.correct === true && <span className="hist-win"> ✓</span>}
                    {r.correct === false && <span className="hist-loss"> ✕</span>}
                    {r.correct === null && r.direction === "NO_TRADE" &&
                      <span className="dim"> no trade</span>}
                  </>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="dim hist-note">
        Bias engine accuracy is separate from the AI learning bar. Outcomes are scored only for
        directional (BUY/SELL) calls that had a confirmed plan.
      </div>
    </section>
  );
}

function SymbolsPanel({ rows, currency, error, onToggle }: {
  rows: SymbolRow[];
  currency: string;
  error: string;
  onToggle: (row: SymbolRow, enabled: boolean, mode: SymbolRow["mode"], close: boolean) => void;
}) {
  const [pending, setPending] = useState<SymbolRow | null>(null);
  const money = (value: number) => new Intl.NumberFormat(undefined, {
    style: "currency", currency,
  }).format(value);
  const change = (row: SymbolRow) => {
    if (row.mode === "off") {
      onToggle(row, true, "active", false);
    } else if (row.open_positions > 0) {
      setPending(row);
    } else {
      onToggle(row, false, "off", false);
    }
  };
  return (
    <section className="card symbols-card">
      <div className="symbols-heading">
        <h3>SYMBOLS</h3>
        {rows.some((row) => row.halted_by_kill_switch) &&
          <span className="symbol-halted-banner">GLOBAL KILL SWITCH · ALL SYMBOLS HALTED</span>}
      </div>
      {error && <div className="err">{error}</div>}
      <div className="symbols-list">
        {rows.map((row) => {
          const state = row.halted_by_kill_switch ? "halted" : row.mode;
          const statusText = row.halted_by_kill_switch ? "HALTED" :
            row.mode === "manage_only" ? "MANAGE ONLY" : row.mode.toUpperCase();
          return (
            <article className={`symbol-row symbol-${state}`} key={row.symbol}>
              <div className="symbol-identity">
                <strong>{row.symbol}</strong>
                {row.broker_symbol !== row.symbol && <span className="dim">{row.broker_symbol}</span>}
                <span className="strategy-name">{row.strategy}</span>
              </div>
              <span className={`symbol-status status-${state}`}>{statusText}</span>
              <span className="symbol-metric"><small>OPEN</small><strong>{row.open_positions}</strong></span>
              <span className={`symbol-metric ${row.today_pnl < 0 ? "negative" : "positive"}`}>
                <small>TODAY P/L</small><strong>{money(row.today_pnl)}</strong>
              </span>
              <button className={`symbol-switch ${row.mode !== "off" ? "is-on" : ""}`}
                data-halted={row.halted_by_kill_switch}
                role="switch" aria-checked={row.mode !== "off"} aria-label={`${row.symbol} trading`}
                onClick={() => change(row)}>
                <span />
              </button>
            </article>
          );
        })}
      </div>
      {pending && <div className="symbol-modal-backdrop" role="presentation">
        <section className="symbol-modal" role="dialog" aria-modal="true"
          aria-labelledby="symbol-modal-title">
          <h3 id="symbol-modal-title">STOP {pending.symbol} ENTRIES?</h3>
          <p>{pending.open_positions} open position(s) will be affected.</p>
          <div className="symbol-modal-actions">
            <button className="btn" onClick={() => setPending(null)}>CANCEL</button>
            <button className="btn manage-choice" onClick={() => {
              onToggle(pending, true, "manage_only", false);
              setPending(null);
            }}>KEEP MANAGING</button>
            <button className="btn danger" onClick={() => {
              onToggle(pending, false, "off", true);
              setPending(null);
            }}>CLOSE NOW</button>
          </div>
        </section>
      </div>}
    </section>
  );
}

function FocusCard({ setup, position, onPin }: {
  setup: Setup; position?: Position; onPin: (symbol: string, pinned: boolean) => void;
}) {
  return (
    <article className={`focus-card ${setup.state === "signal" ? "is-signal" : ""}`}
      data-symbol={setup.symbol}>
      <div className="focus-card-head">
        <div><strong>{setup.symbol}</strong><span className={`badge state-${setup.state}`}>{setup.state}</span></div>
        <button className="pin" onClick={() => onPin(setup.symbol, !setup.pinned)} aria-label={`${setup.pinned ? "Unpin" : "Pin"} ${setup.symbol}`}>
          {setup.pinned ? "UNPIN" : "PIN"}
        </button>
      </div>
      <div className="focus-card-body">
        <Gauge setup={setup} />
        <div className="focus-details">
          <div className="strategy-name">{setup.strategy}</div>
          <div className="score-line">{setup.score.toFixed(0)} <span>/ {setup.threshold.toFixed(0)}</span></div>
          <div className={setup.direction === "BUY" ? "direction buy" : setup.direction === "SELL" ? "direction sell" : "direction"}>
            {setup.direction ?? "NO DIRECTION"}
          </div>
          <p className="reason" title={setup.reason}>{setup.reason}</p>
          <HigherTimeframeVotes votes={setup.higher_timeframe_votes} />
          <EngulfingVotes votes={setup.engulfing_votes} />
          {position && <div className={`floating ${position.floating_profit >= 0 ? "positive" : "negative"}`}>
            {position.strategy} · OPEN · {position.side} · {position.volume} lots · {position.floating_profit >= 0 ? "+" : ""}
            {position.floating_profit.toFixed(2)}
          </div>}
        </div>
      </div>
    </article>
  );
}

function WatchRow({ setup, onPin }: { setup: Setup; onPin: (symbol: string, pinned: boolean) => void }) {
  return (
    <div className="watch-item">
      <div className="watch-row">
        <strong>{setup.symbol}</strong>
        <div className="score-track" aria-label={`Score ${Math.round(setup.score)} out of 100`}>
          <span style={{ width: `${Math.min(100, Math.max(0, setup.score))}%` }} />
        </div>
        <span className="watch-score">{setup.score.toFixed(0)}</span>
        <span className={`badge state-${setup.state}`}>{setup.state}</span>
        <button className="pin" onClick={() => onPin(setup.symbol, !setup.pinned)} aria-label={`${setup.pinned ? "Unpin" : "Pin"} ${setup.symbol}`}>
          {setup.pinned ? "UNPIN" : "PIN"}
        </button>
      </div>
      <HigherTimeframeVotes votes={setup.higher_timeframe_votes} />
      <EngulfingVotes votes={setup.engulfing_votes} />
    </div>
  );
}

function symbolMatches(position: Position, symbol: string): boolean {
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, "");
  const actual = normalize(position.symbol);
  const base = normalize(symbol);
  return actual === base || actual.startsWith(base) || actual.endsWith(base);
}

function normalizeSetups(value: unknown): Setup[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is Setup =>
      typeof item === "object" && item !== null &&
      typeof (item as Record<string, unknown>).symbol === "string" &&
      typeof (item as Record<string, unknown>).score === "number" &&
      typeof (item as Record<string, unknown>).threshold === "number" &&
      ["signal", "near", "watching", "closed"].includes(String((item as Record<string, unknown>).state)),
    ).map((item) => ({
      ...item,
      market_closed: (item as Setup).market_closed === true,
      engulfing_votes: Array.isArray((item as Setup).engulfing_votes)
        ? (item as Setup).engulfing_votes : [],
      higher_timeframe_votes: Array.isArray((item as Setup).higher_timeframe_votes)
        ? (item as Setup).higher_timeframe_votes : [],
    }));
  }
  if (typeof value !== "object" || value === null) return [];
  return Object.entries(value).flatMap(([symbol, raw]) => {
    if (typeof raw !== "object" || raw === null) return [];
    const item = raw as Record<string, unknown>;
    const rawState = String(item.state ?? "watching");
    const state: SetupState = ["signal", "near", "watching", "closed"].includes(rawState)
      ? rawState as SetupState : "watching";
    const score = typeof item.score === "number" && Number.isFinite(item.score) ? item.score : 0;
    const threshold = typeof item.threshold === "number" && Number.isFinite(item.threshold) ? item.threshold : 65;
    return [{
      symbol, strategy: "Trend pullback", score, threshold,
      direction: typeof item.direction === "string" ? item.direction : null,
      state, live: state !== "closed", reason: typeof item.reason === "string" ? item.reason : "",
      updated_at: typeof item.updated_at === "string" ? item.updated_at :
        typeof item.at === "string" ? item.at : new Date().toISOString(),
      has_open_position: false, pinned: false,
      priority: state === "signal" ? 1 : state === "near" ? 2 : state === "closed" ? 4 : 3,
      market_closed: item.market_closed === true,
      engulfing_votes: [],
    }];
  });
}

function Connect({ onToken }: { onToken: (t: string) => void }) {
  const [f, setF] = useState({
    access_key: "", login: "", server: "", password: "", account: "",
    scalping: true, day_trading_enabled: true,
  });
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    api<{ login?: number | string; server?: string }>("/api/v1/auth/bootstrap")
      .then((d) => {
        if (d.login !== undefined && d.login !== "") set("login", String(d.login));
        if (d.server) set("server", d.server);
      })
      .catch(() => undefined);
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const r = await api<{ access_token: string }>("/api/v1/auth/connect", { method: "POST", body: {
        access_key: f.access_key,
        credentials: {
          login: Number(f.login),
          server: f.server,
          password: f.password || undefined,
          metaapi_account_id: f.account || undefined,
        },
        config: { scalping: f.scalping, day_trading_enabled: f.day_trading_enabled } } });
      onToken(r.access_token);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <form className="form card" onSubmit={submit}>
      <h3>CONNECT BROKER SESSION</h3>
      <input type="password" placeholder="access key" value={f.access_key} onChange={(e) => set("access_key", e.target.value)} required />
      <input type="number" placeholder="MT5 login" value={f.login} onChange={(e) => set("login", e.target.value)} required />
      <input type="text" placeholder="MT5 server" value={f.server} onChange={(e) => set("server", e.target.value)} required />
      <input type="password" placeholder="MT5 password (optional for MetaApi)" value={f.password} onChange={(e) => set("password", e.target.value)} />
      <input type="text" placeholder="MetaApi account id (leave blank for local MT5)" value={f.account} onChange={(e) => set("account", e.target.value)} />
      <label className="dim"><input type="checkbox" checked={f.scalping} onChange={(e) => set("scalping", e.target.checked)} /> Scalping mode (30-minute management)</label>
      <label className="dim"><input type="checkbox" checked={f.day_trading_enabled}
        onChange={(e) => set("day_trading_enabled", e.target.checked)} /> Day-trading mode (12-hour management)</label>
      <button className="btn go" disabled={busy}>{busy ? "CONNECTING…" : "CONNECT"}</button>
      {err && <div className="err">{err}</div>}
    </form>
  );
}

export default function Dashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [accountError, setAccountError] = useState("");
  const [setups, setSetups] = useState<Setup[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [symbolRows, setSymbolRows] = useState<SymbolRow[]>([]);
  const [symbolError, setSymbolError] = useState("");
  const [pinned, setPinned] = useState<string[]>([]);
  const [engulfingEnabled, setEngulfingEnabled] = useState(false);
  const [engulfingPaperMode, setEngulfingPaperMode] = useState(true);
  const [pinError, setPinError] = useState("");
  const [positionsError, setPositionsError] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [newsEvents, setNewsEvents] = useState<NewsEvent[]>([]);
  const [tab, setTab] = useState<"overview" | "trade" | "symbols" | "news">("overview");
  const lastId = useRef(0);

  useEffect(() => { setToken(sessionStorage.getItem("soul_token")); }, []);
  const saveToken = (t: string | null) => {
    if (t) sessionStorage.setItem("soul_token", t); else sessionStorage.removeItem("soul_token");
    setToken(t); lastId.current = 0; setLines([]);
    if (!t) { setAccount(null); setAccountError(""); }
  };
  const pollHealth = async () => { try { setHealth(await api<Health>("/health")); } catch { setHealth(null); } };
  const pollAccount = async () => {
    if (!token) {
      setAccount(null);
      setAccountError("");
      return;
    }
    try {
      setAccount(await api<AccountSummary>("/api/v1/bot/account", { token }));
      setAccountError("");
    } catch (e) {
      setAccount(null);
      setAccountError("Broker account unavailable.");
      if (e instanceof ApiError && e.status === 401) saveToken(null);
    }
  };

  useEffect(() => {
    if (!token) return;
    api<{ pinned_symbols: string[]; engulfing_enabled: boolean; engulfing_paper_mode: boolean }>(
      "/api/v1/bot/config", { token })
      .then((config) => {
        setPinned(config.pinned_symbols ?? []);
        setEngulfingEnabled(config.engulfing_enabled ?? false);
        setEngulfingPaperMode(config.engulfing_paper_mode ?? true);
      })
      .catch((e) => { if (e instanceof ApiError && e.status === 401) saveToken(null); });
  }, [token]);

  const togglePin = async (symbol: string, shouldPin: boolean) => {
    if (!token) return;
    const previous = pinned;
    const next = shouldPin ? [...new Set([...pinned, symbol])] : pinned.filter((item) => item !== symbol);
    setPinned(next);
    setPinError("");
    try {
      const config = await api<{ pinned_symbols: string[] }>("/api/v1/bot/config", {
        method: "PATCH", token, body: { pinned_symbols: next },
      });
      setPinned(config.pinned_symbols ?? next);
    } catch (e) {
      setPinned(previous);
      setPinError((e as Error).message);
    }
  };

  const updateEngulfing = async (change: { engulfing_enabled?: boolean; engulfing_paper_mode?: boolean }) => {
    if (!token) return;
    try {
      const config = await api<{ engulfing_enabled: boolean; engulfing_paper_mode: boolean }>(
        "/api/v1/bot/config", { method: "PATCH", token, body: change });
      setEngulfingEnabled(config.engulfing_enabled);
      setEngulfingPaperMode(config.engulfing_paper_mode);
    } catch (e) {
      setPinError(`Engulfing settings were not saved: ${(e as Error).message}`);
    }
  };

  const updateSymbol = async (
    row: SymbolRow, enabled: boolean, mode: SymbolRow["mode"], close: boolean,
  ) => {
    if (!token) return;
    const previous = symbolRows;
    setSymbolError("");
    setSymbolRows((current) => current.map((item) => item.symbol === row.symbol
      ? { ...item, enabled, mode } : item));
    try {
      const updated = await api<SymbolRow>(`/api/v1/symbols/${encodeURIComponent(row.symbol)}/toggle`, {
        method: "POST", token, body: { enabled, mode, close_open_positions: close },
      });
      setSymbolRows((current) => current.map((item) => item.symbol === row.symbol ? updated : item));
    } catch (e) {
      setSymbolRows(previous);
      setSymbolError(`Could not update ${row.symbol}: ${(e as Error).message}`);
    }
  };

  const newsAction = async (eventKey: string, symbol: string, action: "confirm" | "skip") => {
    if (!token) return;
    try {
      await api(`/api/v1/news-events/${encodeURIComponent(eventKey)}/${action}?symbol=${encodeURIComponent(symbol)}`, {
        method: "POST", token,
      });
      // Optimistically reflect the action until the next poll refreshes.
      setNewsEvents((cur) => cur.map((ev) => ev.event_key === eventKey
        ? { ...ev, symbols: ev.symbols.map((sp) => sp.symbol === symbol
            ? { ...sp, confirmed: action === "confirm", skipped: action === "skip" } : sp) }
        : ev));
    } catch (e) {
      setSymbolError(`News ${action} failed: ${(e as Error).message}`);
    }
  };

  usePoll(pollHealth, 5000);
  usePoll(pollAccount, 5000);
  usePoll(async () => {
    if (!token) return;
    try {
      const [st, su, pos, ex, symbolResult, newsResult] = await Promise.allSettled([
        api<Status>("/api/v1/bot/status", { token }),
        api<unknown>("/api/v1/bot/setups", { token }),
        api<Position[]>("/api/v1/bot/positions", { token }),
        api<Line[]>(`/api/v1/bot/explain?after=${lastId.current}`, { token }),
        api<SymbolRow[]>("/api/v1/symbols", { token }),
        api<NewsEvent[]>("/api/v1/news-events/upcoming", { token }),
      ]);
      if (st.status === "rejected") throw st.reason;
      if (su.status === "rejected") throw su.reason;
      if (ex.status === "rejected") throw ex.reason;
      setStatus(st.value); setSetups(normalizeSetups(su.value));
      if (pos.status === "fulfilled") {
        setPositions(pos.value); setPositionsError("");
      } else if (pos.reason instanceof ApiError && pos.reason.status === 401) {
        saveToken(null);
      } else {
        setPositionsError("Position data is temporarily unavailable.");
      }
      if (ex.value.length) { lastId.current = ex.value[ex.value.length - 1].id; setLines((p) => [...p, ...ex.value].slice(-300)); }
      if (symbolResult.status === "fulfilled") {
        setSymbolRows(symbolResult.value);
        setSymbolError("");
      } else {
        setSymbolError("Symbol status is temporarily unavailable.");
      }
      if (newsResult.status === "fulfilled") {
        setNewsEvents(newsResult.value);
      } else if (newsResult.reason instanceof ApiError && newsResult.reason.status === 401) {
        saveToken(null);
      }
      // 503 (engine disabled) or other errors: leave the last known events in place.
    } catch (e) { if (e instanceof ApiError && e.status === 401) saveToken(null); }
  }, 3000);

  const focusRef = useRef<HTMLDivElement>(null);
  const priorRects = useRef(new Map<string, DOMRect>());
  const focus = (() => {
    const live = setups.filter((item) => item.live && item.state !== "closed");
    const required = new Set([
      ...live.slice(0, 3).map((item) => item.symbol),
      ...setups.filter((item) => item.pinned || item.has_open_position || pinned.includes(item.symbol)).map((item) => item.symbol),
    ]);
    return setups.filter((item) => required.has(item.symbol));
  })();
  const focusKey = focus.map((item) => `${item.symbol}:${item.state}`).join("|");
  useLayoutEffect(() => {
    const container = focusRef.current;
    if (!container) return;
    const nodes = Array.from(container.querySelectorAll<HTMLElement>(".focus-card[data-symbol]"));
    const currentRects = new Map<string, DOMRect>();
    for (const node of nodes) {
      const symbol = node.dataset.symbol;
      if (!symbol) continue;
      const rect = node.getBoundingClientRect();
      const old = priorRects.current.get(symbol);
      currentRects.set(symbol, rect);
      if (old) {
        const dx = old.left - rect.left;
        const dy = old.top - rect.top;
        if (dx || dy) node.animate(
          [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0, 0)" }],
          { duration: 280, easing: "cubic-bezier(.2,.8,.2,1)" },
        );
      }
    }
    priorRects.current = currentRects;
  }, [focusKey]);
  const watching = setups.filter((item) => item.live && item.state !== "closed" &&
    !focus.some((selected) => selected.symbol === item.symbol));
  const closed = setups.filter((item) => item.market_closed === true &&
    !focus.some((selected) => selected.symbol === item.symbol));
  const watchingCount = setups.filter((item) => item.live && item.state === "watching").length;
  const hasLiveSetup = setups.some((item) => item.live && (item.state === "signal" || item.state === "near"));
  const positionFor = (setup: Setup) => positions.find((position) => symbolMatches(position, setup.symbol));

  return (
    <>
      <TopBar health={health} refresh={pollHealth} connected={Boolean(token)}
        session={status?.current_session ?? null} onDisconnect={() => saveToken(null)} />
      {!token ? <Connect onToken={saveToken} /> : (
        <main className="grid">
          <AccountCards account={account} error={accountError} />
          <TabBar tab={tab} setTab={setTab}
            badges={{ trade: focus.length, news: newsEvents.length }} />

          {tab === "overview" && (
            <>
              <section className="dashboard-left">
                <LearningBar status={status?.ai_learning} />
                <div className="card"><h3>NEXT HIGH-IMPACT EVENT</h3>
                  <Countdown iso={status?.next_event_time ?? null} label={status?.next_event_type ?? null} />
                </div>
              </section>
              <div className="overview-row">
                <section className="card explainer-section"><h3>SOUL EXPLAINER</h3><Terminal lines={lines} /></section>
                <StrategyTutor setups={setups} positions={positions} />
              </div>
            </>
          )}

          {tab === "trade" && (
            <section className="dashboard-left">
              <div className="card focus-section">
                <h3>FOCUS</h3>
                {focus.length ? <div className="focus-list" ref={focusRef}>
                  {focus.map((item) => <FocusCard key={item.symbol} setup={{
                    ...item, pinned: item.pinned || pinned.includes(item.symbol),
                  }} position={positionFor(item)} onPin={togglePin} />)}
                </div> : <div className="empty">No live setups. Watching {watchingCount} symbols.</div>}
                {!hasLiveSetup && focus.length > 0 && <div className="empty">No live setups. Watching {watchingCount} symbols.</div>}
                {pinError && <div className="err">{pinError}</div>}
                {positionsError && <div className="dim">{positionsError}</div>}
              </div>
              {watching.length > 0 && <div className="card watch-section">
                <h3>WATCHING ({watching.length})</h3>
                {watching.map((item) => <WatchRow key={item.symbol} setup={{
                  ...item, pinned: item.pinned || pinned.includes(item.symbol),
                }} onPin={togglePin} />)}
              </div>}
              <details className="card closed-section">
                <summary>MARKET CLOSED ({closed.length})</summary>
                {closed.map((item) => <WatchRow key={item.symbol} setup={{
                  ...item, pinned: item.pinned || pinned.includes(item.symbol),
                }} onPin={togglePin} />)}
              </details>
              <div className="card">
                <h3>ENGULFING STRATEGY</h3>
                <label className="dim">
                  <input type="checkbox" checked={engulfingEnabled}
                    onChange={(e) => void updateEngulfing({ engulfing_enabled: e.target.checked })} />
                  Enable Bullish/Bearish Engulfing
                </label>
                <label className="dim">
                  <input type="checkbox" checked={engulfingPaperMode}
                    onChange={(e) => void updateEngulfing({ engulfing_paper_mode: e.target.checked })} />
                  Paper mode (signals only)
                </label>
                {!engulfingPaperMode && <div className="err">Live engulfing orders are enabled.</div>}
                <div className="dim">Paper mode is on by default. Live entries use the bot’s existing broker order path.</div>
              </div>
            </section>
          )}

          {tab === "symbols" && (
            <section className="dashboard-left">
              <SymbolsPanel rows={symbolRows} currency={account?.currency ?? "USD"}
                error={symbolError} onToggle={updateSymbol} />
              <div className="card">
                <h3>GOLD AND SILVER TRADING</h3>
                <div className="dim">
                  Gold and silver are traded independently. Silver confirmation is not required for gold entries.
                </div>
              </div>
            </section>
          )}

          {tab === "news" && (
            <section className="dashboard-left">
              <NewsHistoryCard token={token} />
              <NewsEventsPanel events={newsEvents} token={token}
                halted={Boolean(health && !health.auto_trading_enabled)} onAction={newsAction} />
            </section>
          )}
        </main>
      )}
    </>
  );
}
