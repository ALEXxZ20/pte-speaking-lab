import { useEffect, useRef, useState } from 'react'
import type WaveSurfer from 'wavesurfer.js'

type Jump = { start: number; end?: number; nonce: number } | null

let activePlayer: WaveSurfer | null = null

function takeAudioFocus(next: WaveSurfer) {
  if (activePlayer && activePlayer !== next) activePlayer.pause()
  activePlayer = next
}

function releaseAudioFocus(wave: WaveSurfer) {
  if (activePlayer === wave) activePlayer = null
}

export function Waveform({ url, jump, label, height = 80 }: { url: string; jump: Jump; label: string; height?: number }) {
  const container = useRef<HTMLDivElement>(null)
  const player = useRef<WaveSurfer | null>(null)
  const [ready, setReady] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [rate, setRate] = useState(1)
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    let wave: WaveSurfer | null = null
    setReady(false)
    setPlaying(false)
    import('wavesurfer.js').then(({ default: WaveSurfer }) => {
      if (disposed || !container.current) return
      const created = WaveSurfer.create({ container: container.current, url, height, waveColor: '#a5b4fc', progressColor: '#4f46e5', cursorColor: '#312e81' })
      wave = created
      player.current = created
      created.on('ready', () => setReady(true))
      created.on('play', () => { takeAudioFocus(created); setPlaying(true) })
      created.on('pause', () => { releaseAudioFocus(created); setPlaying(false) })
      created.on('finish', () => { releaseAudioFocus(created); setPlaying(false) })
      created.on('error', () => { releaseAudioFocus(created); setError('录音无法播放，请检查音频文件。') })
    }).catch(() => setError('无法载入波形播放器。'))
    return () => { disposed = true; if (wave) { releaseAudioFocus(wave); wave.destroy() }; player.current = null }
  }, [url, height])
  useEffect(() => {
    const wave = player.current
    if (ready && jump && wave) {
      takeAudioFocus(wave)
      void wave.play(jump.start, jump.end).catch(() => releaseAudioFocus(wave))
    }
  }, [ready, jump])
  function togglePlayback() {
    const wave = player.current
    if (!wave) return
    if (wave.isPlaying()) wave.pause()
    else {
      takeAudioFocus(wave)
      void wave.play().catch(() => releaseAudioFocus(wave))
    }
  }
  function toggleRate() {
    const next = rate === 1 ? 0.75 : 1
    player.current?.setPlaybackRate(next)
    setRate(next)
  }
  return <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="mb-3 flex items-center justify-between gap-3"><strong className="text-sm">{label} · 振幅波形</strong><div className="flex gap-2"><button className="button-secondary" type="button" onClick={togglePlayback} disabled={!ready}>{playing ? '暂停' : '播放'}</button><button className="button-secondary" type="button" onClick={toggleRate} disabled={!ready}>{rate}×</button></div></div><div ref={container} aria-label={`${label}录音振幅波形，播放光标随时间移动`} />{error && <p className="mt-2 text-sm text-red-700">{error}</p>}</div>
}
