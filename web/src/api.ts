// 後端介面的薄封裝。權杖存在本機瀏覽器；陣營由後端依權杖判定，前端不宣告。
const BASE = '/api'

export type Session = { token: string; tableId: string }

export function loadSession(): Session | null {
  try { const s = localStorage.getItem('acies.session'); return s ? JSON.parse(s) : null } catch { return null }
}
export function saveSession(s: Session | null) {
  try { s ? localStorage.setItem('acies.session', JSON.stringify(s)) : localStorage.removeItem('acies.session') } catch { /* 無法存也照跑 */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, msg: string) { super(msg); this.status = status }
}

async function req<T>(s: Session | null, method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', ...(s ? { Authorization: `Bearer ${s.token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) {
    let msg = r.statusText
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j) } catch { /* 沒有 JSON */ }
    throw new ApiError(r.status, msg)
  }
  return r.json()
}

export type Me = { table_id: string; role: 'allies' | 'axis' | 'referee' | 'observer'; side: 'allies' | 'axis' | null }
export type Summary = {
  table_id: string; name: string; status: string; tick: number; global_hour: number; max_ticks: number; poll_seconds: number
  round: { status: string; deadline: string | null; confirmed: boolean | Record<string, number | null> } | null
  verdict?: { winner: string | null; why: string }
}
export type Unit = {
  side: 'allies' | 'axis'; short: string; name: string; type: string; pos: [number, number]
  visibility_state: string; hidden?: boolean
  strength?: number; strength_approx?: number; org?: number; personnel?: number; fatigue?: number
  supply_status?: string; fortification?: number; fortification_bucket?: string; camouflaged?: boolean
  equip?: { tanks: number; guns: number }; ammo?: Record<string, number>; status?: string; orders?: string
}
export type State = {
  tick: number; global_hour: number; game_time?: string; map: { width: number; height: number; terrain: string[][] }
  units: Record<string, Unit>
  command: Record<string, { main_cp: [number, number] | null; fwd_cp: [number, number] | null; commander_at: string | null; pending_cp?: { kind: string; pos: [number, number]; effective_gh: number }[] }>
  works?: Record<string, { man_hours: number; by: string }>
  fog_of_war: Record<string, string[] | string>
  pending_orders?: { id: string; level: string; text: string; effective_global_hour: number; status: string }[]
  standing_orders?: Record<string, string>
  hour_log_side?: Record<string, string[]>
  score?: Record<string, { points: number }>
}
export type Ruling = { seq: number; ruling_id: string; gh: number; condition: string; effect: string; basis?: string; beneficiary?: string }
export type Pending = { pending_id: string; gh: number; phase: string; kind: string; side: string | null; clause_id: string | null; body: Record<string, unknown>; status: string; answer: Record<string, unknown> | null }
export type Question = { question_id: string; tick: number; text?: string; answer: Record<string, string> }

export const api = {
  createTable: (name: string) => req<{ table_id: string; tokens: Record<string, string> }>(null, 'POST', '/tables', { name }),
  me: (s: Session) => req<Me>(s, 'GET', '/me'),
  summary: (s: Session) => req<Summary>(s, 'GET', `/tables/${s.tableId}`),
  state: (s: Session) => req<State>(s, 'GET', `/tables/${s.tableId}/state`),
  brief: (s: Session, tick?: number) => req<{ tick: number; text: string; shared_hash: string }>(s, 'GET', `/tables/${s.tableId}/brief${tick === undefined ? '' : `?tick=${tick}`}`),
  getOrder: (s: Session, tick: number) => req<{ version: number; text: string }>(s, 'GET', `/tables/${s.tableId}/rounds/${tick}/order`),
  putOrder: (s: Session, tick: number, text: string, key: string) => req<{ version: number; round_status: string }>(s, 'PUT', `/tables/${s.tableId}/rounds/${tick}/order`, { text, idempotency_key: key }),
  confirm: (s: Session, tick: number) => req<{ round_status: string }>(s, 'POST', `/tables/${s.tableId}/rounds/${tick}/confirm`),
  rulings: (s: Session) => req<Ruling[]>(s, 'GET', `/tables/${s.tableId}/rulings`),
  questions: (s: Session) => req<Question[]>(s, 'GET', `/tables/${s.tableId}/questions`),
  ask: (s: Session, text: string) => req<{ question_id: string }>(s, 'POST', `/tables/${s.tableId}/questions`, { text }),
  adjudications: (s: Session) => req<Pending[]>(s, 'GET', `/tables/${s.tableId}/adjudications`),
  answer: (s: Session, id: string, body: { kind: string; public_text: string; private_text: string; beneficiary: string }) =>
    req<{ ok: boolean }>(s, 'POST', `/tables/${s.tableId}/adjudications/${id}/answer`, body),
}
