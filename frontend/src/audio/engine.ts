// Every sound in the game, generated with the Web Audio API. No audio files, no licences.
//
// Graph:  sources -> sfx / ambient buses -> (dry + reverb) -> master gain -> compressor -> out
// The AudioContext is created on the first click (browsers block audio before that). Muting ramps
// the master gain to 0 and then suspends the context, so nothing at all reaches the speakers.

const STORE_KEY = 'ghost-words:sound'
const MASTER = 0.8

type Listener = (muted: boolean) => void

function loadMuted(): boolean {
  try {
    return localStorage.getItem(STORE_KEY) === 'off'
  } catch {
    return false
  }
}

function rand(a: number, b: number): number {
  return a + Math.random() * (b - a)
}

class Engine {
  private ctx: AudioContext | null = null
  private master!: GainNode
  private sfx!: GainNode
  private amb!: GainNode
  private wet!: GainNode
  private analyser!: AnalyserNode
  private white!: AudioBuffer
  private brown!: AudioBuffer
  private muted = loadMuted()
  private ambientOn = false
  private suspendTimer: number | undefined
  private listeners = new Set<Listener>()

  // ------------------------------------------------------------------ state

  isMuted(): boolean {
    return this.muted
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  /** Call from a click or key press. Creates the context and starts the room tone. */
  unlock(): void {
    if (!this.ctx) this.build()
    const ctx = this.ctx
    if (!ctx) return
    if (!this.muted && ctx.state !== 'running') void ctx.resume()
    this.startAmbient()
  }

  setMuted(m: boolean): void {
    this.muted = m
    try {
      localStorage.setItem(STORE_KEY, m ? 'off' : 'on')
    } catch {
      /* private mode: the choice just isn't remembered */
    }
    this.listeners.forEach((fn) => fn(m))
    const ctx = this.ctx
    if (!ctx) return
    const g = this.master.gain
    const now = ctx.currentTime
    window.clearTimeout(this.suspendTimer)
    g.cancelScheduledValues(now)
    g.setValueAtTime(g.value, now)
    if (m) {
      g.linearRampToValueAtTime(0, now + 0.25)
      this.suspendTimer = window.setTimeout(() => {
        if (this.muted) void ctx.suspend()
      }, 320)
    } else {
      void ctx.resume().then(() => {
        const t = ctx.currentTime
        g.cancelScheduledValues(t)
        g.setValueAtTime(0, t)
        g.linearRampToValueAtTime(MASTER, t + 0.6)
      })
    }
  }

  /** The speaker button and the M key. Unmuting counts as the first click if it comes first. */
  toggle(): void {
    const m = !this.muted
    this.setMuted(m)
    if (!m) this.unlock()
  }

  /** RMS of what is going to the speakers right now (0 when muted). For checks in dev tools. */
  level(): number {
    if (!this.ctx || this.ctx.state !== 'running') return 0
    const buf = new Float32Array(this.analyser.fftSize)
    this.analyser.getFloatTimeDomainData(buf)
    let s = 0
    for (const v of buf) s += v * v
    return Math.sqrt(s / buf.length)
  }

  state(): string {
    return this.ctx ? this.ctx.state : 'not created'
  }

  // ------------------------------------------------------------------ graph

  private build(): void {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AC) return
    const ctx = new AC()
    this.ctx = ctx

    const comp = ctx.createDynamicsCompressor()
    comp.threshold.value = -14
    comp.ratio.value = 4
    this.analyser = ctx.createAnalyser()
    this.analyser.fftSize = 1024
    this.master = ctx.createGain()
    this.master.gain.value = this.muted ? 0 : MASTER
    this.master.connect(comp).connect(this.analyser).connect(ctx.destination)

    // A cold stone room: a convolver fed with a decaying noise impulse.
    const verb = ctx.createConvolver()
    verb.buffer = this.impulse(3.2, 2.6)
    this.wet = ctx.createGain()
    this.wet.gain.value = 0.32
    this.wet.connect(verb).connect(this.master)

    this.sfx = ctx.createGain()
    this.sfx.gain.value = 1
    this.sfx.connect(this.master)
    this.amb = ctx.createGain()
    this.amb.gain.value = 0
    this.amb.connect(this.master)

    this.white = this.noiseBuffer(2, false)
    this.brown = this.noiseBuffer(6, true)

    if (this.muted) void ctx.suspend()
  }

  private noiseBuffer(seconds: number, brown: boolean): AudioBuffer {
    const ctx = this.ctx!
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate)
    const d = buf.getChannelData(0)
    let last = 0
    for (let i = 0; i < d.length; i++) {
      const w = Math.random() * 2 - 1
      if (brown) {
        last = (last + 0.02 * w) / 1.02
        d[i] = last * 3.5
      } else {
        d[i] = w
      }
    }
    return buf
  }

  private impulse(seconds: number, decay: number): AudioBuffer {
    const ctx = this.ctx!
    const len = Math.floor(ctx.sampleRate * seconds)
    const buf = ctx.createBuffer(2, len, ctx.sampleRate)
    for (let c = 0; c < 2; c++) {
      const d = buf.getChannelData(c)
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay)
    }
    return buf
  }

  /** Is it worth making a sound right now? */
  private live(): AudioContext | null {
    const ctx = this.ctx
    if (!ctx || this.muted || ctx.state !== 'running') return null
    return ctx
  }

  private noise(buf: AudioBuffer, t: number, dur: number, rate = 1): AudioBufferSourceNode {
    const src = this.ctx!.createBufferSource()
    src.buffer = buf
    src.loop = true
    src.playbackRate.value = rate
    src.start(t, Math.random() * (buf.duration - 0.1))
    src.stop(t + dur + 0.05)
    return src
  }

  /** Route a node to the dry sfx bus and, optionally, the reverb. */
  private out(node: AudioNode, wet = 0): void {
    node.connect(this.sfx)
    if (wet > 0) {
      const g = this.ctx!.createGain()
      g.gain.value = wet
      node.connect(g).connect(this.wet)
    }
  }

  // ------------------------------------------------------------------ ambient

  private startAmbient(): void {
    const ctx = this.ctx
    if (!ctx || this.ambientOn) return
    this.ambientOn = true
    const t = ctx.currentTime

    // Two detuned low drones: A1 and the tritone above it, each a beating pair.
    const lp = ctx.createBiquadFilter()
    lp.type = 'lowpass'
    lp.frequency.value = 170
    lp.Q.value = 0.8
    const droneGain = ctx.createGain()
    droneGain.gain.value = 0.11
    lp.connect(droneGain).connect(this.amb)
    const lfo = ctx.createOscillator()
    lfo.frequency.value = 0.045
    const lfoAmt = ctx.createGain()
    lfoAmt.gain.value = 70
    lfo.connect(lfoAmt).connect(lp.frequency)
    lfo.start(t)
    for (const [f, type, g] of [
      [55, 'sawtooth', 0.5],
      [55.35, 'sawtooth', 0.5],
      [77.78, 'triangle', 0.35],
      [78.2, 'triangle', 0.35],
    ] as const) {
      const o = ctx.createOscillator()
      o.type = type
      o.frequency.value = f
      const og = ctx.createGain()
      og.gain.value = g
      o.connect(og).connect(lp)
      o.start(t)
    }
    // Slow swell on the tritone pair so the room seems to breathe.
    const breath = ctx.createOscillator()
    breath.frequency.value = 0.07
    const breathAmt = ctx.createGain()
    breathAmt.gain.value = 0.04
    breath.connect(breathAmt).connect(droneGain.gain)
    breath.start(t)

    // Wind: brown noise through a wandering band-pass.
    const wind = ctx.createBufferSource()
    wind.buffer = this.brown
    wind.loop = true
    const bp = ctx.createBiquadFilter()
    bp.type = 'bandpass'
    bp.frequency.value = 420
    bp.Q.value = 0.9
    const windGain = ctx.createGain()
    windGain.gain.value = 0.3
    wind.connect(bp).connect(windGain).connect(this.amb)
    const gust = ctx.createOscillator()
    gust.frequency.value = 0.06
    const gustAmt = ctx.createGain()
    gustAmt.gain.value = 260
    gust.connect(gustAmt).connect(bp.frequency)
    const gust2 = ctx.createOscillator()
    gust2.frequency.value = 0.11
    const gust2Amt = ctx.createGain()
    gust2Amt.gain.value = 0.16
    gust2.connect(gust2Amt).connect(windGain.gain)
    wind.start(t)
    gust.start(t)
    gust2.start(t)

    // Fade the room in.
    this.amb.gain.setValueAtTime(0, t)
    this.amb.gain.linearRampToValueAtTime(1, t + 4)

    this.crackle()
  }

  /** A candle that spits now and then, in little clusters. */
  private crackle(): void {
    const ctx = this.live()
    if (ctx && document.visibilityState === 'visible') {
      const pops = Math.random() < 0.25 ? Math.floor(rand(2, 5)) : 1
      let t = ctx.currentTime + 0.01
      for (let i = 0; i < pops; i++) {
        const src = this.noise(this.white, t, 0.06, rand(0.6, 1.4))
        const hp = ctx.createBiquadFilter()
        hp.type = 'highpass'
        hp.frequency.value = rand(1400, 3800)
        const g = ctx.createGain()
        const peak = rand(0.025, 0.09)
        g.gain.setValueAtTime(0.0001, t)
        g.gain.exponentialRampToValueAtTime(peak, t + 0.002)
        g.gain.exponentialRampToValueAtTime(0.0001, t + rand(0.015, 0.05))
        src.connect(hp).connect(g).connect(this.amb)
        t += rand(0.03, 0.12)
      }
    }
    window.setTimeout(() => this.crackle(), rand(180, 1400))
  }

  // ------------------------------------------------------------------ effects

  /** Card in: a short paper rustle. */
  rustle(): void {
    const ctx = this.live()
    if (!ctx) return
    const t = ctx.currentTime + 0.02
    const src = this.noise(this.white, t, 0.45)
    const bp = ctx.createBiquadFilter()
    bp.type = 'bandpass'
    bp.Q.value = 1.1
    bp.frequency.setValueAtTime(1100, t)
    bp.frequency.exponentialRampToValueAtTime(4200, t + 0.18)
    bp.frequency.exponentialRampToValueAtTime(1800, t + 0.42)
    const g = ctx.createGain()
    g.gain.setValueAtTime(0.0001, t)
    // Crinkles: a few bumps rather than one smooth swell.
    for (const [dt, v] of [[0.025, 0.22], [0.08, 0.07], [0.13, 0.18], [0.2, 0.05], [0.26, 0.12]] as const) {
      g.gain.linearRampToValueAtTime(v, t + dt)
    }
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.44)
    src.connect(bp).connect(g)
    this.out(g, 0.15)
  }

  private whoosh(t: number): void {
    const ctx = this.ctx!
    const src = this.noise(this.white, t, 1.1)
    const bp = ctx.createBiquadFilter()
    bp.type = 'bandpass'
    bp.Q.value = 2.2
    bp.frequency.setValueAtTime(160, t)
    bp.frequency.exponentialRampToValueAtTime(2600, t + 0.85)
    const g = ctx.createGain()
    g.gain.setValueAtTime(0.0001, t)
    g.gain.exponentialRampToValueAtTime(0.32, t + 0.7)
    g.gain.exponentialRampToValueAtTime(0.0001, t + 1.05)
    const pan = ctx.createStereoPanner()
    pan.pan.setValueAtTime(-0.6, t)
    pan.pan.linearRampToValueAtTime(0.5, t + 1)
    src.connect(bp).connect(g).connect(pan)
    this.out(pan, 0.4)
  }

  private thud(t: number, level = 0.9): void {
    const ctx = this.ctx!
    const o = ctx.createOscillator()
    o.type = 'sine'
    o.frequency.setValueAtTime(95, t)
    o.frequency.exponentialRampToValueAtTime(36, t + 0.35)
    const g = ctx.createGain()
    g.gain.setValueAtTime(0.0001, t)
    g.gain.exponentialRampToValueAtTime(level, t + 0.008)
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.55)
    o.connect(g)
    o.start(t)
    o.stop(t + 0.6)
    this.out(g, 0.25)
    // The knock of the stamp on the desk.
    const n = this.noise(this.white, t, 0.08)
    const lp = ctx.createBiquadFilter()
    lp.type = 'lowpass'
    lp.frequency.value = 900
    const ng = ctx.createGain()
    ng.gain.setValueAtTime(0.0001, t)
    ng.gain.exponentialRampToValueAtTime(level * 0.35, t + 0.003)
    ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.07)
    n.connect(lp).connect(ng)
    this.out(ng)
  }

  /** Breath shaped by moving formants: a whisper with no words in it. */
  whisper(delay = 0, dur = 1.5): void {
    const ctx = this.live()
    if (!ctx) return
    const t = ctx.currentTime + delay
    const src = this.noise(this.white, t, dur)
    const hp = ctx.createBiquadFilter()
    hp.type = 'highpass'
    hp.frequency.value = 700
    src.connect(hp)
    const sum = ctx.createGain()
    sum.gain.value = 1
    for (const base of [650, 1150, 2500]) {
      const f = ctx.createBiquadFilter()
      f.type = 'bandpass'
      f.Q.value = 9
      // Glide between vowel-ish positions, like syllables.
      let tt = t
      f.frequency.setValueAtTime(base * rand(0.8, 1.2), tt)
      while (tt < t + dur) {
        tt += rand(0.12, 0.28)
        f.frequency.linearRampToValueAtTime(base * rand(0.75, 1.3), tt)
      }
      hp.connect(f).connect(sum)
    }
    const env = ctx.createGain()
    env.gain.setValueAtTime(0.0001, t)
    let tt = t
    while (tt < t + dur - 0.15) {
      const len = rand(0.12, 0.3)
      env.gain.linearRampToValueAtTime(rand(0.25, 0.6), tt + len * 0.4)
      env.gain.linearRampToValueAtTime(rand(0.03, 0.1), tt + len)
      tt += len
    }
    env.gain.linearRampToValueAtTime(0.0001, t + dur)
    const pan = ctx.createStereoPanner()
    pan.pan.setValueAtTime(rand(-0.8, 0.8), t)
    pan.pan.linearRampToValueAtTime(rand(-0.8, 0.8), t + dur)
    sum.connect(env).connect(pan)
    this.out(pan, 0.55)
  }

  /** An inharmonic bell: partials of a real church bell, each decaying at its own rate. */
  private bell(t: number, base: number, decay: number, level: number): void {
    const ctx = this.ctx!
    const partials: [number, number][] = [
      [0.5, 0.7], [1, 1], [1.183, 0.55], [1.506, 0.4], [2, 0.32], [2.514, 0.2], [2.662, 0.16], [3.011, 0.12], [4.166, 0.07],
    ]
    const bus = ctx.createGain()
    bus.gain.value = level / 3
    for (const [ratio, amp] of partials) {
      const o = ctx.createOscillator()
      o.type = 'sine'
      o.frequency.value = base * ratio
      o.detune.value = rand(-4, 4)
      const g = ctx.createGain()
      const d = decay / Math.pow(ratio, 0.6)
      g.gain.setValueAtTime(0.0001, t)
      g.gain.exponentialRampToValueAtTime(amp, t + 0.004)
      g.gain.exponentialRampToValueAtTime(0.0001, t + d)
      o.connect(g).connect(bus)
      o.start(t)
      o.stop(t + d + 0.05)
    }
    this.out(bus, 0.6)
  }

  private heartbeat(t: number): void {
    const ctx = this.ctx!
    for (const [dt, v] of [[0, 0.8], [0.24, 0.55], [0.86, 0.75], [1.1, 0.5]] as const) {
      const o = ctx.createOscillator()
      o.type = 'sine'
      o.frequency.setValueAtTime(62, t + dt)
      o.frequency.exponentialRampToValueAtTime(38, t + dt + 0.16)
      const lp = ctx.createBiquadFilter()
      lp.type = 'lowpass'
      lp.frequency.value = 140
      const g = ctx.createGain()
      g.gain.setValueAtTime(0.0001, t + dt)
      g.gain.exponentialRampToValueAtTime(v, t + dt + 0.012)
      g.gain.exponentialRampToValueAtTime(0.0001, t + dt + 0.2)
      o.connect(lp).connect(g)
      o.start(t + dt)
      o.stop(t + dt + 0.25)
      this.out(g, 0.1)
    }
  }

  private dissonance(t: number): void {
    const ctx = this.ctx!
    const lp = ctx.createBiquadFilter()
    lp.type = 'lowpass'
    lp.frequency.value = 1300
    const g = ctx.createGain()
    g.gain.setValueAtTime(0.0001, t)
    g.gain.linearRampToValueAtTime(0.075, t + 0.18)
    g.gain.exponentialRampToValueAtTime(0.0001, t + 1.3)
    lp.connect(g)
    const vib = ctx.createOscillator()
    vib.frequency.value = 5.5
    const vibAmt = ctx.createGain()
    vibAmt.gain.value = 9
    vib.connect(vibAmt)
    vib.start(t)
    vib.stop(t + 1.4)
    for (const f of [220, 233.08, 311.13]) {
      const o = ctx.createOscillator()
      o.type = 'triangle'
      o.frequency.value = f
      vibAmt.connect(o.detune)
      o.connect(lp)
      o.start(t)
      o.stop(t + 1.4)
    }
    this.out(g, 0.5)
  }

  // ------------------------------------------------------------------ cues used by the UI

  /** Ghost reveal: rising whoosh, the stamp's thud, then a whisper. */
  ghostReveal(): void {
    const ctx = this.live()
    if (!ctx) return
    const t = ctx.currentTime + 0.02
    this.whoosh(t)
    this.thud(t + 0.42)
    this.whisper(0.85, 1.4)
  }

  /** Real reveal: one low bell. */
  realReveal(): void {
    const ctx = this.live()
    if (!ctx) return
    this.bell(ctx.currentTime + 0.05, 146.8, 4.5, 0.55)
  }

  /** Wrong answer: a double heartbeat and a brief dissonant chord. */
  wrong(): void {
    const ctx = this.live()
    if (!ctx) return
    const t = ctx.currentTime + 0.55
    this.heartbeat(t)
    this.dissonance(t + 0.1)
  }

  /** Finale: a bell tolling three times. */
  toll(): void {
    const ctx = this.live()
    if (!ctx) return
    const t = ctx.currentTime + 0.3
    for (let i = 0; i < 3; i++) this.bell(t + i * 2.4, 98, 7, 0.75)
  }

  /** The stamp alone (used on the finale card). */
  stamp(delay = 0): void {
    const ctx = this.live()
    if (!ctx) return
    this.thud(ctx.currentTime + delay, 0.8)
  }
}

export const audio = new Engine()

if (import.meta.env.DEV) {
  ;(window as unknown as { __ghostAudio: Engine }).__ghostAudio = audio
}
