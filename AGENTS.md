# PTE Speaking Lab — Agent instructions

## Source of truth

- Read `PROJECT_SPEC.md` for product scope and acceptance criteria before planning or editing.
- Read `ARCHITECTURE.md` for data contracts, pipeline boundaries, persistence, API, and provider design.
- If the documents conflict, preserve the product boundary in `PROJECT_SPEC.md` and flag the specific conflict before changing an interface. Update both documents when an agreed design change affects both.
- Work in this project directory. Keep scratch files out of the repository and do not modify unrelated projects.

## MVP boundaries

- Focus on Pronunciation and Fluency. Store and display Xingji Content scores, but do not implement independent Content scoring, image understanding, or semantic content diagnosis.
- A comparison contains one user `ResponseSample` and one high-score benchmark `ResponseSample`. The benchmark is an example of high performance, not an official answer or scoring standard.
- Preserve source audio, Xingji scores, transcripts, colors, and pause labels. Do not replace source facts with model output.
- Xingji screenshots are the preferred input for observed transcript and word colors. Preserve the original image, OCR draft, optional copied transcript, final edited transcript, source labels, and immutable revisions. Include reliably mapped screenshot colors in the first analysis as low-confidence `candidate`; keep uncertain colors `unknown`. Human confirmation or correction changes the status to `confirmed` without rewriting old reports. Shared reading script screenshots are a separate source and must contain the full intended English text.
- Never label an internally generated result as an official PTE or Xingji score.

## Analysis architecture

- Keep Pronunciation and Fluency pipelines separately runnable and testable. They may share prepared audio, transcript, and timestamp data, but neither engine may depend on the other's result.
- Pronunciation prioritizes Xingji red/yellow words; use shared words only for word-level A/B comparison. Fluency compares timing and delivery metrics even when the two transcripts differ.
- Perform cross-dimension inference only in the Diagnosis Engine, after the independent evidence has been saved. A relationship between a difficult word and a pause is a supported hypothesis, not proven causation.
- Every finding and recommendation must cite stored evidence with source, location, quality, and algorithm/provider version. Missing or unreliable alignment must degrade dependent findings instead of producing guessed timestamps or phoneme claims.
- Bind each analysis run to immutable revisions of both samples so corrections cannot change the meaning of old reports.
- Treat OpenPronounce and other model results as separate signals; do not convert them into Xingji or official scores.

## Implementation and verification

- MVP stack: React, Vite, Tailwind, WaveSurfer; FastAPI, SQLite, local filesystem, and FFmpeg. Keep provider interfaces swappable. Implement OpenAI first; do not present future providers as working.
- For required system software, prefer Homebrew. Install Python and JavaScript project libraries with their project package managers and record versions in lockfiles.
- ChatGPT Plus does not supply an API key. Keep `OPENAI_API_KEY` server-side only; never commit keys, audio, transcripts, or the `data/` directory.
- Preserve original files and store relative paths so the project can move from the M2 development machine to the M5 Pro machine.
- Before finishing a change, run checks that cover the affected behavior, including independent pipeline operation and degraded results when applicable. Report what was verified and any remaining limitation.
- Before copying third-party code, models, or assets, verify the exact version's license and required notices. Echoic is UI reference only; PronounceAI and GOPT are later-phase research references.
