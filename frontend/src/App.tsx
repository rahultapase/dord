import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import type { AnswerResult, CardData, Choice, Health, Mode, Scores } from './api'
import { Card } from './components/Card'
import { RevealCard } from './components/RevealCard'
import { ScoreBar } from './components/ScoreBar'
import { Finale, ModePicker, Title } from './components/Screens'
import { ThreeDefs } from './components/ThreeDefs'
import { toRound } from './rounds'
import type { Round } from './rounds'

type Screen = 'title' | 'modes' | 'play' | 'finale'
const ROUNDS = 20

interface Play {
  id: string
  mode: Mode
  vsGemma: boolean
  card: CardData
  scores: Scores
  chosen: Choice | null
  result: AnswerResult | null
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('title')
  const [health, setHealth] = useState<Health | null>(null)
  const [vsGemma, setVsGemma] = useState(true)
  const [play, setPlay] = useState<Play | null>(null)
  const [history, setHistory] = useState<Round[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busyRef = useRef(false)

  useEffect(() => {
    api.health().then(setHealth).catch((e: ApiError) => {
      setHealth({ ok: false, ollama: false, models: {}, headwords: 0, reals: 0, ghosts: 0, threeDefsWords: 0 })
      setError(e.message)
    })
  }, [])

  const run = useCallback(async (fn: () => Promise<void>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }, [])

  const start = useCallback(
    (mode: Mode) =>
      run(async () => {
        const g = await api.newGame(mode, ROUNDS, vsGemma && health?.ok !== false)
        setPlay({ id: g.id, mode, vsGemma: g.vsGemma, card: g.card, scores: g.scores, chosen: null, result: null })
        setHistory([])
        setScreen('play')
      }),
    [run, vsGemma, health],
  )

  const choose = useCallback(
    (c: Choice) => {
      if (!play || play.chosen !== null) return
      setPlay({ ...play, chosen: c })
      run(async () => {
        try {
          const r = await api.answer(play.id, play.card.n, c)
          setPlay((p) => (p ? { ...p, result: r, scores: r.scores } : p))
          setHistory((h) => [...h, toRound(r)])
        } catch (e) {
          setPlay((p) => (p ? { ...p, chosen: null } : p))
          throw e
        }
      })
    },
    [play, run],
  )

  const next = useCallback(() => {
    if (!play?.result) return
    if (play.result.next === null) {
      setScreen('finale')
      return
    }
    const n = play.result.next
    run(async () => {
      const { card, scores } = await api.card(play.id, n)
      setPlay((p) => (p ? { ...p, card, scores, chosen: null, result: null } : p))
    })
  }, [play, run])

  // Keyboard: R / G, 1 / 2 / 3, Enter
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const k = e.key.toLowerCase()
      if (screen === 'title' && k === 'enter') {
        setScreen('modes')
        return
      }
      if (screen !== 'play' || !play) return
      if (play.result) {
        if (k === 'enter') {
          e.preventDefault()
          next()
        }
        return
      }
      if (play.chosen !== null) return
      if (play.mode === 'real-or-ghost' && (k === 'r' || k === 'g')) choose(k === 'r' ? 'real' : 'ghost')
      if (play.mode === 'three-defs' && ['1', '2', '3'].includes(k)) choose(Number(k) as 1 | 2 | 3)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [screen, play, choose, next])

  const home = () => {
    setScreen('title')
    setPlay(null)
  }

  return (
    <div className="app">
      <header className="top">
        {screen !== 'title' ? (
          <button className="brand" onClick={home} aria-label="Ghost Words, back to the title">
            Gh<em>o</em>st Words
          </button>
        ) : (
          <span />
        )}
        <div className="right">{play && screen === 'play' && <ScoreBar scores={play.scores} vsGemma={play.vsGemma} />}</div>
      </header>

      <main className="main">
        {error && (
          <div className="error-box" role="alert">
            {error}
            {error.includes('back end') && (
              <>
                <br />
                Start it with <code>uv run uvicorn backend.main:app --port 8000</code>
              </>
            )}
          </div>
        )}

        {screen === 'title' && <Title health={health} onEnter={() => setScreen('modes')} />}

        {screen === 'modes' && <ModePicker onPick={start} vsGemma={vsGemma} setVsGemma={setVsGemma} busy={busy} />}

        {screen === 'play' && play && (
          <div className="stage">
            <div>
              <p className="label">The question</p>
              {play.mode === 'real-or-ghost' ? (
                <Card card={play.card} chosen={play.chosen} busy={busy && !play.result} onChoose={choose} />
              ) : (
                <ThreeDefs
                  card={play.card}
                  result={play.result}
                  chosen={play.chosen}
                  busy={busy && !play.result}
                  onChoose={choose}
                />
              )}
            </div>
            <div>
              <p className="label">The reveal</p>
              {play.result ? (
                <RevealCard result={play.result} isLast={play.result.next === null} onNext={next} />
              ) : (
                <p className="waiting">
                  {play.chosen !== null
                    ? play.vsGemma
                      ? 'Gemma is still deciding…'
                      : 'Turning the page…'
                    : play.vsGemma
                      ? 'Gemma is reading the same card.'
                      : ''}
                </p>
              )}
            </div>
          </div>
        )}

        {screen === 'finale' && play && (
          <Finale
            scores={play.scores}
            rounds={history}
            mode={play.mode}
            vsGemma={play.vsGemma}
            onAgain={() => start(play.mode)}
            onModes={() => setScreen('modes')}
          />
        )}
      </main>

      <footer className="foot">
        <span>
          <span className="candle" />
          Offline · public-domain dictionary · open-weight model
        </span>
        <span>“dord” · 1934–1947</span>
      </footer>
    </div>
  )
}
