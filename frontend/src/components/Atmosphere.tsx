import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { motion } from 'motion/react'

/** A card coming up out of the fog: from below, blurred, then sharp. */
export function RiseFromFog({ children, delay = 0, slow = false }: { children: ReactNode; delay?: number; slow?: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: slow ? 90 : 56, filter: 'blur(12px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ duration: slow ? 2.2 : 0.95, delay, ease: [0.2, 0.7, 0.2, 1] }}
    >
      {children}
    </motion.div>
  )
}

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

interface Flash {
  kind: 'flicker'
  id: number
}

/**
 * The room around the cards: fog, eyes in the dark, vignette, film grain and the lights failing.
 * `dread` goes up by one on every wrong answer and blacks the room out briefly.
 * With prefers-reduced-motion there is no flicker and no blackout (CSS also stops the drift).
 */
export function Atmosphere({ dread }: { dread: number }) {
  const [flash, setFlash] = useState<Flash | null>(null)

  // The candles gutter now and then on their own.
  useEffect(() => {
    let timer: number
    const plan = () => {
      timer = window.setTimeout(() => {
        if (!reducedMotion() && document.visibilityState === 'visible') setFlash({ kind: 'flicker', id: Date.now() })
        plan()
      }, 18000 + Math.random() * 30000)
    }
    plan()
    return () => window.clearTimeout(timer)
  }, [])


  return (
    <div className="atmos" aria-hidden="true">
      <div className="fog fog-back" />
      <div className="fog fog-mid" />
      <div className="eyes e1">
        <i />
        <i />
      </div>
      <div className="eyes e2">
        <i />
        <i />
      </div>
      <div className="eyes e3">
        <i />
        <i />
      </div>
      <div className="fog fog-front" />
      <div className="vignette" />
      <div className="grain" />
      {flash && <div key={flash.id} className={`blackout ${flash.kind}`} onAnimationEnd={() => setFlash(null)} />}
      {/* A new key restarts the animation; it ends transparent. CSS hides it for reduced motion. */}
      {dread > 0 && <div key={`dread-${dread}`} className="blackout dark" />}
    </div>
  )
}
