import { memo, useState } from 'react'
import type { AcousticDisplay } from '../api/client'

const reasons: Record<string, string> = {
  audio_too_short: '录音过短', no_audible_signal: '没有足够的可听信号',
  no_reliable_pitch: '未检测到足够可靠的有声音高', processing_timeout: '曲线计算超时',
  processing_failed: '曲线计算失败', audio_exceeds_acoustic_display_limit: '录音超出曲线处理范围',
}

function AcousticPlot({ data, duration, label, onSeek }: { data?: AcousticDisplay; duration: number; label: string; onSeek: (time: number) => void }) {
  // 历史报告没有曲线字段时正常退化；纵轴统一标 Hz 和录音能量，避免误读波形振幅。
  const [selected, setSelected] = useState(0)
  if (!data || data.status !== 'complete' || !data.points.length) {
    return <p className="text-sm text-slate-600">{label}：{data ? reasons[data.reason || ''] || '曲线不可用' : '此历史报告没有曲线数据'}。现有录音和证据回听仍可使用。</p>
  }
  const width = 900
  const maxTime = Math.max(duration, data.points[data.points.length - 1].time_s)
  const x = (time: number) => (time / maxTime * width).toFixed(1)
  // 无可靠基频时断线，不用邻帧插值制造“连续音高”。
  const pitch = data.points.map((point, index) => point.pitch_hz === null ? '' : `${index === 0 || data.points[index - 1].pitch_hz === null ? 'M' : 'L'}${x(point.time_s)},${(98 - Math.min(1, Math.max(0, (point.pitch_hz - 75) / 375)) * 82).toFixed(1)}`).join(' ')
  const energy = data.points.map((point, index) => `${index ? 'L' : 'M'}${x(point.time_s)},${(208 - Math.min(1, Math.max(0, (point.energy_dbfs + 60) / 60)) * 82).toFixed(1)}`).join(' ')
  const seek = (time: number) => { setSelected(time); onSeek(time) }
  return <div>
    <p className="text-xs text-slate-600">上图：音高估计，越靠上频率越高；无声或无法可靠估计的地方断开。下图：录音能量，越靠上声音越强。两侧录音设备的响度不能直接比较。</p>
    <svg viewBox="0 0 900 235" className="mt-2 w-full cursor-crosshair rounded-lg bg-slate-50" aria-label={`${label}音高与能量时间曲线，点击位置回听`} onClick={event => {
      const rect = event.currentTarget.getBoundingClientRect()
      seek(Math.min(maxTime, Math.max(0, (event.clientX - rect.left) / rect.width * maxTime)))
    }}>
      <path d="M0 106 H900 M0 216 H900" stroke="#cbd5e1" strokeWidth="1" />
      <path d={pitch} fill="none" stroke="#4f46e5" strokeWidth="2" />
      <path d={energy} fill="none" stroke="#4f46e5" strokeWidth="2" />
      <path d={`M${x(selected)} 0 V220`} stroke="#312e81" strokeWidth="1" />
      <text x="8" y="13" fill="#475569" fontSize="13">音高 450 Hz ↑ / 75 Hz ↓</text>
      <text x="8" y="123" fill="#475569" fontSize="13">能量 强 ↑ / 弱 ↓</text>
      <text x="8" y="231" fill="#475569" fontSize="12">0 秒</text>
      <text x="842" y="231" fill="#475569" fontSize="12">{maxTime.toFixed(1)} 秒</text>
    </svg>
    <div className="mt-2 flex items-center gap-3 text-sm"><label htmlFor={`acoustic-${label}`}>定位</label><input id={`acoustic-${label}`} className="min-w-0 flex-1" type="range" min="0" max={maxTime} step="0.1" value={selected} onChange={event => setSelected(Number(event.target.value))} /><span>{selected.toFixed(1)} 秒</span><button type="button" className="text-indigo-700 underline" onClick={() => onSeek(selected)}>回听附近</button></div>
    <p className="mt-1 text-xs text-slate-500">曲线是未经人工校准的声学线索，不能单独判断重音、具体音素或 PTE 分数。</p>
  </div>
}

export default memo(AcousticPlot)
