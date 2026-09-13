# F.R.E.D. (Fairly Reliable Engine Doing Deeds) — Problem Statement

## The Core Problem

Modern, cloud-based AI assistants require users to trade data privacy for utility. While they can automate tasks and retrieve information, they operate as "black boxes" that hide their reasoning, process highly personal data on remote servers, and often execute actions without sufficient user oversight. Furthermore, these systems lack deep, specialized context regarding a user's local knowledge base and cannot dynamically self-correct or ask for clarification when their confidence is low.

## Key Challenges & Limitations of Current Systems

- **Privacy, Cost & Latency:** Relying on commercial APIs exposes private administrative data (calendars, emails, messages) to third-party servers, introduces recurring per-call costs, and requires an internet dependency for every request — including ones that don't actually need external data — introducing avoidable latency in voice-activated commands.
- **Execution Risk:** Standard assistants lack strict Human-in-the-Loop (HITL) architecture, risking accidental transmission of unapproved emails or incorrect calendar modifications.
- **Opaque Reasoning:** Cloud LLMs do not expose their internal logic or confidence thresholds, making it impossible for the user to trust the decision-making process before an action is taken.
- **Static Memory:** Existing Retrieval-Augmented Generation systems typically act as static search engines for a fixed document set, rather than dynamic, agentic memories that can supplement local knowledge with live web search only when genuinely needed.

## The Proposed Solution

F.R.E.D. (Fairly Reliable Engine Doing Deeds) is a local-first, voice-activated intelligent agent designed to prioritize privacy, transparency, and user control, at zero recurring inference cost. All private data classes and reasoning stay on-device by default; the reasoning model may invoke web search as an explicit, logged tool only when it determines local knowledge is insufficient to answer confidently. Orchestrated within a lightweight, high-performance Python environment, the system provides hands-free automation for drafting communications, summarizing documents, managing schedules, and answering questions about the user's personal financial data.

## System Design: Constraints

_Constraints define the boundaries the system may not cross, regardless of the specific feature being executed. These are verified by architectural audit, not by test case._

- **Local-first execution for all private data classes.** Voice audio, personal documents, calendar/email/Telegram content, and financial records stay on-device by default. All inference (STT, reasoning, TTS) runs on local models, which also eliminates recurring API costs — a primary motivation alongside privacy. The sole exception is reasoning-gated web search (see Functional Requirements below), which is an explicit, logged tool call, not a default data path.
- **No file system write access.** F.R.E.D. can read and reason over local files (documents, financial exports) but has no ability to create, modify, or delete any file. Any suggested change to a file is presented to the user as a proposal only — the user makes the edit themselves.
- **No unsupervised external write actions.** F.R.E.D. may draft emails, messages, and calendar events, but every write action (sending, scheduling, modifying) requires explicit user confirmation before execution. No exceptions, no timeout-based auto-approval.
- **Read-only access to Gmail and Telegram.** F.R.E.D. has read access to these two platforms solely to build context for understanding what the user is referring to in conversation (e.g., "reply to what Sarah sent me"). It cannot send, delete, or modify messages on either platform directly — only draft a reply for the user to review and send themselves.
- **Fetched web content is always treated as untrusted data, never as instructions.** Text extracted from any web page is passed to the reasoning model strictly as reference material to summarize/cite — the agent must not execute instructions embedded in page content (a prompt-injection defense that matters more here given F.R.E.D. also has read access to email and messages). No stealth/anti-bot-evasion techniques are used to bypass a site's active blocking of automated access; a blocked fetch fails gracefully rather than being circumvented.

## System Design: Functional Requirements

_Functional requirements describe observable, testable behaviors given a specific input._

- **Transparent Reasoning:** Expose the model's chain-of-thought directly in the UI as text, while translating only the final answer to audio — keeping voice output concise without hiding the reasoning trace from the user.
- **Calibrated Confidence Gating:** Every parsed intent is scored for confidence using a calibrated method (not raw model self-report). If the score falls below a tuned threshold, the agent audibly pauses and prompts the user for clarification rather than guessing.
- **Human-in-the-Loop Approval Flow:** F.R.E.D. may draft emails, replies, calendar events, and proposed file edits, but must present each in full and await explicit user confirmation before any corresponding write action is executed.
- **Reasoning-Gated Web Retrieval:** Web search (via DuckDuckGo) is invoked as an agentic tool only when the reasoning model determines, based on the retrieved local context, that its local knowledge is insufficient to answer confidently — not as a default fallback for every query. Each web search is logged and shown to the user.
- **Web Page Reading, Summarization & Citation:** Given a URL (user-provided, or surfaced by the web search tool), F.R.E.D. fetches the page, extracts its readable content, and summarizes it with citations back to the source. Multi-page exploration is capped at a fixed number of fetches per query (default 3–5 hops) and scoped to the originating domain unless the reasoning model has specific justification to leave it — bounding both cost and the prompt-injection surface rather than allowing open-ended crawling. Every fetch is logged.
- **Bilingual Text Normalization:** All textual input (transcribed voice, read messages) passes through a dedicated normalization stage before intent parsing. This stage expands informal shorthand and internet slang (e.g., "u," "gt," "lol") to canonical form and handles English/Chinese bilingual content — including code-switched text — via a retrieval-based lookup against a maintained slang/abbreviation index, rather than relying on the reasoning model to interpret shorthand implicitly. See Architecture Note below.
- **Financial Data Query:** F.R.E.D. can answer natural-language questions about the user's personal finances (spending by category, trends over time, budget adherence) by reasoning over local exports (CSV/OFX from banking or budgeting apps) — never via a live brokerage/bank API connection, keeping this data class local by construction, matching the same architecture as the document RAG system.

## Evaluation & Success Metrics

_Chosen to test the parts of the system most likely to fail silently: intent understanding, agent decision quality, and answer faithfulness._

- **Speech/Intent Understanding — Precision & Recall:** For a labeled test set of voice commands, measure precision and recall of correctly extracted intent + slots (e.g., correct recipient, correct date) before the parse is passed to the reasoning model. This isolates STT + NLU quality from downstream LLM reasoning quality — if this stage is weak, no amount of reasoning-model quality fixes it.
- **LLM-as-a-Judge:** A separate local model (or the same model in a distinct evaluation pass) scores final responses against the retrieved context for faithfulness/groundedness, and against the original query for relevance and completeness — catching answers that sound confident but drift from the source material.
- **Trajectory@k:** For agentic decisions (e.g., "should I search the web," "which tool to call"), sample the agent's reasoning-and-action trajectory k times per test case and measure how often the correct tool-call sequence is reached across samples. This surfaces trajectory-level inconsistency that a single-pass evaluation would miss — analogous to pass@k in code-generation evaluation, but applied to the agent's decision path rather than a final code output.
- **HITL Integrity:** Across all test sessions, zero write actions (email send, calendar write, message send) occur without a logged, explicit user approval — an audit-log-verified metric rather than a sampled one, since a single silent failure here is disqualifying regardless of overall rate.

## Feature Set

**Core:**

1. Calendar access (read + propose write, HITL-gated)
2. Draft email and message replies (read context from Gmail/Telegram, HITL-gated send)
3. Financial data query over local exports
4. Bilingual (English/Chinese) slang and shorthand normalization pipeline, upstream of the reasoning model
5. Web page reading, summarization, and citation (hop-capped, domain-scoped, logged)

## Architecture Note: Text Normalization Layer

Rather than a general-purpose neural translation model handling both language conversion and slang interpretation in one opaque step (harder to debug, harder to keep deterministic for a "transparent reasoning" system), this is split into two explicit, inspectable stages between STT/message-read and intent parsing:

1. **Language identification** — lightweight local classifier (e.g., fastText `lid.176`) tags each input segment as English, Chinese, or code-switched (both present, common in Singlish-style messages).
2. **Retrieval-based slang/shorthand expansion** — an indexed dictionary (same ChromaDB pattern used elsewhere in the project) of known shorthand → canonical-form mappings, covering both English internet slang ("u" → "you," "gt" → "got," "lol" → "laughing out loud") and Chinese internet slang ("666" → "impressive," "yyds" → "the best of all time"). Unrecognized tokens are matched via nearest-neighbour lookup against the index rather than left unexpanded, and the index is straightforward to extend as new shorthand appears.
3. **Translation to a working language** (only if needed) — a small local MT model (e.g., a distilled NLLB-200 or MarianMT en↔zh checkpoint) converts non-English segments to English before the normalized text reaches the reasoning model, keeping intent parsing single-language internally.

This keeps the normalization step itself auditable — you can log exactly which shorthand got expanded to what, which matters for a "transparent reasoning" system and would be lost if this were folded into one black-box translation call.

**Extensions (see companion architecture doc for phasing):**

- Daily voice briefing (calendar + email triage + weather)
- Meeting transcription → action-item extraction
- Semantic local file search across full document store
- Spaced-repetition study quiz mode over notes corpus
