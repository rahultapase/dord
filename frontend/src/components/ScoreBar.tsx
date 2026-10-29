import type { Scores } from '../api'

export function ScoreBar({ scores, vsGemma }: { scores: Scores; vsGemma: boolean }) {
  return (
    <div className="score" aria-live="polite">
      You <b>{scores.you}</b>
      {vsGemma && (
        <>
          {' '}· Gemma <b>{scores.gemma}</b>
        </>
      )}{' '}
      · Round {Math.min(scores.round, scores.rounds)} / {scores.rounds}
    </div>
  )
}
