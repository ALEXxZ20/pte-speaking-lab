import { useEffect, useState, type FormEvent } from 'react'
import { createComparison, generateTTS, getTTSSettings, importScreenshot, previewScreenshot, previewTTSSegments, upload, type Comparison, type Draft, type TTSSettings } from '../api/client'
import { empty, PictureInput, ReviewPanel, SampleForm, type FormSide } from './NewComparison'

export default function NewTTSComparison() {
  const [title, setTitle] = useState('')
  const [questionType, setQuestionType] = useState('DI')
  const [readingText, setReadingText] = useState('')
  const [readingOcr, setReadingOcr] = useState('')
  const [readingScreenshot, setReadingScreenshot] = useState<File | null>(null)
  const [readingScreenshotId, setReadingScreenshotId] = useState<string | null>(null)
  const [segments, setSegments] = useState<string[]>([])
  const [side, setSide] = useState<FormSide>(empty)
  const [settings, setSettings] = useState<TTSSettings | null>(null)
  const [voice, setVoice] = useState('en-US-AriaNeural')
  const [rate, setRate] = useState('+0%')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => { getTTSSettings().then(value => { setSettings(value); setVoice(value.default_voice); setRate(value.default_rate) }).catch(error => setMessage(String(error))) }, [])
  async function recognizeReading(file: File) {
    setReadingScreenshot(file); setReadingScreenshotId(null); setMessage('正在识别朗读稿…')
    try {
      const asset = await upload('screenshots', file)
      const result = await previewScreenshot(asset.id, 'reading_script')
      setReadingScreenshotId(asset.id); setReadingOcr(result.text); setReadingText(result.text); setSegments([])
      setMessage(`已识别 ${result.word_count} 词；请先核对原稿，再预览断句。`)
    } catch (error) { setMessage(`朗读稿识别失败：${String(error)}`) }
  }
  async function recognizeUser(file: File) {
    setSide(previous => ({ ...previous, screenshot: file, screenshotId: null, draft: null, recognizing: true }))
    try {
      const asset = await upload('screenshots', file)
      const result = await previewScreenshot(asset.id, 'xingji')
      setSide(previous => ({ ...previous, screenshotId: asset.id, ocrText: result.text, transcript: result.text, draft: result.draft, recognizing: false }))
    } catch (error) { setSide(previous => ({ ...previous, recognizing: false })); setMessage(`我的截图识别失败：${String(error)}`) }
  }
  async function split() {
    try { setSegments((await previewTTSSegments(readingText)).segments); setMessage('请检查断句；可逐段修改生成时朗读的文字。') }
    catch (error) { setMessage(`断句失败：${String(error)}`) }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!side.audio || !side.screenshotId || !side.transcript.trim() || !side.pronunciation || !side.fluency || !side.content || !segments.length || segments.some(item => !item.trim())) {
      setMessage('请填写我的录音、猩际截图和三项分数，并预览及检查朗读分段。'); return
    }
    setBusy(true); setMessage('正在生成练习参考录音，随后保存双边样本；在线服务可能需要几十秒…')
    try {
      // 生成结果返回最终文本与词时间；以服务器保存的文本为唯一参考脚本。
      const generated = await generateTTS(segments, voice, rate)
      const [audio, preview] = await Promise.all([upload('audio', side.audio), previewScreenshot(side.screenshotId, 'xingji', side.transcript)])
      const sample = { role: 'user', audio_origin: 'human_recording', audio_asset_id: audio.id,
        color_screenshot_asset_ids: [side.screenshotId], transcript_raw: side.transcript,
        transcript_source: side.transcript === side.ocrText ? 'screenshot_ocr' : 'screenshot_ocr_edited',
        ocr_transcript_raw: side.ocrText, copied_transcript_raw: side.copied || null,
        tokens: preview.draft!.tokens.map(token => ({ index: token.index, surface: token.surface,
          color: token.candidate_color, color_review_status: token.candidate_color === 'unknown' ? 'unreviewed' : 'candidate',
          color_source_screenshot_id: token.candidate_color === 'unknown' ? null : side.screenshotId })),
        pronunciation_score: { value: Number(side.pronunciation), max: 90 }, fluency_score: { value: Number(side.fluency), max: 90 }, content_score: { value: Number(side.content), max: 5 } }
      const saved = await createComparison({ exercise: { question_type: questionType, title: title || null,
        reading_text_raw: generated.text, reading_text_source: readingScreenshotId ? generated.text === readingOcr ? 'screenshot_ocr' : 'screenshot_ocr_edited' : 'manual',
        reading_text_ocr_raw: readingScreenshotId ? readingOcr : null, reading_screenshot_asset_id: readingScreenshotId },
        samples: [sample, { role: 'benchmark', audio_origin: 'edge_tts', audio_asset_id: generated.audio_asset_id,
          color_screenshot_asset_ids: [], transcript_raw: generated.text, transcript_source: 'tts_script', tokens: [],
          pronunciation_score: null, fluency_score: null, content_score: null, pause_labels: [] }] })
      setComparison(saved); setDraft(preview.draft)
      await importScreenshot(saved.samples.user.id, side.screenshotId).catch(() => undefined)
      setMessage(`已保存；参考录音包含 ${generated.word_boundaries.length} 个词时间事件、${generated.seam_intervals.length} 处分段接缝。`)
    } catch (error) { setMessage(`创建失败：${String(error)}。已输入的内容仍在页面中，可重试。`) }
    finally { setBusy(false) }
  }
  return <div className="space-y-7"><div><p className="eyebrow text-teal-700">TTS 练习参考</p><h1 className="page-title">用朗读稿生成参考录音</h1><p className="page-subtitle">上传你的猩际录音和反馈，在线生成同稿朗读。参考录音没有猩际分数或词色。</p></div>
    {!comparison ? <form onSubmit={submit} className="space-y-6"><section className="panel space-y-4"><div className="grid gap-4 sm:grid-cols-2"><label>题型<input className="field mt-2 w-full" value={questionType} onChange={event => setQuestionType(event.target.value)} required /></label><label>题目名称或编号<input className="field mt-2 w-full" value={title} onChange={event => setTitle(event.target.value)} /></label></div><PictureInput label="完整英文朗读稿截图（可选）" file={readingScreenshot} onFile={recognizeReading} /><label className="block">计划朗读的原文<textarea className="field mt-2 min-h-40 w-full" value={readingText} onChange={event => { setReadingText(event.target.value); setSegments([]) }} required /></label><button type="button" className="button-secondary" onClick={split} disabled={!readingText.trim()}>预览断句</button>
      {!!segments.length && <div className="space-y-2"><h2 className="font-semibold">生成前核对断句与文字</h2><p className="text-sm text-slate-600">生成时会把这些段落依次朗读并拼接；分段边界至少保留约 {settings?.gap_ms ?? 300} ms 的首尾安静区，不足才补静音。请修正 OCR 误字和不自然的断句。</p>{segments.map((segment, index) => <label key={index} className="block text-sm">第 {index + 1} 段<textarea className="field mt-1 min-h-20 w-full" value={segment} onChange={event => setSegments(previous => previous.map((part, i) => i === index ? event.target.value : part))} /></label>)}</div>}
      <div className="flex flex-wrap gap-4"><label>英语音色<select className="field mt-2 block" value={voice} onChange={event => setVoice(event.target.value)}>{settings?.voices.map(item => <option key={item}>{item}</option>)}</select></label><label>语速<select className="field mt-2 block" value={rate} onChange={event => setRate(event.target.value)}>{['-20%', '-10%', '+0%', '+10%', '+20%'].map(item => <option key={item}>{item}</option>)}</select></label></div><p className="rounded-lg bg-teal-50 p-3 text-sm text-teal-900">{settings?.notice || '朗读文本会发送到在线语音服务。'}</p></section>
      <SampleForm role="user" value={side} change={setSide} recognize={recognizeUser} /><button className="rounded-xl bg-teal-700 px-5 py-3 font-semibold text-white disabled:opacity-50" disabled={busy || !settings?.enabled || side.recognizing}>{busy ? '正在生成并保存…' : '生成参考并保存比较'}</button></form> : <div className="space-y-5"><p className="rounded-xl bg-teal-50 p-4 text-teal-900">比较已保存：{comparison.id}</p><ReviewPanel record={comparison.samples.user} draft={draft} onSaved={next => setComparison(previous => previous && ({ ...previous, samples: { ...previous.samples, user: next } }))} /><a className="button-primary inline-block" href={`/comparisons/${comparison.id}`}>查看比较与分析</a></div>}
    {message && <p role="status" className="rounded-xl bg-indigo-50 p-4 text-sm text-indigo-800">{message}</p>}</div>
}
