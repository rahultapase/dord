// Thin client for the FastAPI back end (backend/main.py). Same origin: Vite proxies /api in dev.

export type Mode = 'real-or-ghost' | 'three-defs'
export type Choice = 'real' | 'ghost' | 1 | 2 | 3

export interface CardData {
  n: number
  rounds: number
  mode: Mode
  word: string
  pos: string
  definition?: string // real-or-ghost
  options?: string[] // three-defs
}

export interface Scores {
  you: number
  gemma: number
  gemmaAnswered: number
  round: number
  rounds: number
  finished: boolean
}

export interface Sense {
  text: string
  number?: string
  quote?: string
  author?: string
}

export interface Entry1913 {
  headline?: string
  pron?: string
  pos?: string
  etym?: string
  labels?: string[]
  line?: number
  senses: Sense[]
}

export interface Check {
  code: string
  label: string
}

export interface RealProof {
  kind: 'real'
  text: string
  entry: Entry1913
}

export interface GhostProof {
  kind: 'ghost'
  text: string
  checks: Check[]
  headwords: number
  ghost: { definition: string; etym: string; model: string; summoned: boolean }
}

export interface GemmaResult {
  answer: Choice | null
  source: 'live' | 'seance' | 'none' | 'timeout'
  seconds?: number
  correct: boolean | null
}

export interface AnswerResult {
  n: number
  choice: Choice
  correct: boolean
  truth: Choice
  kind: 'real' | 'ghost'
  word: string
  pos: string
  proof: RealProof | GhostProof
  gemma: GemmaResult | null
  scores: Scores
  next: number | null
  options?: string[]
}

export interface NewGameResult {
  id: string
  mode: Mode
  rounds: number
  vsGemma: boolean
  card: CardData
  scores: Scores
}

export interface Health {
  ok: boolean
  ollama: boolean
  models: Record<string, boolean>
  headwords: number
  reals: number
  ghosts: number
  threeDefsWords: number
  error?: string
}

export interface SummonResult {
  accepted: boolean
  word: string
  pos: string
  definition: string
  etym: string
  theme: string
  seconds: number
  model: string
  checks: Check[]
  reason: string
  code?: string
  match?: string | null
  entry?: Entry1913
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'The back end is not answering. Is uvicorn running on port 8000?')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : res.statusText
    throw new ApiError(res.status, detail)
  }
  return data as T
}

export const api = {
  health: () => call<Health>('GET', '/health'),
  newGame: (mode: Mode, rounds = 20, vsGemma = true) =>
    call<NewGameResult>('POST', '/game', { mode, rounds, vsGemma }),
  card: (id: string, n: number) => call<{ card: CardData; scores: Scores }>('GET', `/game/${id}/card/${n}`),
  answer: (id: string, n: number, choice: Choice) =>
    call<AnswerResult>('POST', `/game/${id}/answer`, { n, choice }),
  summon: () => call<SummonResult>('POST', '/ghosts/summon'),
}

/** 'Gal`li*mau"fry' -> 'Gal·li·mau′fry' (1913 accent marks shown the way the book prints them). */
export function prettyPron(p: string | undefined): string {
  if (!p) return ''
  return p.replace(/\*/g, '\u00b7').replace(/"/g, '\u2032').replace(/`/g, '\u02ce')
}
