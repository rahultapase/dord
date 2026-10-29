import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api, prettyPron } from '../api'
import type { SummonResult } from '../api'
import { audio } from '../audio/engine'
import { cap } from '../rounds'
import { Stamp } from './RevealCard'

type State =
  | { kind: 'idle' }
  | { kind: 'working'; since: number }
  | { kind: 'done'; r: SummonResult; id: number }
  | { kind: 'error'; message: string }

/** Codes for which Gemma's "fake" was in fact a real word. */
const REAL_CODES = new Set(['1913', 'modern', 'inflection', 'hand'])

function stampText(r: SummonResult): string {
  if (r.accepted) return 'Ghost'
  if (r.code === '1913' || r.code === 'inflection') return 'Real · 1913'
  if (r.code === 'modern') return 'Real · modern'
  if (r.code === 'hand') return 'Real'
  if (r.code === 'near-1913') return 'Too close'
  if (r.code === 'duplicate') return 'Already here'
  return 'Rejected'
}

/** Gemma invents a new fake word live; code checks it; if it passes it haunts the next game. */
export function SummonButton({ available }: { available: boolean }) {
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [elapsed, setElapsed] = useState(0)
  const working = useRef(false)

  useEffect(() => {
    if (state.kind !== 'working') return
    const t = window.setInterval(() => setElapsed((Date.now() - state.since) / 1000), 100)
    return () => window.clearInterval(t)
  }, [state])

  const summon = async () => {
    if (working.current) return
    working.current = true
    setElapsed(0)
    setState({ kind: 'working', since: Date.now() })
    audio.whisper(0, 2.2)
    try {
      const r = await api.summon()
      setState({ kind: 'done', r, id: Date.now() })
      if (r.accepted) audio.ghostReveal()
      else if (REAL_CODES.has(r.code ?? '')) audio.realReveal()
      else audio.stamp(0.3)
    } catch (e) {
      setState({ kind: 'error', message: e instanceof Error ? e.message : String(e) })
    } finally {
      working.current = false
    }
  }

  const busy = state.kind === 'working'
  return (
    <div className="summon">
      <button className="enter summon-btn" onClick={summon} disabled={!available || busy}>
        {busy ? 'Summoning…' : state.kind === 'done' ? 'Summon another' : 'Summon a fresh ghost'}
      </button>
      <p className="small">
        {!available
          ? 'Gemma is not answering, so nothing can be summoned. The ghosts already in the deck still play.'
          : busy
            ? `Gemma 4 is inventing a word on this laptop… ${elapsed.toFixed(1)} s`
            : 'Gemma 4 invents a new fake word right now. Code checks it against the 1913 Webster’s and a modern word list before it may haunt you.'}
      </p>

      <AnimatePresence mode="wait">
        {state.kind === 'done' && (
          <motion.div
            key={state.id}
            className="summon-result"
            initial={{ opacity: 0, y: 50, filter: 'blur(10px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -20, filter: 'blur(6px)' }}
            transition={{ duration: 0.7, ease: [0.2, 0.7, 0.2, 1] }}
          >
            <SummonCard r={state.r} />
          </motion.div>
        )}
        {state.kind === 'error' && (
          <motion.p key="err" className="summon-error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            The summoning failed: {state.message}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}

function SummonCard({ r }: { r: SummonResult }) {
  const ghost = r.accepted
  const wasReal = REAL_CODES.has(r.code ?? '')
  const sense = r.entry?.senses?.[0]
  return (
    <div className={`card reveal summon-card${ghost ? ' hit' : ''}`}>
      <Stamp ghost={ghost || !wasReal} text={stampText(r)} delay={0.5} />
      <div className="round">
        <span>Summoned just now</span>
        <span>
          {r.model} · {r.seconds} s
        </span>
      </div>
      <div className="rule" />
      <div className={`verdict${ghost ? '' : ' real-v'}`}>
        {ghost ? 'Never in any dictionary' : wasReal ? 'Gemma’s fake was a real word' : 'Turned away at the door'}
      </div>
      {/* Not dissolved: unlike a game card, the player has not read this word yet. */}
      <div className={`head${ghost ? ' ghostly' : ''}`}>{cap(r.word)}</div>
      <div className="pron">
        {r.pos}
        {r.etym && <> &nbsp;[{r.etym}]</>}
      </div>
      <div className="def small-def">Gemma: “{r.definition}”</div>
      <div className="proof">
        {ghost ? (
          <>
            <p>{r.reason}</p>
            <ul className="checks">
              {r.checks.map((c) => (
                <li key={c.code}>{c.label}</li>
              ))}
            </ul>
            <p>It will haunt your next game of Real or Ghost.</p>
          </>
        ) : (
          <>
            <p>{/^[a-z]/.test(r.reason) ? `Rejected: ${r.reason}.` : r.reason}</p>
            {r.entry && (
              <div className="entry">
                <div>
                  <b>{r.entry.headline ?? cap(r.match ?? r.word)}</b>
                  {r.entry.pron && (
                    <>
                      {' '}
                      <i>{prettyPron(r.entry.pron)}</i>
                    </>
                  )}
                  {r.entry.pos && <>, {r.entry.pos}</>}
                </div>
                {sense && <div>{sense.text}</div>}
              </div>
            )}
            <p>Code caught it, so it never reaches the deck.</p>
          </>
        )}
      </div>
    </div>
  )
}
