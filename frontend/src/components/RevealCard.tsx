import type { AnswerResult, Choice, GemmaResult, GhostProof, RealProof } from '../api'
import { prettyPron } from '../api'
import { cap } from '../rounds'

interface Props {
  result: AnswerResult
  isLast: boolean
  onNext: () => void
}

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

function RealEntry({ proof }: { proof: RealProof }) {
  const e = proof.entry
  return (
    <div className="entry">
      <div>
        <i>{prettyPron(e.pron)}</i>, {e.pos}
        {e.etym && <span className="etym"> [{e.etym}]</span>}
      </div>
      <ol>
        {e.senses.map((s, i) => (
          <li key={i} value={s.number && /^\d+$/.test(s.number) ? Number(s.number) : i + 1}>
            {s.text}
            {(s.quote || s.author) && (
              <span className="quote">
                {s.quote && <>“{s.quote}” </>}
                {s.author && <span className="author">{s.author}</span>}
              </span>
            )}
          </li>
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

export function RevealCard({ result, isLast, onNext }: Props) {
  const ghost = result.proof.kind === 'ghost'
  const mode = result.options ? 'three-defs' : 'real-or-ghost'
  const g = result.gemma
  return (
    <div className="card reveal" role="region" aria-label="The reveal">
      <div className={`stamp${ghost ? '' : ' real-s'}`}>{ghost ? 'Ghost' : 'Real · 1913'}</div>
      <div className="round">
        <span>Round {result.n}</span>
        <span>
          you said: {label(result.choice)} {result.correct ? '✓' : '✗'}
        </span>
      </div>
      <div className="rule" />
      <div className={`verdict${ghost ? '' : ' real-v'}`}>{ghost ? 'Never in any dictionary' : "In Webster's, 1913"}</div>
      <div className={`head${ghost ? ' faded' : ''}`}>{cap(result.word)}</div>
      {result.proof.kind === 'real' && <RealEntry proof={result.proof} />}
      <div className="proof">
        {result.proof.kind === 'ghost' ? <GhostDetail proof={result.proof} /> : <p>{result.proof.text}</p>}
        <GemmaLine g={g} mode={mode} />
      </div>
      <div className="tally">
        <span className={`pill${result.correct ? '' : ' x'}`}>You {result.correct ? '✓' : '✗'}</span>
        {g && g.answer !== null && <span className={`pill${g.correct ? '' : ' x'}`}>Gemma {g.correct ? '✓' : '✗'}</span>}
        <button className="pill" onClick={onNext} autoFocus>
          {isLast ? 'The last word ↵' : 'Next ↵'}
        </button>
      </div>
    </div>
  )
}
