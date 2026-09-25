import { useEffect, useRef, useState } from 'react'
import type WaveSurfer from 'wavesurfer.js'

type Jump = { start: number; end?: number; nonce: number } | null

export function Waveform({ url, jump, label }: { url: string; jump: Jump; label: string }) {
  const container = useRef<HTMLDivElement>(null)
  const player = useRef<WaveSurfer | null>(null)
  const [ready, setReady] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [rate, setRate] = useState(1)
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    let wave: WaveSurfer | null = null
    import('wavesurfer.js').then(({ default: WaveSurfer }) => {
      if (disposed || !container.current) return
      wave = WaveSurfer.create({ container: container.current, url, height: 80, waveColor: '#a5b4fc', progressColor: '#4f46e5', cursorColor: '#312e81' })
      player.current = wave
      wave.on('ready', () => setReady(true))
      wave.on('play', () => setPlaying(true))
      wave.on('pause', () => setPlaying(false))
      wave.on('error', () => setError('录音无法播放，请检查音频文件。'))
    }).catch(() => setError('无法载入波形播放器。'))
    return () => { disposed = true; wave?.destroy(); player.current = null }
  }, [url])
  useEffect(() => { if (ready && jump) void player.current?.play(jump.start, jump.end) }, [ready, jump])
  function toggleRate() {
    const next = rate === 1 ? 0.75 : 1
    player.current?.setPlaybackRate(next)
    setRate(next)
  }
  return <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="mb-3 flex items-center justify-between gap-3"><strong className="text-sm">{label}</strong><div className="flex gap-2"><button className="button-secondary" type="button" onClick={() => void player.current?.playPause()} disabled={!ready}>{playing ? '暂停' : '播放'}</button><button className="button-secondary" type="button" onClick={toggleRate} disabled={!ready}>{rate}×</button></div></div><div ref={container} aria-label={`${label}录音波形`} />{error && <p className="mt-2 text-sm text-red-700">{error}</p>}</div>
}
