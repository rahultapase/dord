import { useEffect, useState } from 'react'
import { Volume2, VolumeX } from 'lucide-react'
import { audio } from '../audio/engine'

/** Speaker button, top right. M toggles it too. The choice is kept in localStorage. */
export function SoundToggle() {
  const [muted, setMuted] = useState(audio.isMuted())

  useEffect(() => audio.subscribe(setMuted), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return
      if (e.key.toLowerCase() === 'm') audio.toggle()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const label = muted ? 'Sound off (M to turn on)' : 'Sound on (M to mute)'
  return (
    <button className="sound" onClick={() => audio.toggle()} title={label} aria-label="Sound" aria-pressed={!muted}>
      {muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
    </button>
  )
}
