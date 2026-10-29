import type { AnswerResult } from './api'

export function cap(w: string): string {
  return w.charAt(0).toUpperCase() + w.slice(1)
}

/** One played round, kept for the finale's "who the ghosts fooled" line. */
export interface Round {
  kind: 'real' | 'ghost'
  you: boolean
  gemma: boolean | null
  youSaidReal: boolean
  gemmaSaidReal: boolean | null
}

export function toRound(r: AnswerResult): Round {
  const three = !!r.options
  return {
    kind: r.kind,
    you: r.correct,
    gemma: r.gemma?.answer == null ? null : !!r.gemma.correct,
    youSaidReal: !three && r.choice === 'real',
    gemmaSaidReal: three || r.gemma?.answer == null ? null : r.gemma.answer === 'real',
  }
}
