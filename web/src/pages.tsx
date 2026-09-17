import { useEffect, useMemo, useState } from 'react'
import { marked } from 'marked'
import { api, type Pending, type Ruling, type Session, type State, type Summary } from './api'
import { Map, UnitCard } from './Map'

function Md({ text }: { text: string }) {
  const html = useMemo(() => marked.parse(text, { async: false }) as string, [text])
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
}

export function Battlefield({ s, state }: { s: Session; state: State | null }) {
  const [sel, setSel] = useState<string | null>(null)
  if (!state) return <p>載入中…</p>
  const mine = Object.entries(state.units).filter(([, u]) => u.strength !== undefined)
  const enemy = Object.entries(state.units).filter(([, u]) => u.strength === undefined)
  void s
  return <div className="two">
    <div>
      <Map state={state} selected={sel} onSelect={setSel} />
      <p className="dim">格線每 5 格加粗；■ 指揮所（★＝軍長所在）；虛線框＝己方工事；圓點＝補給（綠暢通／黃受威脅／紅切斷）。</p>
      {sel && state.units[sel] && <UnitCard uid={sel} u={state.units[sel]} />}
    </div>
    <div>
      <h3>我方部隊</h3>
      <table><thead><tr><th>編隊</th><th>位置</th><th>戰力</th><th>組織</th><th>疲勞</th><th>工事</th><th>補給</th></tr></thead>
        <tbody>{mine.map(([uid, u]) => <tr key={uid} onClick={() => setSel(uid)} className={sel === uid ? 'sel' : ''}>
          <td>{uid}</td><td>({u.pos[0]},{u.pos[1]})</td><td>{u.strength}</td><td>{u.org}</td><td>{u.fatigue}</td><td>{u.fortification?.toFixed(2)}</td><td>{u.supply_status}</td></tr>)}</tbody></table>
      <h3>敵情（僅列已偵獲）</h3>
      {enemy.length === 0 ? <p className="dim">尚未偵獲任何敵編隊。</p> :
        <table><thead><tr><th>編隊</th><th>位置</th><th>概估</th><th>能見</th><th>工事</th></tr></thead>
          <tbody>{enemy.map(([uid, u]) => <tr key={uid} onClick={() => setSel(uid)}><td>{uid}</td><td>({u.pos[0]},{u.pos[1]})</td><td>~{u.strength_approx}%</td><td>{u.visibility_state}</td><td>{u.fortification_bucket}</td></tr>)}</tbody></table>}
      {state.pending_orders && state.pending_orders.length > 0 && <>
        <h3>延遲中的命令</h3>
        <ul>{state.pending_orders.filter(o => o.status === 'pending').map(o => <li key={o.id}>[{o.level}] gh{o.effective_global_hour} 生效：{o.text}</li>)}</ul></>}
      {state.score && <p>計分：藍 {state.score.allies?.points} : 紅 {state.score.axis?.points}</p>}
      {state.hour_log_side && <><h3>上一段紀錄</h3><pre className="log">{Object.values(state.hour_log_side)[0]?.slice(-14).join('\n')}</pre></>}
    </div>
  </div>
}

const TEMPLATE = `## 意圖
（一到三句：這個 tick 你想達成什麼、為什麼）

## 命令
1. [L1] XXX-?：具體動作＋目標座標＋姿態

## 應變
- 若（具體條件）則（具體動作）

## 給裁判的問題
`

export function Orders({ s, summary }: { s: Session; summary: Summary }) {
  const tick = summary.tick
  const [text, setText] = useState('')
  const [version, setVersion] = useState(0)
  const [msg, setMsg] = useState('')
  useEffect(() => { api.getOrder(s, tick).then(o => { setVersion(o.version); setText(o.text || TEMPLATE) }).catch(() => setText(TEMPLATE)) }, [s, tick])
  const open = summary.round && (summary.round.status === '窗口開啟' || summary.round.status === '裁示後重開')
  const confirmed = summary.round?.confirmed === true
  async function submit() {
    try {
      const r = await api.putOrder(s, tick, text, crypto.randomUUID())
      setVersion(r.version); setMsg(`已送出（第 ${r.version} 版）；窗口狀態：${r.round_status}`)
    } catch (e) { setMsg(String((e as Error).message)) }
  }
  async function confirm() {
    try { const r = await api.confirm(s, tick); setMsg(`已確認不改；窗口狀態：${r.round_status}`) } catch (e) { setMsg(String((e as Error).message)) }
  }
  return <div>
    <p>Tick {tick} 命令　目前版本 {version}　窗口：{summary.round?.status}{confirmed ? '（你已確認）' : ''}
      {summary.round?.deadline && <span className="dim">　期限 {new Date(summary.round.deadline).toLocaleString()}</span>}</p>
    <textarea value={text} onChange={e => setText(e.target.value)} rows={22} disabled={!open} />
    <div className="row">
      <button onClick={submit} disabled={!open}>送出命令</button>
      <button onClick={confirm} disabled={!open || version === 0}>確認不改</button>
      <span className="dim">{msg}</span>
    </div>
    <p className="dim">上一回的命令仍在執行（常設）。不重下＝零延遲；重下要重新吃一次延遲。裁示重開窗口後，「確認不改」與「修改」同等效力，沒有回應不算。</p>
  </div>
}

export function BriefPage({ s, summary }: { s: Session; summary: Summary }) {
  const [tick, setTick] = useState(summary.tick)
  const [text, setText] = useState('')
  useEffect(() => { api.brief(s, tick).then(b => setText(b.text)).catch(e => setText(`（${(e as Error).message}）`)) }, [s, tick])
  return <div>
    <div className="row">簡報 Tick <select value={tick} onChange={e => setTick(Number(e.target.value))}>
      {Array.from({ length: summary.tick + 1 }, (_, i) => <option key={i} value={i}>{i}</option>)}</select></div>
    <Md text={text} />
  </div>
}

export function RulingsPage({ s }: { s: Session }) {
  const [rows, setRows] = useState<Ruling[]>([])
  useEffect(() => { api.rulings(s).then(setRows) }, [s])
  return <div>
    <h3>裁示全集（雙方逐位元組相同）</h3>
    {rows.length === 0 && <p className="dim">本局尚無裁示。</p>}
    {rows.map(r => <div className="card" key={r.ruling_id}><b>裁示 {r.seq}</b>（gh{r.gh}）<br />條件：{r.condition}<br />效果：{r.effect}<br /><span className="dim">依據：{r.basis}　對誰有利：{r.beneficiary}</span></div>)}
  </div>
}

export function QuestionsPage({ s }: { s: Session; side: string | null }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<{ question_id: string; tick: number; text?: string; answer: Record<string, string> }[]>([])
  const load = () => api.questions(s).then(setRows)
  useEffect(() => { load() }, [s])
  return <div>
    <h3>給裁判的問題</h3>
    <p className="dim">只能問你視角內合法的問題，不可問戰術建議。通則性的答案會公告雙方；只涉及你自己命令解讀的答案只回你。</p>
    <div className="row"><input value={q} onChange={e => setQ(e.target.value)} placeholder="問題" style={{ flex: 1 }} />
      <button onClick={async () => { if (q.trim()) { await api.ask(s, q); setQ(''); load() } }}>送出</button></div>
    {rows.map(r => <div className="card" key={r.question_id}><b>{r.question_id}</b>（T{r.tick}）{r.text && <><br />{r.text}</>}
      {r.answer && Object.keys(r.answer).length > 0 && <><br /><i>答：</i>{r.answer.public_text || r.answer.private_text}</>}</div>)}
  </div>
}

export function RefereePage({ s, state }: { s: Session; state: State | null }) {
  const [items, setItems] = useState<Pending[]>([])
  const [form, setForm] = useState({ kind: 'public_ruling', public_text: '', private_text: '', beneficiary: 'neutral' })
  const [sel, setSel] = useState<string | null>(null)
  const load = () => api.adjudications(s).then(setItems)
  useEffect(() => { load() }, [s])
  const open = items.filter(i => i.status === 'open' && (i.body as { material?: boolean }).material)
  const notices = items.filter(i => i.status === 'open' && !(i.body as { material?: boolean }).material)
  return <div className="two">
    <div>
      <h3>待人工裁定（{open.length}）</h3>
      {open.length === 0 && <p className="dim">沒有需要你裁定的事；桌會自己往前走。</p>}
      {open.map(p => <div className="card" key={p.pending_id}><b>{p.pending_id}</b>　gh{p.gh}　{p.phase}／{p.kind}{p.side && `　${p.side}`}{p.clause_id && `　${p.clause_id}`}
        <pre className="log">{JSON.stringify(p.body, null, 1)}</pre>
        <div className="row"><select value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value })}>
          <option value="public_ruling">公開裁示（條件 → 效果）</option><option value="referee_instruction">給裁判的指示（不公開）</option>
          <option value="clause_rewrite">條款改寫</option><option value="reject">駁回</option></select>
          <select value={form.beneficiary} onChange={e => setForm({ ...form, beneficiary: e.target.value })}>
            {['neutral', 'favours_attacker', 'favours_defender', 'favours_mover', 'favours_stationary', 'favours_fortified'].map(b => <option key={b}>{b}</option>)}</select></div>
        <input placeholder="公開文字（條件 → 效果；不得指名陣營）" value={form.public_text} onChange={e => setForm({ ...form, public_text: e.target.value })} />
        <input placeholder="不公開文字" value={form.private_text} onChange={e => setForm({ ...form, private_text: e.target.value })} />
        <button onClick={async () => { await api.answer(s, p.pending_id, form); setForm({ ...form, public_text: '', private_text: '' }); load() }}>送出裁定</button>
      </div>)}
      <h3>裁判的通知（非重大，已用最小解讀暫定，會進該方簡報）（{notices.length}）</h3>
      {notices.map(p => <div className="card dim" key={p.pending_id}><b>{p.pending_id}</b>　{p.side}　{p.clause_id}<br />{String((p.body as { question?: string }).question ?? '')}</div>)}
      <h3>已回覆</h3>
      {items.filter(i => i.status !== 'open').map(p => <div className="card dim" key={p.pending_id}>{p.pending_id}　{p.kind} → {String(p.answer?.kind)}：{String(p.answer?.public_text || p.answer?.private_text || '')}</div>)}
    </div>
    <div>
      <h3>上帝視角</h3>
      {state ? <><Map state={state} selected={sel} onSelect={setSel} cell={24} />{sel && state.units[sel] && <UnitCard uid={sel} u={state.units[sel]} />}</> : <p>載入中…</p>}
    </div>
  </div>
}
