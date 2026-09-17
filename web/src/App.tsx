import { useCallback, useEffect, useState } from 'react'
import { api, loadSession, saveSession, type Me, type Session, type State, type Summary } from './api'
import { Battlefield, BriefPage, Orders, QuestionsPage, RefereePage, RulingsPage } from './pages'

type Page = '戰場' | '命令' | '簡報' | '裁示' | '問答' | '裁判席' | '觀戰'

function sessionFromUrl(): Session | null {
  // 網址帶 ?table=…&token=… 直接入席（給裁判席／觀戰席連結用），入席後把參數從網址拿掉
  const q = new URLSearchParams(window.location.search)
  const table = q.get('table'), token = q.get('token')
  if (table && token) {
    const sess = { tableId: table, token }
    saveSession(sess)
    window.history.replaceState(null, '', window.location.pathname)
    return sess
  }
  return loadSession()
}

export default function App() {
  const [s, setS] = useState<Session | null>(sessionFromUrl())
  const [me, setMe] = useState<Me | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [state, setState] = useState<State | null>(null)
  const [page, setPage] = useState<Page>('戰場')
  const [err, setErr] = useState('')

  const refresh = useCallback(async () => {
    if (!s) return
    try {
      const [m, sum] = await Promise.all([api.me(s), api.summary(s)])
      setMe(m); setSummary(sum); setErr('')
      if (m.side || m.role === 'referee') setState(await api.state(s))
      else setState(null)
    } catch (e) { setErr((e as Error).message); if ((e as { status?: number }).status === 401) { saveSession(null); setS(null) } }
  }, [s])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    if (!s) return
    const id = setInterval(refresh, Math.max(5, summary?.poll_seconds ?? 30) * 1000)
    return () => clearInterval(id)
  }, [s, summary?.poll_seconds, refresh])

  if (!s) return <Login onLogin={sess => { saveSession(sess); setS(sess) }} />
  const side = me?.side ?? null
  const isRef = me?.role === 'referee'
  const pages: Page[] = side ? ['戰場', '命令', '簡報', '裁示', '問答'] : isRef ? ['裁判席', '裁示'] : ['觀戰', '裁示']
  const roleZh = side === 'allies' ? '藍軍指揮部' : side === 'axis' ? '紅軍指揮部' : isRef ? '裁判席' : '觀戰席'
  return <div className="app">
    <header>
      <b>料鋒 Acies</b>　{summary?.name}　<span className={side === 'allies' ? 'blue' : side === 'axis' ? 'red' : ''}>{roleZh}</span>
      {summary && <span className="dim">　Tick {summary.tick}/{summary.max_ticks}　gh{summary.global_hour}　{summary.status}　窗口：{summary.round?.status ?? '—'}</span>}
      {summary?.verdict && <span>　終局：{summary.verdict.winner ?? '平手'}——{summary.verdict.why}</span>}
      <nav>{pages.map(p => <button key={p} className={page === p ? 'on' : ''} onClick={() => setPage(p)}>{p}</button>)}
        <button onClick={refresh}>重新整理</button><button onClick={() => { saveSession(null); setS(null) }}>離席</button></nav>
      {err && <div className="err">{err}</div>}
    </header>
    <main>
      {!summary ? <p>載入中…</p> :
        page === '戰場' ? <Battlefield s={s} state={state} /> :
        page === '命令' ? <Orders s={s} summary={summary} /> :
        page === '簡報' ? <BriefPage s={s} summary={summary} /> :
        page === '裁示' ? <RulingsPage s={s} /> :
        page === '問答' ? <QuestionsPage s={s} side={side} /> :
        page === '裁判席' ? <RefereePage s={s} state={state} /> :
        <Observe s={s} summary={summary} state={state} />}
    </main>
  </div>
}

function Observe({ summary, state }: { s: Session; summary: Summary; state: State | null }) {
  return <div>
    <h3>觀戰</h3>
    <p>終局前觀戰席只看雙方公開段；終局後可見全局。</p>
    {state ? <Battlefield s={null as unknown as Session} state={state} /> : <p>計分請見標題列；狀態：{summary.status}</p>}
  </div>
}

function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [token, setToken] = useState('')
  const [tableId, setTableId] = useState('')
  const [name, setName] = useState('')
  const [created, setCreated] = useState<{ table_id: string; tokens: Record<string, string> } | null>(null)
  const [err, setErr] = useState('')
  return <div className="login">
    <h1>料鋒 Acies</h1>
    <p>貼上桌號與席位權杖入席。陣營由權杖決定，不由你選。</p>
    <input placeholder="桌號" value={tableId} onChange={e => setTableId(e.target.value)} />
    <input placeholder="席位權杖" value={token} onChange={e => setToken(e.target.value)} />
    <button onClick={() => { if (token && tableId) onLogin({ token, tableId }) }}>入席</button>
    <hr />
    <p>或建一桌新的（純戰場）：</p>
    <div className="row"><input placeholder="桌名" value={name} onChange={e => setName(e.target.value)} />
      <button onClick={async () => { try { setCreated(await api.createTable(name)) } catch (e) { setErr((e as Error).message) } }}>建桌</button></div>
    {err && <div className="err">{err}</div>}
    {created && <div className="card"><b>桌號</b> {created.table_id}<br />
      {Object.entries(created.tokens).map(([r, t]) => <div key={r}><b>{r}</b>：<code>{t}</code> <button onClick={() => onLogin({ token: t, tableId: created.table_id })}>以此入席</button></div>)}
      <p className="dim">權杖只顯示這一次；把各方的權杖分別交給對應的人。</p></div>}
  </div>
}
