import type { CardData, Choice } from '../api'
import { cap } from '../rounds'

interface Props {
  card: CardData
  chosen: Choice | null
  busy: boolean
  onChoose: (c: Choice) => void
}

/** The question card for Real or Ghost? */
export function Card({ card, chosen, busy, onChoose }: Props) {
  const locked = chosen !== null || busy
  return (
    <div className="card">
      <div className="round">
        <span>Real or Ghost?</span>
        <span>Webster's, 1913</span>
      </div>
      <div className="rule" />
      <div className="head">{cap(card.word)}</div>
      <div className="pron">{card.pos}</div>
      <div className="def">{card.definition}</div>
      <div className="btns">
        <button
          className={`btn real${chosen === 'real' ? ' chosen' : ''}`}
          disabled={locked}
          onClick={() => onChoose('real')}
        >
          Real
        </button>
        <button
          className={`btn ghost${chosen === 'ghost' ? ' chosen' : ''}`}
          disabled={locked}
          onClick={() => onChoose('ghost')}
        >
          Ghost
        </button>
      </div>
      <div className="keys">{busy ? 'the spirits deliberate…' : 'press R or G'}</div>
    </div>
  )
}
