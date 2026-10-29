import type { AnswerResult, CardData, Choice } from '../api'
import { cap } from '../rounds'

interface Props {
  card: CardData
  result: AnswerResult | null
  chosen: Choice | null
  busy: boolean
  onChoose: (c: Choice) => void
}

/** The question card for Three Definitions: one real 1913 word, its true sense and two bluffs. */
export function ThreeDefs({ card, result, chosen, busy, onChoose }: Props) {
  const locked = chosen !== null || busy
  const options = card.options ?? []
  return (
    <div className="card">
      <div className="round">
        <span>Three Definitions</span>
        <span>Webster's, 1913</span>
      </div>
      <div className="rule" />
      <div className="head">{cap(card.word)}</div>
      <div className="pron">{card.pos} &nbsp;One of these is true. Two were written by Gemma.</div>
      <div className="options">
        {options.map((text, i) => {
          const n = (i + 1) as 1 | 2 | 3
          let cls = 'option'
          const who: string[] = []
          if (result) {
            cls += n === result.truth ? ' true' : ' false'
            if (n === result.choice) who.push('you')
            if (result.gemma?.answer === n) who.push('Gemma')
          } else if (chosen === n) {
            cls += ' true'
          }
          return (
            <button key={n} className={cls} disabled={locked} onClick={() => onChoose(n)}>
              <span className="num">{n}</span>
              <span>
                {text}
                {result && (n === result.truth || who.length > 0) && (
                  <span className="who">
                    {n === result.truth ? 'the true 1913 sense' : 'a bluff by Gemma'}
                    {who.length > 0 && ` · chosen by ${who.join(' and ')}`}
                  </span>
                )}
              </span>
            </button>
          )
        })}
      </div>
      <div className="keys">{busy ? 'the spirits deliberate…' : 'press 1, 2 or 3'}</div>
    </div>
  )
}
