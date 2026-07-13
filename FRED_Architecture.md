# F.R.E.D. (Fairly Reliable Engine Doing Deeds) — Technical Architecture & Build Plan

## 0. Reality check before architecture

Your problem statement makes four hard promises that are in tension with each other, and naming the tension up front will make you look sharper in an interview than pretending it doesn't exist:

1. **"100% local" vs. "chain-of-thought quality + reliable confidence scores."** Small local models (7B–14B, which is what most laptops can run) are noticeably worse than cloud frontier models at two exact things your spec requires: faithful chain-of-thought and calibrated confidence estimates. This is solvable, but it needs deliberate engineering (below), not just "call the local model and ask for a confidence score."
2. **Web retrieval is now scoped, not contradictory.** The spec is local-first, not local-only: private data (voice, documents, calendar/Gmail/Telegram content, financial records) never leaves the device, and web access (search + page reading) is an explicit, logged, reasoning-gated tool for non-private queries — capped in scope (hop limits, domain scoping) so it stays a bounded exception rather than an open-ended dependency.
3. **Latency.** Local STT→LLM→TTS on consumer hardware without a GPU will feel noticeably slower than cloud voice assistants. Worth benchmarking early and setting expectations rather than discovering it in week 6.
4. **Hardware determines everything.** Model choice, quantization, and whether "chain-of-thought exposed in real time" is even latency-feasible all depend on what you're running on (Apple Silicon unified memory, discrete NVIDIA GPU, or CPU-only). I don't know your hardware — the plan below covers three tiers, but tell me your specs and I'll tighten this to one.

## 1. High-level architecture

```
                    ┌─────────────────────────────────────────┐
                    │              LOCAL MACHINE                │
                    │                                           │
 [Mic] → local STT ─┤→ Intent Parser (structured output) ─┐    │
                    │         │                            │    │
                    │    confidence score                  │    │
                    │         │                            │    │
                    │   ┌─────┴─────┐                       │    │
                    │   │ < threshold│──► "Ask for          │    │
                    │   │            │     clarification"   │    │
                    │   │ ≥ threshold│                       │    │
                    │   └─────┬─────┘                       │    │
                    │         ▼                             ▼    │
                    │   LangGraph orchestrator ◄── Local RAG      │
                    │   (state machine)             (ChromaDB)    │
                    │         │                       │           │
                    │         ├── needs current info? ─┴─► DuckDuckGo (only external hop)
                    │         │
                    │         ▼
                    │   Action classified:
                    │   ┌───────────────┬──────────────────┐
                    │   │  Read-only /   │  Write action     │
                    │   │  informational │  (email/calendar) │
                    │   └───────┬───────┴─────────┬─────────┘
                    │           │                  │
                    │           ▼                  ▼
                    │      Speak answer      DRAFT ONLY, shown
                    │      (local TTS)        in UI + spoken summary
                    │                         → await explicit
                    │                           "confirm" before
                    │                           any API write call
                    └───────────────────────────────────────────┘
```

The key structural decision: **the LangGraph graph has a hardcoded, unconditional edge before any node that performs a write.** Not a prompt instruction telling the model to ask permission — an actual graph edge that always routes to a `human_approval` node with no bypass. This is what makes HITL "strict" rather than "the model usually asks."

## 2. Component-by-component

### 2.1 Speech-to-Text (local)

- **`faster-whisper`** (CTranslate2-optimized Whisper) — best default. `small.en` or `medium.en` for CPU-only machines, `large-v3` if you have a GPU with ≥6GB VRAM to spare.
- Alternative: `whisper.cpp` if you want a pure C++ binary with no Python dependency for this stage — useful if you later want a system-tray-style always-listening daemon.
- Wake-word detection (so it's not always transcribing): `openWakeWord` or `Porcupine` (free tier) sitting in front of Whisper so STT only fires after "Hey F.R.E.D.."

### 2.2 Local LLM inference

Run via **Ollama** (simplest, good enough control) or **llama.cpp** directly (more control over sampling/grammars, matters for your confidence-gate requirement).

Model choice by hardware tier:
| Hardware | Model | Notes |
|---|---|---|
| CPU-only / 8-16GB RAM | Qwen2.5-7B-Instruct (Q4_K_M) or Llama-3.1-8B-Instruct (Q4) | Usable but slow (~5-15 tok/s); fine for demo, not snappy |
| Apple Silicon (M-series, 16GB+ unified) | Qwen2.5-14B or Llama-3.1-8B at Q5/Q6 | MLX runtime (`mlx-lm`) outperforms llama.cpp on Apple Silicon specifically |
| Discrete GPU (8GB+ VRAM) | Qwen2.5-14B-Instruct or Mistral-Small-24B (quantized to fit VRAM) | Best quality-to-latency ratio of the three tiers |

Qwen2.5/3-series models are specifically worth prioritizing over Llama here — they're noticeably stronger at structured JSON output and instruction-following at equivalent size, which matters a lot for your confidence-gate mechanism.

### 2.3 Structured output & confidence gating (the hard part)

Don't ask the model to "output a confidence score" in free text — small models hallucinate plausible-looking numbers with no actual calibration to them. Instead:

1. **Constrain the output schema** using grammar-constrained decoding (`llama.cpp` GBNF grammars, or the `outlines` / `instructor` Python libraries on top of Ollama). Force the model to emit:

```json
{
  "intent": "draft_email | schedule_event | summarize_doc | general_query | ...",
  "parsed_slots": { "recipient": "...", "subject": "...", "date": "..." },
  "confidence": 0.0,
  "reasoning": "short chain-of-thought string, shown in UI"
}
```

2. **Calibrate the confidence signal properly**, since raw model-reported confidence is weak. Two approaches, use both:
   - _Self-consistency_: sample the intent-parse 3x at temperature 0.7, use agreement rate across samples as the actual confidence score (if 3/3 agree on intent+slots → high confidence; if they diverge → genuinely low, route to clarification). This is far more trustworthy than a single model-reported number.
   - _Slot completeness as a hard signal_: if a required slot (e.g. recipient for an email) is null/empty, that's a deterministic low-confidence trigger regardless of what the model reports — don't rely on the LLM to notice its own gaps.
3. Set your threshold empirically once you have test data — start at "if self-consistency agreement < 2/3, clarify" and tune from there.

### 2.4 Text-to-Speech (local)

- **Piper** — fast, fully local, ONNX-based, good enough quality, runs comfortably on CPU. Best default for a hands-free assistant.
- **Kokoro-82M** — newer, notably better prosody than Piper for similar speed, worth A/B testing if quality matters more than raw speed to you.
- Feed only the **final answer** to TTS, not the reasoning trace — reasoning stays visible in the UI as text (satisfies "transparent decision-making") without bloating what gets spoken, which is exactly the pattern that avoids the truncation problem from your earlier Gemini-clone project.

### 2.5 Agentic memory

- Local vector store: **ChromaDB** (you've already worked with this — reuse the pattern from your MOE exam tool and Mandai RAG project) for your document corpus.
- Retrieval routing node in the LangGraph graph decides: _local doc search_ vs. _web search_ vs. _both_, based on a classification step ("is this asking about something in my local knowledge base, something current/live, or ambiguous?"). This is the "dynamic" part — not a static single-index RAG lookup, but a routed decision per query.
- Web search tool: DuckDuckGo's HTML search (no API key needed, `duckduckgo-search` Python package) — keep this as an explicit, logged, user-visible step ("F.R.E.D. searched the web for: ...") rather than a silent fallback, which reinforces your transparency goal.

### 2.6 Bilingual text normalization

- **Language ID**: fastText `lid.176` (lightweight, local) tags each input segment as English, Chinese, or code-switched — common in Singlish-style messages.
- **Slang/shorthand expansion**: retrieval-based lookup against a ChromaDB-indexed dictionary of shorthand → canonical form (English internet slang: "u," "gt," "lol"; Chinese internet slang: "666," "yyds"). Unrecognized tokens get nearest-neighbour matched against the index rather than passed through unexpanded.
- **Translation**: a small local MT model (distilled NLLB-200, e.g. `nllb-200-distilled-600M`, or a MarianMT `opus-mt-zh-en` checkpoint) converts non-English segments to English before intent parsing, so the reasoning model only ever sees single-language input.
- This sits as its own node in the LangGraph graph, between STT/message-read and the intent parser — keep it a separate, inspectable stage rather than folding it into the LLM prompt, so exactly which shorthand got expanded to what stays logged and auditable.

### 2.7 Web page reading & rendering

Two-tier fetch strategy, to keep the common case cheap and only pay for a full browser when actually needed:

1. **Tier 1 (static)**: plain `requests` GET → `trafilatura.extract()` for clean article text. Handles the majority of content sites.
2. **Tier 2 (JS-rendered fallback)**: if Tier 1 returns suspiciously little content (heuristic: <500 chars), fall back to **Playwright** (chosen over Selenium/Puppeteer — native async Python API fits directly into a LangGraph tool call, faster and more reliable than Selenium, and avoids introducing a Node-first tool into an otherwise Python stack):
   - `page.goto(url, wait_until="networkidle")` for standard JS-rendered content.
   - Scripted scroll loop for infinite-scroll/lazy-loaded pages.
   - `page.wait_for_selector(...)` for content that mounts without triggering new network activity.
   - Block image/font resource types via `page.route(...)` to keep fetches fast — only the DOM/text is needed.
   - Reuse a single browser instance across a session rather than relaunching per fetch.
   - Hand the rendered `page.content()` HTML to trafilatura for extraction, same as Tier 1.

**Constraints enforced in the graph, not just prompted:**

- Hard cap on fetches per query (default 3–5 hops), domain-scoped by default.
- Fetched page content is passed to the reasoning model strictly as data to summarize/cite — never treated as instructions. This matters specifically because F.R.E.D. also has read access to Gmail/Telegram, which raises the stakes of a prompt-injection payload embedded in a fetched page.
- No stealth/anti-bot-evasion (e.g. `playwright-stealth`) — a blocked fetch fails gracefully and is reported to the user, not circumvented.
- Every fetch (URL, tier used, hop count) is logged, same as the existing web-search logging.

### 2.8 Human-in-the-loop execution layer

- Any node that would call an external write API (Gmail send, Calendar insert/update) is preceded by a **non-optional** `human_approval` node in the graph.
- UI shows the drafted action in full (not a summary) before the confirm button is live — no auto-confirm, no timeout-based auto-approval.
- Log every approval/rejection locally (SQLite is enough) — gives you an audit trail, which is also a nice thing to point to in an interview as evidence of the HITL claim being real, not decorative.

## 3. Suggested stack summary

| Layer                 | Choice                                                                                                            |
| --------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Orchestration         | LangGraph (state machine, confidence-gated routing — you've used this pattern before)                             |
| STT                   | faster-whisper + openWakeWord                                                                                     |
| LLM runtime           | Ollama or llama.cpp, Qwen2.5-Instruct family                                                                      |
| Structured output     | `outlines` or `instructor` + GBNF grammar constraints                                                             |
| TTS                   | Piper (or Kokoro-82M)                                                                                             |
| Vector DB             | ChromaDB                                                                                                          |
| Web search            | duckduckgo-search                                                                                                 |
| Web page fetch/render | `requests` + `trafilatura` (static), Playwright (JS-rendered fallback)                                            |
| Text normalization    | fastText `lid.176`, ChromaDB slang index, distilled NLLB-200 or MarianMT (en↔zh)                                  |
| Write-action APIs     | Google Calendar API / Gmail API / Telegram client API (Telethon), OAuth, but data flow only happens post-approval |
| Approval/audit log    | SQLite                                                                                                            |
| UI                    | Local web app (FastAPI + a lightweight frontend) showing live transcript, reasoning trace, and pending approvals  |

## 4. Phased roadmap

1. **Phase 1 — Core loop, text-only.** Wake-word skipped for now, type input instead. Get intent parsing + confidence gating + LangGraph routing working end-to-end on text before adding audio at all. This is where the hardest engineering (structured confidence calibration) gets debugged fastest.
2. **Phase 2 — Add STT/TTS.** Wire in faster-whisper and Piper around the working text pipeline. Measure real end-to-end latency here — this is your reality check on the "voice-activated" promise.
3. **Phase 3 — RAG + web search + web page reading.** Local ChromaDB corpus first, then the routed web-search fallback, then the two-tier page-fetch tool (static → Playwright) on top of it — test against pages you know are JS-rendered early, since that's where the fallback logic actually gets exercised.
4. **Phase 4 — Bilingual normalization layer.** Add language ID + slang-index expansion + translation as its own graph node upstream of intent parsing. Test against your own real Telegram history early — code-switched Singlish-style messages are the hard case and worth surfacing before the rest of the system is built around clean input assumptions.
5. **Phase 5 — Write-action integrations + HITL.** Gmail/Calendar/Telegram-read API integration, draft-then-approve flow, audit logging. Do this last and deliberately — it's the highest-risk-if-wrong component, so build it once the rest is stable.
6. **Phase 6 — Polish.** Wake-word always-listening mode, UI for the reasoning trace, latency optimization (quantization tuning, streaming TTS to reduce perceived latency).

## 5. Open question that changes tier-specific recommendations

Your hardware (CPU-only laptop vs. Apple Silicon vs. discrete GPU, and how much RAM/VRAM) determines which model size is actually usable at acceptable latency. Happy to lock in a specific model + quantization recommendation once you share that.
