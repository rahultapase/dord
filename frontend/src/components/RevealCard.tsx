import { useState } from 'react'
import { motion } from 'motion/react'
import type { AnswerResult, Choice, GemmaResult, GhostProof, RealProof } from '../api'
import { prettyPron } from '../api'
import { cap } from '../rounds'

interface Props {
  result: AnswerResult
  isLast: boolean
  onNext: () => void
}

/** When the stamp lands (seconds after the card starts to flip). The engine's thud uses the same. */
export const SLAM_AT = 0.42

function label(c: Choice | null | undefined): string {
  if (c === null || c === undefined) return ''
  return typeof c === 'number' ? `No. ${c}` : cap(c)
}

function GemmaLine({ g, mode }: { g: GemmaResult | null; mode: 'real-or-ghost' | 'three-defs' }) {
  if (!g) return null
  if (g.answer === null) {
    return <p>Gemma was asked the same question but {g.source === 'timeout' ? 'did not answer in time' : 'gave no answer'}.</p>
  }
  const said = mode === 'real-or-ghost' ? <b>{label(g.answer)}</b> : <b>definition {g.answer}</b>
  const how = g.source === 'seance' ? ' (from the séance)' : g.seconds ? ` in ${g.seconds} s` : ''
  return (
    <p>
      Gemma, asked the same question{how}, {g.correct ? 'also chose' : 'swore by'} {said}
      {g.correct ? '.' : ', and was wrong.'}
    </p>
  )
}

/** Ink soaking into the page: each part of the old entry sharpens in turn. */
const ink = (i: number) => ({
  initial: { opacity: 0, filter: 'blur(4px)' },
  animate: { opacity: 1, filter: 'blur(0px)' },
  transition: { duration: 1.1, delay: 0.55 + i * 0.28, ease: 'easeOut' as const },
})

function RealEntry({ proof }: { proof: RealProof }) {
  const e = proof.entry
  return (
    <div className="entry">
      <motion.div {...ink(0)}>
        <i>{prettyPron(e.pron)}</i>, {e.pos}
        {e.etym && <span className="etym"> [{e.etym}]</span>}
      </motion.div>
      <ol>
        {e.senses.map((s, i) => (
          <motion.li key={i} value={s.number && /^\d+$/.test(s.number) ? Number(s.number) : i + 1} {...ink(i + 1)}>
            {s.text}
            {(s.quote || s.author) && (
              <span className="quote">
                {s.quote && <>“{s.quote}” </>}
                {s.author && <span className="author">{s.author}</span>}
              </span>
            )}
          </motion.li>
        ))}
      </ol>
    </div>
  )
}

function GhostDetail({ proof }: { proof: GhostProof }) {
  return (
    <>
      <p>
        {proof.ghost.summoned ? 'Summoned live' : 'Invented'} by <b>Gemma 4</b> ({proof.ghost.model}) on this laptop
        {proof.ghost.etym && <>, with a made-up origin: <i>{proof.ghost.etym}</i></>}.
      </p>
      <p>
        Searched <b>{proof.headwords.toLocaleString('en-US')}</b> headwords of the 1913 Webster's and a modern word
        list: <b>no trace</b>. Checked that it is:
      </p>
      <ul className="checks">
        {proof.checks.map((c) => (
          <li key={c.code}>{c.label}</li>
        ))}
      </ul>
    </>
  )
}

/** The ghost's headword comes apart: every letter drifts up, blurs and fades, at its own pace. */
export function Dissolve({ word, start = 0.9 }: { word: string; start?: number }) {
  const [drift] = useState(() =>
    [...word].map(() => ({
      y: -(4 + Math.random() * 14),
      x: (Math.random() - 0.5) * 10,
      o: 0.14 + Math.random() * 0.14,
      d: Math.random() * 0.35,
    })),
  )
  return (
    <div className="head dissolve" aria-label={word} role="img">
      {[...word].map((ch, i) => (
        <motion.span
          key={i}
          aria-hidden
          initial={{ opacity: 1, x: 0, y: 0, filter: 'blur(0px)' }}
          animate={{ opacity: drift[i].o, x: drift[i].x, y: drift[i].y, filter: 'blur(2.6px)' }}
          transition={{ delay: start + i * 0.07 + drift[i].d, duration: 2.4, ease: 'easeInOut' }}
        >
          {ch}
        </motion.span>
      ))}
    </div>
  )
}

/** A real word's headword: ink spreads on the paper and the letters come into focus. */
function InkBleed({ word }: { word: string }) {
  return (
    <div className="ink-wrap">
      <motion.div
        className="ink-blot"
        aria-hidden
        initial={{ scale: 0.15, opacity: 0 }}
        animate={{ scale: 1, opacity: [0, 0.55, 0.18] }}
        transition={{ duration: 1.8, ease: 'easeOut' }}
      />
      <motion.div
        className="head"
        initial={{ opacity: 0, filter: 'blur(9px)', letterSpacing: '0.14em' }}
        animate={{ opacity: 1, filter: 'blur(0px)', letterSpacing: '0.02em' }}
        transition={{ duration: 1.3, delay: 0.15, ease: 'easeOut' }}
      >
        {word}
      </motion.div>
    </div>
  )
}

export function Stamp({ ghost, text, delay = SLAM_AT }: { ghost: boolean; text: string; delay?: number }) {
  const rotate = ghost ? -13 : 9
  return (
    <motion.div
      className={`stamp${ghost ? '' : ' real-s'}`}
      initial={{ scale: 2.8, opacity: 0, rotate }}
      animate={{ scale: 1, opacity: 1, rotate }}
      transition={{ delay: delay - 0.12, type: 'spring', stiffness: 700, damping: 22, mass: 0.7 }}
    >
      {text}
      {ghost && (
        <span className="drips" aria-hidden>
          <i style={{ left: '18%', animationDelay: `${delay + 0.3}s` }} />
          <i style={{ left: '57%', animationDelay: `${delay + 1.1}s`, width: 3 }} />
          <i style={{ left: '81%', animationDelay: `${delay + 0.6}s` }} />
        </span>
      )}
    </motion.div>
  )
}

export function RevealCard({ result, isLast, onNext }: Props) {
  const ghost = result.proof.kind === 'ghost'
  const mode = result.options ? 'three-defs' : 'real-or-ghost'
  const g = result.gemma
  return (
    <motion.div
      className="reveal-wrap"
      initial={{ rotateY: -82, opacity: 0 }}
      animate={{ rotateY: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.3, 0.6, 0.3, 1] }}
      style={{ transformPerspective: 1300 }}
    >
      {ghost && <div className="wraith" aria-hidden />}
      <div className={`card reveal${ghost ? ' hit' : ''}`} role="region" aria-label="The reveal">
        <Stamp ghost={ghost} text={ghost ? 'Ghost' : 'Real · 1913'} />
        <div className="round">
          <span>Round {result.n}</span>
          <span>
            you said: {label(result.choice)} {result.correct ? '✓' : '✗'}
          </span>
        </div>
        <div className="rule" />
        <div className={`verdict${ghost ? '' : ' real-v'}`}>{ghost ? 'Never in any dictionary' : "In Webster's, 1913"}</div>
        {ghost ? <Dissolve word={cap(result.word)} /> : <InkBleed word={cap(result.word)} />}
        {result.proof.kind === 'real' && <RealEntry proof={result.proof} />}
        <motion.div
          className="proof"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: ghost ? 0.9 : 1.2 }}
        >
          {result.proof.kind === 'ghost' ? <GhostDetail proof={result.proof} /> : <p>{result.proof.text}</p>}
          <GemmaLine g={g} mode={mode} />
        </motion.div>
        <div className="tally">
          <span className={`pill${result.correct ? '' : ' x'}`}>You {result.correct ? '✓' : '✗'}</span>
          {g && g.answer !== null && <span className={`pill${g.correct ? '' : ' x'}`}>Gemma {g.correct ? '✓' : '✗'}</span>}
          <button className="pill" onClick={onNext} autoFocus>
            {isLast ? 'The last word ↵' : 'Next ↵'}
          </button>
        </div>
      </div>
    </motion.div>
  )
}
