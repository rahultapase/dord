import { motion } from 'motion/react'
import type { Health, Mode, Scores } from '../api'
import type { Round } from '../rounds'
import { RiseFromFog } from './Atmosphere'
import { Stamp } from './RevealCard'
import { SummonButton } from './SummonButton'

export function Title({ onEnter, health }: { onEnter: () => void; health: Health | null }) {
  return (
    <section className="title-screen">
      <RiseFromFog slow>
        <h1 className="glitch">
          Gh<em>o</em>st Words
        </h1>
      </RiseFromFog>
      <RiseFromFog delay={0.9}>
        <p className="lede">
          In 1934 Webster's printed a word that never existed: <i>dord</i>. It haunted the dictionary for thirteen
          years. Editors call such words <b>ghost words</b>, and language models make them all the time.
        </p>
      </RiseFromFog>
      <RiseFromFog delay={1.3}>
        <p className="lede">
          Here are forgotten words from the 1913 Webster's, and ghosts that Gemma invented on this laptop. Tell them
          apart. Code, not the model, decides what is real.
        </p>
      </RiseFromFog>
      <RiseFromFog delay={1.9}>
        <button className="enter" onClick={onEnter}>
          Enter, if you dare
        </button>
      </RiseFromFog>
      <p className="small">
        {health === null
          ? 'Listening for the back end…'
          : health.ok
            ? `${health.headwords.toLocaleString('en-US')} headwords · ${health.reals} forgotten words · ${health.ghosts} ghosts · Gemma is awake`
            : 'Gemma is not answering (is Ollama running?). You can still play; Gemma will sit this one out.'}
      </p>
      <p className="small hint">This room has sound. M or the speaker, top right, turns it on and off.</p>
    </section>
  )
}

export function ModePicker({
  onPick,
  vsGemma,
  setVsGemma,
  busy,
  gemmaAwake,
  onSeance,
}: {
  onPick: (m: Mode) => void
  vsGemma: boolean
  setVsGemma: (v: boolean) => void
  busy: boolean
  gemmaAwake: boolean
  onSeance: () => void
}) {
  return (
    <section className="title-screen">
      <div className="modes">
        <RiseFromFog>
          <button className="card mode-card" onClick={() => onPick('real-or-ghost')} disabled={busy}>
            <div className="round">
              <span>The first game</span>
              <span>R · G</span>
            </div>
            <div className="rule" />
            <div className="head">Real or Ghost?</div>
            <div className="pron">twenty words, one at a time</div>
            <div className="def">
              A word and its meaning. Is it a forgotten word from 1913, or a ghost Gemma made up?
            </div>
          </button>
        </RiseFromFog>
        <RiseFromFog delay={0.25}>
          <button className="card mode-card reveal" onClick={() => onPick('three-defs')} disabled={busy}>
            <div className="round">
              <span>The parlour game</span>
              <span>1 · 2 · 3</span>
            </div>
            <div className="rule" />
            <div className="head">Three Definitions</div>
            <div className="pron">twenty real words</div>
            <div className="def">
              Every word is real. One meaning is from 1913; Gemma wrote the other two. Find the true one.
            </div>
          </button>
        </RiseFromFog>
      </div>
      <button className="toggle" onClick={() => setVsGemma(!vsGemma)} aria-pressed={vsGemma}>
        <span className="box">{vsGemma ? '✓' : ''}</span>
        Gemma plays the same cards against you
      </button>
      <SummonButton available={gemmaAwake} />
      <button className="seance-link" onClick={onSeance}>
        The séance: do the machines believe in their own ghosts?
      </button>
    </section>
  )
}

/** When the letters of "Dord" part to show the slip it came from, and when the stamp lands. */
export const DORD_SPLIT_AT = 2.6
export const DORD_STAMP_AT = 4.1

function DordWord() {
  const part = { initial: { marginLeft: '0em' }, animate: { marginLeft: '0.34em' } }
  const t = { delay: DORD_SPLIT_AT, duration: 1.3, ease: 'easeInOut' as const }
  return (
    <div className="head dord" role="img" aria-label="Dord: the slip read D or d">
      <span>D</span>
      <motion.span {...part} transition={t}>
        o
      </motion.span>
      <span>r</span>
      <motion.span {...part} transition={t}>
        d
      </motion.span>
    </div>
  )
}

export function Finale({
  scores,
  rounds,
  mode,
  vsGemma,
  onAgain,
  onModes,
}: {
  scores: Scores
  rounds: Round[]
  mode: Mode
  vsGemma: boolean
  onAgain: () => void
  onModes: () => void
}) {
  const ghosts = rounds.filter((r) => r.kind === 'ghost')
  const youFooled = ghosts.filter((r) => r.youSaidReal).length
  const gemmaFooled = ghosts.filter((r) => r.gemmaSaidReal).length
  return (
    <section className="finale">
      <RiseFromFog slow>
        <div className="card">
          <Stamp ghost text="Ghost · 1934" delay={DORD_STAMP_AT} />
          <div className="round">
            <span>The last word</span>
            <span>Webster's, 1934</span>
          </div>
          <div className="rule" />
          <DordWord />
          <motion.div
            className="slip"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: DORD_SPLIT_AT + 0.9, duration: 1 }}
          >
            the slip said: <b>D or d</b>, density
          </motion.div>
          <div className="pron">n. Physics &amp; Chem. Density.</div>
          <motion.div
            className="story"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.6, duration: 1.4 }}
          >
            <p>
              In 1934 the second edition of Webster's New International Dictionary printed <i>dord</i>, meaning
              density. There was no record of anyone ever using it. A chemistry editor's slip for the abbreviations,{' '}
              <i>D or d</i>, for density, was read as a single word and set in type.
            </p>
            <p>
              The entry had no etymology and no example of use. An editor caught the error in 1939; the word was not
              taken out until 1947. Every ghost in this game has the same flaw. Gemma can give a word a meaning; only
              the past can give it a history.
            </p>
            <p className="small">
              The story is told by Merriam-Webster:{' '}
              <a href="https://www.merriam-webster.com/wordplay/dord-a-ghost-word" target="_blank" rel="noreferrer">
                “Dord”: a ghost word
              </a>
              .
            </p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: DORD_STAMP_AT + 0.6, duration: 0.9 }}
          >
            <div className="final-score">
              <div>
                You<b>{scores.you}</b>
              </div>
              {vsGemma && (
                <div>
                  Gemma<b>{scores.gemma}</b>
                </div>
              )}
              <div>
                of<b>{scores.rounds}</b>
              </div>
            </div>
            {mode === 'real-or-ghost' && ghosts.length > 0 && (
              <p className="proof">
                Of {ghosts.length} ghosts, {youFooled} fooled you
                {vsGemma && scores.gemmaAnswered > 0 && <> and {gemmaFooled} fooled Gemma</>}.
              </p>
            )}
            <div className="again">
              <button className="btn real" onClick={onAgain}>
                Play again
              </button>
              <button className="btn ghost" onClick={onModes}>
                Other game
              </button>
            </div>
          </motion.div>
        </div>
      </RiseFromFog>
    </section>
  )
}
