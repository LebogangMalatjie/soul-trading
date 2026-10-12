const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, msg: string) { super(msg); }
}

type Opts = { method?: string; token?: string | null; key?: string; body?: unknown };

export type SymbolRow = {
  symbol: string;
  broker_symbol: string;
  strategy: string;
  enabled: boolean;
  mode: "active" | "manage_only" | "off";
  open_positions: number;
  today_pnl: number;
  halted_by_kill_switch: boolean;
};

export async function api<T>(path: string, o: Opts = {}): Promise<T> {
  const h: Record<string, string> = {};
  if (o.body) h["Content-Type"] = "application/json";
  if (o.token) h.Authorization = `Bearer ${o.token}`;
  if (o.key) h["X-Soul-Shutdown-Key"] = o.key;
  const r = await fetch(`${BASE}${path}`, {
    method: o.method ?? "GET", headers: h, cache: "no-store",
    body: o.body ? JSON.stringify(o.body) : undefined,
  });
  if (!r.ok) {
    let d = r.statusText;
    try { const j = await r.json(); if (typeof j.detail === "string") d = j.detail; } catch {}
    throw new ApiError(r.status, d);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}
