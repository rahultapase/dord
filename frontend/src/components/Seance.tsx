import { useEffect, useState } from 'react'
import { api, type Seance as SeanceData, type SeanceModel } from '../api'
import { RiseFromFog } from './Atmosphere'

type Row = { label: string; value: (s: SeanceModel) => [number, number] | string }

const ROWS: Row[] = [
  { label: 'Real or Ghost: right', value: (s) => [s.realOrGhost.correct, s.realOrGhost.cards] },
  { label: 'Ghosts it believed were real', value: (s) => [s.realOrGhost.ghostsCalledReal, s.realOrGhost.ghosts] },
  { label: 'Real words it called ghosts', value: (s) => [s.realOrGhost.realsCalledGhost, s.realOrGhost.reals] },
  { label: 'Three Definitions: right', value: (s) => [s.threeDefs.correct, s.threeDefs.cards] },
  { label: 'Ghosts it defined with confidence', value: (s) => [s.define.madeUp, s.define.ghosts] },
  { label: 'Seconds per answer (median)', value: (s) => (s.secondsPerAnswer === null ? '-' : `${s.secondsPerAnswer}`) },
]

function Cell({ v }: { v: [number, number] | string }) {
  if (typeof v === 'string') return <td>{v}</td>
  const [a, b] = v
  return (
    <td>
      <b>{b ? Math.round((100 * a) / b) : 0}%</b>
      <span className="of">
        {a} of {b}
      </span>
    </td>
  )
}

/** The benchmark: both models, the same fixed cards, the game's own prompts. */
export function Seance({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<SeanceData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.seance().then(setData, (e: Error) => setError(e.message))
  }, [])

  const models = data ? Object.keys(data.summary) : []
  // Quote the model that made up the most meanings for ghosts.
  const liar = data ? [...models].sort((a, b) => data.summary[b].define.madeUp - data.summary[a].define.madeUp)[0] : ''
  const madeUp = data
    ? data.answers
        .filter((a) => a.mode === 'define' && a.model === liar && a.answer === 'made-up' && a.definition)
        .sort((a, b) => (a.definition ?? '').length - (b.definition ?? '').length)
        .slice(0, 3)
    : []

  return (
    <section className="finale seance">
      <RiseFromFog slow>
        <div className="card">
          <div className="round">
            <span>The séance</span>
            <span>{data ? new Date(data.held).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : ''}</span>
          </div>
          <div className="rule" />
          <div className="head">The Séance</div>
          <div className="pron">Do the machines believe in their own ghosts?</div>

          {error && <p className="summon-error">{error}</p>}
          {data && (
            <>
              <p className="lead">
                Both models played the same fixed cards with the game's own questions: 100 Real or Ghost cards (half
                ghosts), 50 Three Definitions words, and 30 ghosts to define. Temperature 0, thinking off, on this
                laptop.
              </p>
              <table className="seance-table">
                <thead>
                  <tr>
                    <th />
                    {models.map((m) => (
                      <th key={m}>{m}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ROWS.map((r) => (
                    <tr key={r.label}>
                      <th scope="row">{r.label}</th>
                      {models.map((m) => (
                        <Cell key={m} v={r.value(data.summary[m])} />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {madeUp.length > 0 && (
                <div className="proof">
                  <p>
                    Asked to define ghosts that Gemma 4 had invented, <b>{liar}</b> answered as if they were real:
                  </p>
                  {madeUp.map((a) => (
                    <p key={a.word} className="quoted">
                      <b>{a.word}</b>: “{a.definition}”
                    </p>
                  ))}
                </div>
              )}
              {!data.complete && <p className="small">The séance is still running; these numbers are partial.</p>}
            </>
          )}
          <div className="again">
            <button className="btn ghost" onClick={onBack}>
              Back
            </button>
          </div>
        </div>
      </RiseFromFog>
    </section>
  )
}
