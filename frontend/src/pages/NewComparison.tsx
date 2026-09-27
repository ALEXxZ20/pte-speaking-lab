import { useEffect, useState, type ClipboardEvent, type FormEvent } from 'react'
import { createComparison, importScreenshot, previewScreenshot, upload, type Comparison, type Draft, type Sample, type SampleRecord, updateSample } from '../api/client'

type Role = 'user' | 'benchmark'
export type FormSide = { audio: File | null; screenshot: File | null; screenshotId: string | null; ocrText: string; transcript: string; copied: string; draft: Draft | null; pronunciation: string; fluency: string; content: string; recognizing: boolean }
export const empty = (): FormSide => ({ audio: null, screenshot: null, screenshotId: null, ocrText: '', transcript: '', copied: '', draft: null, pronunciation: '', fluency: '', content: '', recognizing: false })
const names: Record<Role, string> = { user: '我的回答', benchmark: 'AI 生成的高分参考录音' }
const colors = { red: '红色', yellow: '黄色', green: '绿色', unknown: '未知' }
function transcriptDifference(visible: string, copied: string) {
  const left = visible.trim().split(/\s+/), right = copied.trim().split(/\s+/)
  const different = left.map((word, index) => ({ index, word, other: right[index] || '∅' }))
    .filter(item => item.word.toLocaleLowerCase() !== item.other.toLocaleLowerCase())
  const extra = Math.max(0, right.length - left.length)
  return `按词位置发现 ${different.length + extra} 处差异${left.length !== right.length ? `；词数 ${left.length}/${right.length}` : ''}。` +
    different.slice(0, 5).map(item => ` 第 ${item.index + 1} 词：截图「${item.word}」/复制「${item.other}」`).join('')
}

function ScoreField({ label, value, max, change }: { label: string; value: string; max: string; change: (value: string) => void }) {
  return <label className="block text-sm text-slate-700"><span className="font-medium">{label}</span><span className="mt-1 flex items-center gap-2"><input className="field w-24" type="number" min="0" max={max} step="0.1" value={value} onChange={event => change(event.target.value)} required /><span className="text-slate-500">/ {max}</span></span></label>
}

export function PictureInput({ label, file, onFile }: { label: string; file: File | null; onFile: (file: File) => void }) {
  function paste(event: ClipboardEvent<HTMLDivElement>) {
    const image = [...event.clipboardData.items].find(item => item.type.startsWith('image/'))?.getAsFile()
    if (image) { event.preventDefault(); onFile(new File([image], `粘贴截图-${Date.now()}.png`, { type: image.type })) }
  }
  return <div className="text-sm font-medium"><label>{label}<input className="file-field mt-2" type="file" accept="image/png,image/jpeg" onChange={event => { const file = event.target.files?.[0]; if (file) onFile(file) }} /></label><div tabIndex={0} onPaste={paste} className="mt-2 rounded-lg border border-dashed border-indigo-300 bg-indigo-50 p-3 text-sm font-normal text-indigo-800 focus:outline-indigo-500">点击这里后按 ⌘V 粘贴截图{file && ` · 已选 ${file.name}`}</div></div>
}

export function SampleForm({ role, value, change, recognize }: { role: Role; value: FormSide; change: (next: FormSide) => void; recognize: (file: File) => void }) {
  const set = (field: keyof FormSide, next: string | File | null) => change({ ...value, [field]: next })
  return <section className="panel space-y-5"><div><p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">{role === 'user' ? '01' : '02'} · Response Sample</p><h2 className="mt-1 text-xl font-semibold">{names[role]}</h2>{role === 'benchmark' && <p className="mt-1 text-sm text-slate-600">上传已生成的 AI 音频，以及这段音频在猩际 PTE 得到的转写、截图和三项分数。本项目不生成朗读音频。</p>}</div>
    <label className="block text-sm font-medium">录音文件 <span className="text-red-600">*</span><input className="file-field mt-2" type="file" accept="audio/*,.m4a,.mp4,.webm,.wav,.mp3" onChange={event => set('audio', event.target.files?.[0] || null)} /></label>
    <PictureInput label="猩际逐词颜色截图 *" file={value.screenshot} onFile={recognize} />
    <label className="block text-sm font-medium">截图识别的实际转写 <span className="text-red-600">*</span><textarea className="field mt-2 min-h-40 w-full resize-y" value={value.transcript} onChange={event => set('transcript', event.target.value)} placeholder="上传或粘贴截图后自动识别；提交前可修改" required /></label>
    <p className="text-sm text-slate-600">{value.recognizing ? '正在识别截图…' : value.draft ? `识别 ${value.draft.tokens.length} 词 · 候选颜色 ${value.draft.candidate_count} · 未知 ${value.draft.unknown_count}` : '截图会同时提取文字与词色候选。'}</p>
    <label className="block text-sm font-medium">复制的猩际转写（可选，用于核对）<textarea className="field mt-2 min-h-24 w-full resize-y" value={value.copied} onChange={event => set('copied', event.target.value)} placeholder="可留空；与截图识别不同也能提交" /></label>
    {value.copied.trim() && value.transcript.trim() && value.copied.trim() !== value.transcript.trim() && <p className="rounded-lg bg-amber-50 p-2 text-sm text-amber-900">复制文本与当前转写不同：{transcriptDifference(value.transcript, value.copied)} 差异不阻止提交。</p>}
    <div className="grid grid-cols-3 gap-3"><ScoreField label="Pronunciation" value={value.pronunciation} max="90" change={next => set('pronunciation', next)} /><ScoreField label="Fluency" value={value.fluency} max="90" change={next => set('fluency', next)} /><ScoreField label="Content" value={value.content} max="5" change={next => set('content', next)} /></div>
  </section>
}

export function ReviewPanel({ record, draft, onSaved }: { record: SampleRecord; draft: Draft | null; onSaved: (next: SampleRecord) => void }) {
  const initial = record.sample.tokens.map(token => ({ color: token.color, confirmed: token.color_review_status === 'confirmed' }))
  const [choices, setChoices] = useState(() => draft ? draft.tokens.map((token, index) => ({ color: (initial[index]?.confirmed ? initial[index].color : token.candidate_color), confirmed: initial[index]?.confirmed || false })) : initial)
  useEffect(() => {
    if (!draft) return
    setChoices(draft.tokens.map((token, index) => {
      const saved = record.sample.tokens[index]
      const confirmed = saved?.color_review_status === 'confirmed'
      return { color: confirmed ? saved.color : saved?.color_review_status === 'candidate' ? saved.color : token.candidate_color, confirmed }
    }))
  }, [draft, record.id])
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const setChoice = (index: number, color: Sample['tokens'][number]['color']) => setChoices(previous => previous.map((item, i) => i === index ? { color, confirmed: color !== 'unknown' } : item))
  const confirmAll = () => setChoices(previous => previous.map(item => ({ ...item, confirmed: item.color !== 'unknown' })))
  async function save() {
    setSaving(true); setMessage('')
    try {
      const sample: Sample = { ...record.sample, tokens: record.sample.tokens.map((token, index) => ({ ...token,
        color: choices[index]?.color || 'unknown',
        color_review_status: choices[index]?.confirmed ? 'confirmed' : choices[index]?.color !== 'unknown' ? 'candidate' : 'unreviewed',
        color_source_screenshot_id: choices[index]?.color !== 'unknown' ? record.sample.color_screenshot_asset_ids[0] : null,
      })) }
      const result = await updateSample(record, sample)
      onSaved(result)
      setMessage('复核结果已保存。')
    } catch (error) { setMessage(error instanceof Error ? error.message : '保存失败') }
    finally { setSaving(false) }
  }
  return <section className="panel"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{names[record.sample.role]} · 词色复核</h3><p className="mt-1 text-sm text-slate-600">{draft ? `识别 ${draft.candidate_count} 词，尚未人工确认 ${choices.filter(choice => !choice.confirmed && choice.color !== 'unknown').length} 词` : '暂无截图映射草稿'} · <span className="font-semibold text-red-700" title="未知词请对照截图手动复核">! 未知 {choices.filter(choice => choice.color === 'unknown').length}（需手动复核）</span></p></div><div className="flex gap-2"><button type="button" className="button-secondary" onClick={confirmAll} disabled={!draft}>确认全部可识别词</button><button type="button" className="button-primary" onClick={save} disabled={saving}>{saving ? '保存中…' : '保存复核'}</button></div></div>
    {message && <p role="status" className="mt-3 text-sm text-indigo-700">{message}</p>}
    <div className="mt-5 grid gap-5 lg:grid-cols-2"><div className="max-h-[36rem] overflow-auto rounded-xl bg-slate-100 p-2">{record.sample.color_screenshot_asset_ids[0] ? <img className="mx-auto max-w-full" src={`/api/v1/assets/screenshots/${record.sample.color_screenshot_asset_ids[0]}`} alt={`${names[record.sample.role]}猩际逐词颜色原图`} /> : '无截图'}</div><div className="max-h-[36rem] space-y-2 overflow-auto pr-2">{record.sample.tokens.map((token, index) => <label key={token.index} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-2 text-sm"><span className="min-w-0 flex-1 truncate"><span className="mr-2 text-slate-400">{index + 1}</span>{token.surface}</span><select className="rounded-md border border-slate-300 p-1" aria-label={`${token.surface} 的颜色`} value={choices[index]?.color || 'unknown'} onChange={event => setChoice(index, event.target.value as Sample['tokens'][number]['color'])}>{Object.entries(colors).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><span className={choices[index]?.confirmed ? 'text-emerald-700' : 'text-amber-700'}>{choices[index]?.confirmed ? '已确认' : '待确认'}</span></label>)}</div></div>
    <p className="mt-4 text-sm text-slate-500">截图候选已参与分析，但可信度较低；人工修改或确认后会成为已确认颜色。截图没有可靠的停顿标签时会显示“不可用”。</p>
  </section>
}

export default function NewComparison() {
  const [title, setTitle] = useState('')
  const [questionType, setQuestionType] = useState('DI')
  const [readingText, setReadingText] = useState('')
  const [readingOcr, setReadingOcr] = useState('')
  const [readingScreenshot, setReadingScreenshot] = useState<File | null>(null)
  const [readingScreenshotId, setReadingScreenshotId] = useState<string | null>(null)
  const [sides, setSides] = useState<Record<Role, FormSide>>({ user: empty(), benchmark: empty() })
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [drafts, setDrafts] = useState<Record<Role, Draft | null>>({ user: null, benchmark: null })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  function score(value: string, max: number) { return value.trim() ? { value: Number(value), max } : null }
  async function recognizeSide(role: Role, file: File) {
    setSides(previous => ({ ...previous, [role]: { ...previous[role], screenshot: file, screenshotId: null, draft: null, recognizing: true } }))
    setMessage('')
    try {
      const asset = await upload('screenshots', file)
      const result = await previewScreenshot(asset.id, 'xingji')
      setSides(previous => ({ ...previous, [role]: { ...previous[role], screenshotId: asset.id, ocrText: result.text, transcript: result.text, draft: result.draft, recognizing: false } }))
    } catch (error) {
      setSides(previous => ({ ...previous, [role]: { ...previous[role], recognizing: false } }))
      setMessage(`${names[role]}截图识别失败：${error instanceof Error ? error.message : '未知错误'}`)
    }
  }
  async function recognizeReading(file: File) {
    setReadingScreenshot(file); setReadingScreenshotId(null); setMessage('正在识别共同朗读稿截图…')
    try {
      const asset = await upload('screenshots', file)
      const result = await previewScreenshot(asset.id, 'reading_script')
      setReadingScreenshotId(asset.id); setReadingOcr(result.text); setReadingText(result.text)
      setMessage(`共同朗读稿截图识别了 ${result.word_count} 个词，请检查并修改。`)
    } catch (error) { setMessage(`共同朗读稿识别失败：${error instanceof Error ? error.message : '未知错误'}`) }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!readingText.trim() || Object.values(sides).some(side => !side.audio || !side.screenshotId || !side.transcript.trim() || !side.pronunciation || !side.fluency || !side.content)) { setMessage('请填写共同朗读稿，并为两侧提供录音、成功识别的截图和三项分数。'); return }
    setBusy(true); setMessage('正在上传并保存双边样本…')
    try {
      const roles: Role[] = ['user', 'benchmark']
      const uploads = await Promise.all(roles.map(async role => ({ role, audio: await upload('audio', sides[role].audio!), screenshotId: sides[role].screenshotId! })))
      const mapped = await Promise.all(uploads.map(async item => ({ ...item, preview: await previewScreenshot(item.screenshotId, 'xingji', sides[item.role].transcript) })))
      const body = { exercise: { question_type: questionType, title: title || null, reading_text_raw: readingText,
        reading_text_source: readingScreenshotId ? readingText === readingOcr ? 'screenshot_ocr' : 'screenshot_ocr_edited' : 'manual',
        reading_text_ocr_raw: readingScreenshotId ? readingOcr : null, reading_screenshot_asset_id: readingScreenshotId },
        samples: mapped.map(({ role, audio, screenshotId, preview }) => ({ role, audio_origin: role === 'user' ? 'human_recording' : 'ai_generated',
          audio_asset_id: audio.id, color_screenshot_asset_ids: [screenshotId], transcript_raw: sides[role].transcript,
          transcript_source: sides[role].transcript === sides[role].ocrText ? 'screenshot_ocr' : 'screenshot_ocr_edited',
          ocr_transcript_raw: sides[role].ocrText, copied_transcript_raw: sides[role].copied || null,
          tokens: preview.draft!.tokens.map(token => ({ index: token.index, surface: token.surface,
            color: token.candidate_color, color_review_status: token.candidate_color === 'unknown' ? 'unreviewed' : 'candidate',
            color_source_screenshot_id: token.candidate_color === 'unknown' ? null : screenshotId })),
          pronunciation_score: score(sides[role].pronunciation, 90), fluency_score: score(sides[role].fluency, 90), content_score: score(sides[role].content, 5) })) }
      const created = await createComparison(body)
      setComparison(created)
      setDrafts(Object.fromEntries(mapped.map(({ role, preview }) => [role, preview.draft])) as Record<Role, Draft>)
      await Promise.allSettled(mapped.map(({ role, screenshotId }) => importScreenshot(created.samples[role].id, screenshotId)))
      setMessage('已保存截图识别稿和词色候选；候选会参与首次分析。未知词可在下方手动复核。')
    } catch (error) { setMessage(error instanceof Error ? error.message : '保存失败，请重试') }
    finally { setBusy(false) }
  }
  return <div className="space-y-8"><div><p className="eyebrow">新建比较</p><h1 className="page-title">比较同一朗读稿的两份录音</h1><p className="page-subtitle">上传或粘贴两侧猩际截图，先识别转写和词色；复制的猩际转写可选。两侧实际朗读的个别词和尾部可以不同。</p></div>
    {!comparison ? <form onSubmit={submit} className="space-y-6"><div className="panel grid gap-4 sm:grid-cols-2"><label className="text-sm font-medium">题型<input className="field mt-2 w-full" value={questionType} onChange={event => setQuestionType(event.target.value)} required /></label><label className="text-sm font-medium">题目名称或编号（可选）<input className="field mt-2 w-full" value={title} onChange={event => setTitle(event.target.value)} /></label><div className="sm:col-span-2"><PictureInput label="共同原文完整英文朗读稿截图（可选，不能用 DI 图表代替）" file={readingScreenshot} onFile={recognizeReading} /></div><label className="text-sm font-medium sm:col-span-2">两侧计划朗读的共同原文 <span className="text-red-600">*</span><textarea className="field mt-2 min-h-36 w-full resize-y" value={readingText} onChange={event => setReadingText(event.target.value)} placeholder="上传朗读稿截图自动识别，或直接粘贴完整英文朗读稿；提交前可修改" required /></label></div><div className="grid gap-6 lg:grid-cols-2">{(['user', 'benchmark'] as const).map(role => <SampleForm key={role} role={role} value={sides[role]} change={next => setSides(previous => ({ ...previous, [role]: next }))} recognize={file => recognizeSide(role, file)} />)}</div><button className="button-primary" disabled={busy || Object.values(sides).some(side => side.recognizing)}>{busy ? '处理中…' : '保存双边样本与截图候选'}</button></form> : <div className="space-y-6"><p className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800">双边样本已保存。比较编号：{comparison.id}</p>{(['user', 'benchmark'] as const).map(role => <ReviewPanel key={role} record={comparison.samples[role]} draft={drafts[role]} onSaved={next => setComparison(previous => previous && ({ ...previous, samples: { ...previous.samples, [role]: next } }))} />)}<a className="button-primary inline-block" href={`/comparisons/${comparison.id}`}>查看比较</a></div>}
    {message && <p role="status" className="rounded-xl bg-indigo-50 p-4 text-sm text-indigo-800">{message}</p>}
  </div>
}
