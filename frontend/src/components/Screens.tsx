import type { Health, Mode, Scores } from '../api'
import type { Round } from '../rounds'

export function Title({ onEnter, health }: { onEnter: () => void; health: Health | null }) {
  return (
    <section className="title-screen">
      <h1>
        Gh<em>o</em>st Words
      </h1>
      <p className="lede">
        In 1934 Webster's printed a word that never existed: <i>dord</i>. It haunted the dictionary for thirteen
        years. Editors call such words <b>ghost words</b>, and language models make them all the time.
      </p>
      <p className="lede">
        Here are forgotten words from the 1913 Webster's, and ghosts that Gemma invented on this laptop. Tell them
        apart. Code, not the model, decides what is real.
      </p>
      <button className="enter" onClick={onEnter}>
        Enter, if you dare
      </button>
      <p className="small">
        {health === null
          ? 'Listening for the back end…'
          : health.ok
            ? `${health.headwords.toLocaleString('en-US')} headwords · ${health.reals} forgotten words · ${health.ghosts} ghosts · Gemma is awake`
            : 'Gemma is not answering (is Ollama running?). You can still play; Gemma will sit this one out.'}
      </p>
    </section>
  )
}

export function ModePicker({
  onPick,
  vsGemma,
  setVsGemma,
  busy,
}: {
  onPick: (m: Mode) => void
  vsGemma: boolean
  setVsGemma: (v: boolean) => void
  busy: boolean
}) {
  return (
    <section className="title-screen">
      <div className="modes">
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
      </div>
      <button className="toggle" onClick={() => setVsGemma(!vsGemma)} aria-pressed={vsGemma}>
        <span className="box">{vsGemma ? '✓' : ''}</span>
        Gemma plays the same cards against you
      </button>
    </section>
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
      <div className="card">
        <div className="round">
          <span>The last word</span>
          <span>Webster's, 1934</span>
        </div>
        <div className="rule" />
        <div className="head">Dord</div>
        <div className="pron">n. Physics &amp; Chem. Density.</div>
        <div className="story">
          <p>
            In 1934 the second edition of Webster's New International Dictionary printed <i>dord</i>, meaning density.
            Nobody had ever used it. A slip meant for the abbreviations, <i>D or d</i>, for density, was read as a
            single word and set in type.
          </p>
          <p>
            In 1939 an editor noticed that <i>dord</i> had no etymology: no history at all. It was taken out in 1947.
            Every ghost in this game has the same flaw. Gemma can give a word a meaning; only the past can give it a
            history.
          </p>
          <p className="small">
            The story is told by Merriam-Webster:{' '}
            <a href="https://www.merriam-webster.com/wordplay/dord-a-ghost-word" target="_blank" rel="noreferrer">
              “Dord”: a ghost word
            </a>
            .
          </p>
        </div>
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
      </div>
    </section>
  )
}
