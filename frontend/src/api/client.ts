export type Score = { value: number; max: number }
export type Token = { index: number; surface: string; normalized: string; color: 'red' | 'yellow' | 'green' | 'unknown'; color_review_status: 'confirmed' | 'unreviewed'; color_source_screenshot_id: string | null }
export type Sample = { role: 'user' | 'benchmark'; audio_origin?: 'human_recording' | 'ai_generated' | 'legacy_unspecified'; audio_asset_id: string | null; color_screenshot_asset_ids: string[]; pronunciation_score: Score | null; fluency_score: Score | null; content_score: Score | null; transcript_raw: string | null; transcript_source: 'xingji_copy' | 'manual_correction' | null; tokens: Token[]; pause_labels: { after_token_index: number | null; raw_label: string; review_status: 'confirmed' | 'unreviewed' }[] }
export type SampleRecord = { id: string; version: number; revision_id: string; sample: Sample }
export type Comparison = { id: string; exercise: { question_type: string; title: string | null; reading_text_raw: string | null }; samples: { user: SampleRecord; benchmark: SampleRecord }; created_at: string }
export type DraftToken = { index: number; surface: string; candidate_color: Token['color']; reason: string; bbox: number[] | null; ocr_confidence: number | null }
export type Draft = { tokens: DraftToken[]; candidate_count: number; unknown_count: number; candidate_color_counts: { red: number; yellow: number; green: number }; warnings: string[] }

async function read<T>(pending: Promise<Response>): Promise<T> {
  const response = await pending
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    throw new Error(typeof detail === 'object' ? detail?.message || detail?.code || `请求失败 ${response.status}` : detail || `请求失败 ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function upload(kind: 'audio' | 'screenshots', file: File): Promise<{ id: string }> {
  const form = new FormData()
  form.append('file', file)
  return read(fetchResponse(`/api/v1/assets/${kind}`, { method: 'POST', body: form }))
}

async function fetchResponse(url: string, init?: RequestInit) { return fetch(url, init) }

export function createComparison(body: unknown) { return read<Comparison>(fetchResponse('/api/v1/comparisons', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })) }
export function getComparison(id: string) { return read<Comparison>(fetchResponse(`/api/v1/comparisons/${id}`)) }
export function getHistory() { return read<{ id: string; created_at: string; question_type: string; title: string | null }[]>(fetchResponse('/api/v1/history')) }
export function previewDeletion(id: string) { return read<{ sample_count: number; run_count: number; audio_file_count: number; screenshot_file_count: number; preserved_shared_assets: number; files: string[] }>(fetchResponse(`/api/v1/comparisons/${id}/deletion-preview`)) }
export function deleteComparison(id: string) { return read<{ deleted: boolean; file_cleanup_pending: string[] }>(fetchResponse(`/api/v1/comparisons/${id}`, { method: 'DELETE' })) }
export function importScreenshot(sampleId: string, screenshotId: string) { return read<{ id: string; draft: Draft }>(fetchResponse(`/api/v1/samples/${sampleId}/screenshot-imports`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ screenshot_id: screenshotId }) })) }
export function getImports(sampleId: string) { return read<{ id: string; draft: Draft }[]>(fetchResponse(`/api/v1/samples/${sampleId}/screenshot-imports`)) }
export function updateSample(record: SampleRecord, sample: Sample) { return read<SampleRecord>(fetchResponse(`/api/v1/samples/${record.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_version: record.version, sample }) })) }

export type Metric = { value: number | null; unit: string; quality: string; reason: string | null; details: Record<string, unknown> }
export type Evidence = { id: string; sample_id: string; dimension: string; kind: string; token_index?: number; start_s?: number | null; end_s?: number | null; value: number | null; unit: string | null; quality: string; details: Record<string, unknown> }
export type SideResult = { sample_id: string; sample: Sample; audio: { duration_s: number }; alignment: { status: string; trusted_count?: number; total_count?: number; tokens: { index: number; start_s: number | null; end_s: number | null; quality: string }[] }; pronunciation: { summary: { counts: Record<string, number>; known_count: number; unknown_count: number; ratios: Record<string, number | null> }; targets: { index: number; surface: string; color: string; start_s: number | null; end_s: number | null; evidence_ids: string[] }[]; evidence: Evidence[] }; fluency: { metrics: Record<string, Metric>; evidence: Evidence[]; status: string } }
export type Report = { run_id: string; comparison_id: string; status: string; revision_ids: Record<string, string>; samples: { user: SideResult; benchmark: SideResult }; comparison: { shared_word_pairs: { word: string; user_index: number; benchmark_index: number; user_color: string; benchmark_color: string; evidence_ids: string[] }[]; transcript_comparison?: { basis: string; script_word_count: number | null; user_matched_script_words: number | null; benchmark_matched_script_words: number | null; shared_script_words: number; user_unmatched_transcript_words: number; benchmark_unmatched_transcript_words: number; user_script_tail_unobserved: number | null; benchmark_script_tail_unobserved: number | null; limitation: string }; fluency_metric_differences: Record<string, { user: Metric; benchmark: Metric; delta_user_minus_benchmark: number | null; quality: string }> }; diagnosis: { llm_status: string; findings: { id: string; kind: string; statement: string; recommendation: string; evidence_ids: string[]; confidence_level: string; limitations: string[] }[] } }
export function startRun(comparisonId: string, options: { allow_cloud: boolean; use_openpronounce: boolean }) { return read<{ run_id: string; status: string }>(fetchResponse(`/api/v1/comparisons/${comparisonId}/runs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options) })) }
export function listRuns(comparisonId: string) { return read<{ id: string; status: string; started_at: string }[]>(fetchResponse(`/api/v1/comparisons/${comparisonId}/runs`)) }
export function getReport(runId: string) { return read<Report>(fetchResponse(`/api/v1/runs/${runId}/report`)) }
export function getProviders() { return read<{ alignment: string; pronunciation: string; llm: string; openai_model: string | null; openai_key_configured: boolean; cloud_requires_explicit_run_choice: boolean }>(fetchResponse('/api/v1/settings/providers')) }
