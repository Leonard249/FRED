# F.R.E.D. (Fairly Reliable Engine Doing Deeds)

_A privacy-first, local-first multimodal assistant & agentic workspace for Apple Silicon._

---

## 0. Reality Check & Core Architectural Invariants

F.R.E.D. operates under strict design tensions that dictate every engineering trade-off:

1. **"100% Local Inference" vs. "Chain-of-Thought Quality & Calibrated Confidence":**  
   Small local models (7B–14B) struggle with faithful chain-of-thought traces and calibrated self-reported confidence. Rather than trusting self-reported numbers, F.R.E.D. enforces grammar-constrained schemas and multi-sample self-consistency checks.
2. **The 24 GB Unified Memory Ceiling & Dynamic Model Swapping:**  
   On an M4 Mac with 24 GB unified RAM, holding three 8B models (Supervisor, Coder, Vision) in memory concurrently requires 23–27 GB (including macOS and KV caches), triggering severe SSD swap-thrashing. F.R.E.D. resolves this via **Just-In-Time (JIT) Model Swapping** and Metal cache flushing.
3. **Local-First, Scoped Web Access:**  
   Private data (voice audio, personal documents, calendar, Gmail, Telegram, financial exports) never leaves the local machine. External web retrieval (DuckDuckGo or Tavily) is reasoning-gated, domain-scoped, hop-capped (3–5 hops), and logged as an explicit tool call.
4. **Architectural Invariant — Non-Bypassable HITL:**  
   The LangGraph state machine enforces an unconditional edge before any node executing an external write (Gmail sending, Calendar modification). The model is architecturally prevented from bypassing user confirmation.
5. **Zero Filesystem Write Permissions:**  
   F.R.E.D. possesses zero direct filesystem write/delete access. Workspace code modifications are strictly emitted as proposed unified diffs for manual review and application.

---

## 1. System Architecture: Modular Pipeline vs. True MAS

F.R.E.D. bridges two operational paradigms depending on user task complexity:

- **Mode A: Event-Driven Modular Dispatch (Default):**  
  Deterministic triggers (CLI startup, image drag-and-drop) directly invoke specialized models without inter-agent deliberation overhead. Keeps latency low and memory footprint lean.
- **Mode B: True Multi-Agent System (MAS) with Actor-Critic Loops:**  
  When high-level tasks demand cross-modal collaboration (e.g., extracting an error screenshot from Gmail, feeding it to Vision, dispatching a patch task to Coder, and validating via test execution), models communicate using an **Agent2Agent (A2A)** JSON schema with a hard cap of 2 refinement iterations.

```text
                    ┌────────────────────────────────────────────────────────┐
                    │                 MACBOOK PRO M4 (24 GB)                 │
                    │                                                        │
 [Voice/Text/Image]─┤► Multi-Interface Entrypoint (--cli, --web, --app)      │
                    │         │                                              │
                    │         ▼                                              │
                    │ Bilingual Normalization (fastText + Slang Index)       │
                    │         │                                              │
                    │         ▼                                              │
                    │ 👑 SUPERVISOR AGENT (Qwen3-8B-DWQ via mlx-lm)          │
                    │ Intent Parser, Confidence Gate & LangGraph Router      │
                    │   ├── < threshold ──► Ask for clarification            │
                    │   └── ≥ threshold ──► Route to Specialist/Tool         │
                    │         │                                              │
                    │   ┌─────┼─────────────────────┬────────────────────┐   │
                    │   ▼     ▼                     ▼                    ▼   │
                    │ 👁️ VISION AGENT         💻 CODER AGENT      🌐 SEARCH AGENT │
                    │ (Qwen3-VL-8B/4B)       (Qwen3-Coder via MLX)(Tavily/DDG)   │
                    │ JIT loaded on image    JIT loaded on diff   Current info,  │
                    │ analysis               request              Page retrieval │
                    │   │     │                     │                    │   │
                    │   └─────┴─────────┬───────────┴────────────────────┘   │
                    │                   ▼                                    │
                    │     Action Routing & Classification                    │
                    │       ├── Read-Only / Informational                    │
                    │       │     ├── Stream to CLI / Web App                │
                    │       │     └── Local TTS (Piper / Kokoro-82M)         │
                    │       │                                                │
                    │       └── External Write Actions (Send / Schedule)     │
                    │             │                                          │
                    │             ▼                                          │
                    │       [NON-BYPASSABLE HITL APPROVAL NODE]              │
                    │       Shows complete draft in UI/CLI                   │
                    │       Requires explicit "confirm" before API execution │
                    └────────────────────────────────────────────────────────┘

```

---

## 2. Memory Budget & Dynamic Model Swapping (24 GB M4)

### 2.1 RAM Budget Breakdown

| Component                                      | RAM Footprint | Lifecycle                                |
| ---------------------------------------------- | ------------- | ---------------------------------------- |
| **macOS & System WindowServer**                | ~4.5 – 5.5 GB | Permanent                                |
| **Supervisor (`Qwen3-8B-DWQ` 4-bit)**          | ~5.2 GB       | Permanent Resident                       |
| **STT / TTS / ChromaDB**                       | ~1.2 – 1.5 GB | Resident / Standby                       |
| **Active Specialist Worker (Coder or Vision)** | ~4.5 – 6.5 GB | JIT Loaded (Evicted when task completes) |
| **Dynamic Headroom & KV Caches**               | ~5.5 – 7.5 GB | Safety buffer against SSD swapping       |

### 2.2 Memory Optimization Strategies

1. **Explicit Metal Cache Eviction:** Python's garbage collector does not automatically release Metal allocations. On specialist unloads, F.R.E.D. executes:

```python
del active_worker
gc.collect()
mlx.core.metal.clear_cache()

```

2. **Quantized KV Caches:** All inference runtimes enable `--kv-bits 4` to shrink KV cache footprints by up to 75% on large context windows.
3. **Context Length Caps:** The resident Supervisor is capped at an 8k context window, reserving wider 32k–64k allocations strictly for the Coder agent during repository traversal.
4. **Lightweight Vision Alternative:** Option to run `Qwen3-VL-4B` (~2.2 GB), allowing both Supervisor and Vision models to stay co-resident in RAM simultaneously.

---

## 3. Omnichannel Interfaces

F.R.E.D. dynamically boots into different modes depending on launch flags:

- **CLI Mode (`uv run fred.py --mode cli`):** Claude Code-style terminal environment powered by `rich`. Supports streaming reasoning traces, Markdown-rendered syntax blocks, interactive diff reviews, and optional voice toggle.
- **Web Mode (`uv run fred.py --mode web`):** Local Gradio web interface featuring drag-and-drop image uploads for screenshots, UI mocks, and error captures.
- **App Mode (`uv run fred.py --mode app`):** Lightweight local desktop wrapper (Tauri) pointing to the local backend, allowing persistent docking on macOS.

---

## 4. Tool Definitions & Constraints

### Personal Communications & Context

- `read_gmail_inbox` / `get_email_thread`: Read-only OAuth2 scope (`gmail.readonly`) to inspect messages and unread threads.
- `read_calendar_events`: Read-only Google Calendar API access to inspect upcoming agendas and check conflicts.
- `read_telegram_messages`: Read-only context extraction via Telethon.
- `draft_communication` / `propose_calendar_event`: Generates draft payloads. Strictly non-executable without passing the HITL approval gate.

### Local Workspace (Claude Code Style)

- `view_file` & `list_directory`: Inspects source files, project structure, and file trees.
- `search_files_grep`: Regex-based file and content searches across the project tree.
- `propose_code_diff`: Produces unified diff proposals. F.R.E.D. cannot write, modify, or delete files directly on disk.
- `execute_safe_command`: Sandboxed read-only terminal execution (`git status`, `git diff`, `pytest`, `python --version`).

### Memory, Data & Scoped Web Access

- `query_local_knowledge`: Vector retrieval over local documents using ChromaDB.
- `query_financial_records`: Local analytics parsing of offline CSV/OFX banking exports.
- `search_web_duckduckgo` / `search_web_tavily`: Logged external search queries with engine toggle.
- `read_web_page`: 2-tier extractor (`trafilatura` static GET → Playwright JS fallback). Capped at 3–5 hops and treated strictly as untrusted data.

---

## 5. Technology Stack Summary

| Layer                     | Technology                                    | Justification                                                  |
| ------------------------- | --------------------------------------------- | -------------------------------------------------------------- |
| **Package Manager**       | `uv`                                          | Deterministic, sub-second dependency management                |
| **Target Hardware**       | Apple Silicon M4 (24 GB Unified RAM)          | High unified memory bandwidth for native MLX execution         |
| **Inference Runtime**     | `mlx-lm` / `mlx-vlm`                          | Native Metal acceleration with dynamic JIT model swapping      |
| **Supervisor Model**      | `Qwen3-8B-DWQ` (4-bit)                        | Permanent resident model for intent parsing and routing        |
| **Vision / Coder Models** | `Qwen3-VL` / `Qwen3-Coder`                    | Dynamically loaded specialist agents                           |
| **Orchestrator**          | LangGraph                                     | State machine with non-bypassable HITL routing                 |
| **UI Suite**              | `rich` (CLI) + `gradio` (Web) + `tauri` (App) | Omnichannel interaction suite                                  |
| **Search Engine**         | DuckDuckGo / Tavily                           | Configurable zero-cost vs. agent-optimized search              |
| **STT / TTS**             | `faster-whisper` + `Piper` / `Kokoro-82M`     | Low-latency local speech pipeline                              |
| **Vector DB**             | ChromaDB                                      | Local on-disk vector store                                     |
| **Auditing & Logs**       | SQLite                                        | Immutable local audit logging for all tool calls and approvals |

---

## 6. Phased Implementation Roadmap

1. **Phase 1 — Single-Agent CLI Core:** Initialize environment with `uv`. Configure `mlx-lm` with Qwen3-8B-DWQ. Build the interactive `rich` CLI and implement LangGraph confidence gating.
2. **Phase 2 — JIT Model Swapping & Workspace Tools:** Implement dynamic model manager (`gc.collect()` + `mx.metal.clear_cache()`). Connect Qwen3-Coder for workspace tools (`view_file`, `grep`, `propose_code_diff`) and Qwen3-VL via `mlx-vlm`.
3. **Phase 3 — UI Modularity:** Abstract frontend logic to support `--cli`, `--web` (Gradio), and `--app` (Tauri wrapper) launch modes.
4. **Phase 4 — Tool Integration (Gmail & Web):** Implement OAuth2 read-only Gmail tools and draft proposals. Wire DuckDuckGo/Tavily search nodes.
5. **Phase 5 — Speech Pipeline:** Integrate `faster-whisper` STT and `Piper` TTS over the core engine. Benchmark latency on the M4 chip.
6. **Phase 6 — Audit & HITL Hardening:** Ensure SQLite logs record all tool executions, and verify that write actions cannot bypass human approval.

---

## 7. F.R.E.D. Project Hierarchy (MCP Integration)

This structure enforces a clean **Separation of Concerns**: UI, AI reasoning, and Tool execution all live in their own dedicated boundaries.

```text
FRED/
├── pyproject.toml              # Managed by `uv` (contains dependencies like mlx, langgraph, rich)
├── README.md                   # Your architectural design document
├── credentials/                # Your OAuth credentials (make sure this is in .gitignore!)
│   ├── credentials.json
│   └── token.json
│
├── mcp_servers/                # 🛠️ THE HANDS: Independent local servers (Model Context Protocol)
│   └── gmail_mcp/
│       ├── __init__.py
│       ├── server.py           # Your read_gmail.py adapted into an MCP Server
│       └── auth.py             # OAuth lifecycle logic
│
└── fred/                       # 🧠 THE BRAIN: Main application package
    ├── __init__.py
    ├── main.py                 # Entrypoint: `uv run fred.py --mode [cli|web|app]`
    │
    ├── core/                   # Orchestration (LangGraph)
    │   ├── graph.py            # Defines the LangGraph Nodes and conditional Edges
    │   ├── state.py            # Defines the shared TypedDict state between agents
    │   └── hitl.py             # Human-in-the-Loop logic and SQLite audit logging
    │
    ├── memory/                 # Memory Management (Cognitive Hierarchy)
    │   ├── checkpointer.py     # Episodic: Configures LangGraph SqliteSaver
    │   ├── vector_store.py     # Semantic: ChromaDB wrapper for facts & entities
    │   ├── playbooks/          # Procedural: Folder for agent-written markdown guides
    │   └── consolidator.py     # Short/Long-Term: Rolling summaries & reflection logic
    │
    ├── models/                 # Model Management (M4 24GB Logic)
    │   ├── manager.py          # The JIT swapper (`gc.collect()`, `mx.metal.clear_cache()`)
    │   ├── supervisor.py       # Qwen3-8B-DWQ initialization and structured output parsing
    │   ├── coder.py            # Qwen3-Coder integration
    │   └── vision.py           # Qwen3-VL integration
    │
    ├── tools/                  # Tool Calling & External connections
    │   └── mcp_client.py       # Connects LangGraph to your local MCP Servers
    │
    ├── pipeline/               # Pre-processing (Runs before LLM sees prompt)
    │   ├── normalizer.py       # fastText language ID & translation routing
    │   └── slang.py            # ChromaDB lookup for Singlish/internet slang
    │
    └── interfaces/             # UX / UI Layer
        ├── cli.py              # `rich` terminal UI (Claude Code style)
        ├── web.py              # `gradio` chatbot UI (Drag-and-drop images)
        └── tauri_app/          # (Optional) Desktop app wrapper configuration
```

---

## 8. Cognitive Memory Hierarchy

F.R.E.D. implements a tiered memory system to decouple context from reasoning, ensuring the Supervisor's 8K context window remains lean and latency stays low.

### 8.1 Short-Term Memory (Working Memory)

- **Sliding Window + Rolling Summary:**
  Raw chat history is strictly capped at the last $N$ turns (e.g., 6 messages). Older messages are not deleted; they are compressed via a background prompt into a dense `working_summary` string that is prepended to the system prompt.
- **Agentic Scratchpad:**
  The LangGraph state maintains a `task_plan` (Supervisor's step-by-step strategy) and a `scratchpad` (internal notes on failed tool executions) to prevent cyclical hallucination loops.

### 8.2 Long-Term Memory (LTM)

LTM is not automatically injected (to prevent context bloat). It is accessed via **Agentic Retrieval** (explicit tool calls by the Supervisor).

- **Semantic Memory (Facts):** Stored in a ChromaDB collection (`semantic_kb`). Retrieved via `query_facts()`. Uses **Time-Weighted Vector Retrieval** to prioritize semantic relevance combined with a recency decay penalty, ensuring F.R.E.D. favors the latest version of a fact.
- **Episodic Memory (Experience):** Powered by LangGraph's native `SqliteSaver`. Captures full conversational states allowing users to say, "Resume what we were working on yesterday."
- **Procedural Memory (Skills):** Stored in `fred/memory/playbooks/` as Markdown. When the Coder agent figures out a complex terminal setup, it synthesizes the steps into a playbook. Retrieved via `query_playbooks()`.

### 8.3 Continuous Learning Loop

F.R.E.D. runs a background **Memory Consolidation Node** after a task completes. It extracts new entities, corrects outdated information, and executes `insert_fact` or `delete_fact` tool calls against ChromaDB to refine its own knowledge base independently of user interaction.
