import type { State, Unit } from './api'

// 引擎是 30×18 方格、八方向切比雪夫距離；這裡照方格畫。
const TERRAIN: Record<string, { fill: string; label: string }> = {
  '.': { fill: '#3a5a32', label: '' }, F: { fill: '#14572a', label: '♣♣' }, H: { fill: '#6b5a2a', label: '︿' },
  U: { fill: '#777', label: '█' }, R: { fill: '#1d4f70', label: '≈' }, B: { fill: '#8a6a2a', label: '╪' },
  S: { fill: '#3f5a5a', label: '~' }, K: { fill: '#3d5c2a', label: '⌗' },
}
const TYPE: Record<string, string> = { infantry: '步', armor: '裝', artillery: '砲', recon: '偵', ranger: '特', mech_inf: '裝步' }
const SUPPLY: Record<string, string> = { intact: '#4caf50', threatened: '#ffb300', cut: '#e53935' }

export function Map({ state, cell = 30, selected, onSelect }: { state: State; cell?: number; selected?: string | null; onSelect?: (uid: string | null) => void }) {
  const { width, height, terrain } = state.map
  const byHex: Record<string, string[]> = {}
  for (const [uid, u] of Object.entries(state.units)) (byHex[u.pos.join(',')] ??= []).push(uid)
  const cps: { side: string; kind: string; pos: [number, number]; here: boolean; pending?: boolean }[] = []
  for (const [side, c] of Object.entries(state.command ?? {})) {
    if (c.main_cp) cps.push({ side, kind: '主', pos: c.main_cp, here: c.commander_at === 'main' })
    if (c.fwd_cp) cps.push({ side, kind: '前', pos: c.fwd_cp, here: c.commander_at === 'fwd' })
    for (const p of c.pending_cp ?? []) cps.push({ side, kind: p.kind === 'main' ? '主' : '前', pos: p.pos, here: false, pending: true })
  }
  const W = width * cell, H = height * cell
  return (
    <svg viewBox={`-${cell} -${cell} ${W + cell * 2} ${H + cell * 2}`} style={{ width: '100%', maxWidth: W + 2 * cell, background: '#111', borderRadius: 6 }}
      onClick={() => onSelect?.(null)}>
      {terrain.map((row, y) => row.map((t, x) => {
        const tt = TERRAIN[t] ?? TERRAIN['.']
        return <g key={`${x},${y}`}>
          <rect x={x * cell} y={y * cell} width={cell} height={cell} fill={tt.fill} stroke="#0008" strokeWidth={x % 5 === 0 || y % 5 === 0 ? 1.2 : 0.4} />
          {tt.label && <text x={x * cell + cell / 2} y={y * cell + cell * 0.36} fontSize={cell * 0.32} textAnchor="middle" fill="#9fe0a0" opacity={0.9}>{tt.label}</text>}
        </g>
      }))}
      {Array.from({ length: width }, (_, x) => <text key={'x' + x} x={x * cell + cell / 2} y={-cell * 0.3} fontSize={cell * 0.35} fill="#aaa" textAnchor="middle">{x}</text>)}
      {Array.from({ length: height }, (_, y) => <text key={'y' + y} x={-cell * 0.3} y={y * cell + cell * 0.65} fontSize={cell * 0.35} fill="#aaa" textAnchor="end">{y}</text>)}
      {Object.entries(state.works ?? {}).map(([k, w]) => {
        const [x, y] = k.split(',').map(Number)
        return <rect key={'w' + k} x={x * cell + 2} y={y * cell + 2} width={cell - 4} height={cell - 4} fill="none" stroke={w.by === 'allies' ? '#7cf' : '#f88'} strokeDasharray="3 2" opacity={Math.min(1, 0.3 + w.man_hours / 40000)} />
      })}
      {cps.map((c, i) => <g key={'cp' + i}>
        <rect x={c.pos[0] * cell + cell * 0.55} y={c.pos[1] * cell + 1} width={cell * 0.42} height={cell * 0.42} fill={c.side === 'allies' ? '#2d6cdf' : '#c62828'} opacity={c.pending ? 0.4 : 0.9} rx={2} />
        <text x={c.pos[0] * cell + cell * 0.76} y={c.pos[1] * cell + cell * 0.34} fontSize={cell * 0.3} fill="#fff" textAnchor="middle">{c.here ? '★' : c.kind}</text>
      </g>)}
      {Object.entries(byHex).map(([k, uids]) => {
        const [x, y] = k.split(',').map(Number)
        return uids.map((uid, i) => {
          const u = state.units[uid]
          const own = u.strength !== undefined
          const sel = selected === uid
          const col = u.side === 'allies' ? '#2d6cdf' : '#c62828'
          const dy = i * (cell * 0.36)
          return <g key={uid} onClick={e => { e.stopPropagation(); onSelect?.(uid) }} style={{ cursor: 'pointer' }}>
            <rect x={x * cell + 1} y={y * cell + cell * 0.4 + dy} width={cell - 2} height={cell * 0.34} fill={col} stroke={sel ? '#fff' : own ? '#000' : '#ffd54f'} strokeWidth={sel ? 2 : 0.8} rx={2} opacity={own ? 1 : 0.85} />
            <text x={x * cell + cell / 2} y={y * cell + cell * 0.67 + dy} fontSize={cell * 0.3} fill="#fff" textAnchor="middle" fontWeight={700}>{TYPE[u.type] ?? u.type[0]}{uid.split('-').slice(1).join('')}</text>
            {own && u.supply_status && <circle cx={x * cell + cell * 0.12} cy={y * cell + cell * 0.57 + dy} r={cell * 0.08} fill={SUPPLY[u.supply_status] ?? '#999'} />}
          </g>
        })
      })}
    </svg>
  )
}

export function UnitCard({ uid, u }: { uid: string; u: Unit }) {
  const own = u.strength !== undefined
  return <div className="card">
    <b>{uid}</b> {u.name}（{u.short}）<br />
    位置 ({u.pos[0]}, {u.pos[1]})　能見 {u.visibility_state}
    {own ? <>
      <br />戰力 {u.strength}　組織 {u.org}　人員 {u.personnel}　疲勞 {u.fatigue}
      <br />戰車 {u.equip?.tanks}　火砲 {u.equip?.guns}　彈藥 {Object.entries(u.ammo ?? {}).map(([g, v]) => `${g}:${Math.round(v)}`).join('／')}
      <br />工事 {u.fortification?.toFixed(2)}　偽裝 {u.camouflaged ? '✓' : '—'}　補給 {u.supply_status}　狀態 {u.status}
      {u.orders && <><br />命令：{u.orders}</>}
    </> : <><br />概估戰力 ~{u.strength_approx}%　工事 {u.fortification_bucket}</>}
  </div>
}
