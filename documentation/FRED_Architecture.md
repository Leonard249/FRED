# F.R.E.D. (Fairly Reliable Engine Doing Deeds)

_A privacy-first, local-first multimodal assistant & agentic workspace for Apple Silicon (M4, 24 GB)._

---

## 0. Reality Check & Core Architectural Invariants

F.R.E.D. operates under strict hardware and design invariants:

1. **"100% Local Inference" vs. "Chain-of-Thought Quality & Calibrated Confidence":**  
   Small local models (3B–8B) struggle with faithful self-reported confidence. Rather than trusting self-assessment scores, F.R.E.D. enforces grammar-constrained schemas and multi-sample self-consistency checks.
2. **Deterministic Memory Budgeting (24 GB M4):**  
   Target models are chosen and benchmarked so their combined weights (~11.02 GB) plus macOS baseline (~5.0 GB) remain safely below the 24 GB ceiling, reserving ~7.5 GB for dynamic KV caches and Metal workspaces without SSD swap-thrashing.
3. **Local-First, Scoped Web Access:**  
   Private data (voice, personal documents, calendar, Gmail, Telegram, banking exports) never leaves the local machine. External web retrieval (DuckDuckGo or Tavily) and web parsing (`trafilatura`) are reasoning-gated, domain-scoped, hop-capped (3–5 hops), and logged.
4. **Architectural Invariant — Non-Bypassable HITL:**  
   The LangGraph state machine enforces an unconditional human-in-the-loop (HITL) review edge before executing any external write action (e.g., sending an email or altering a calendar event).
5. **Zero Filesystem Write Permissions:**  
   F.R.E.D. possesses zero direct filesystem write/delete access. Workspace modifications are strictly emitted as unified diff proposals for manual review.

---

## 1. 3-Tier Adaptive Agent Architecture

To maximize response speed while preventing context drift and infinite loops, F.R.E.D. routes tasks to one of three execution tiers based on task complexity:

```text
                        ┌─────────────────────────────────┐
                        │      USER PROMPT / TASK         │
                        └────────────────┬────────────────┘
                                         │
                                         ▼
                      ┌─────────────────────────────────────┐
                      │    👑 SUPERVISOR CLASSIFIER         │
                      │    (Qwen3-8B Intent & Complexity)   │
                      └──────┬───────────┼───────────┬──────┘
                             │           │           │
           ┌─────────────────┘           │           └──────────────────┐
           ▼                             ▼                              ▼
    [ TIER 1: ReAct ]           [ TIER 2: Plan + Exec ]        [ TIER 3: Reflexion ]
    • Simple lookups            • Multi-modal chains           • Code synthesis & diffs
    • Single tool calls         • Sequential DAG workflows     • Local syntax & test check
    • Sub-second / low latency  • Replanning upon failure      • Actor-Critic self-repair loop
```

- **Tier 1: Fast ReAct (Thought → Action → Observation):**  
  Direct, low-latency execution for single-step requests (`read_calendar_events`, single-file grep, conversational queries).
- **Tier 2: Plan-and-Execute (Planner → Executor → Replanner):**  
  Decomposes multi-step, multi-modal workflows into a directed acyclic graph (DAG). For example: inspecting a newsletter label in Gmail, extracting an article URL, parsing the web page via `trafilatura`, and analyzing an embedded architecture diagram with the Vision agent.
- **Tier 3: Reflexion (Actor → Evaluator → Critique Loop):**  
  Specialized for code generation and bug fixes. The Coder Agent proposes a diff, an automated evaluator checks it locally (`ruff check` or `pytest` via `execute_safe_command`), and if it fails, the error trace triggers an explicit self-critique loop (hard-capped at 2 iterations).

---

## 2. Benchmark-Validated Memory Budget (M4, 24 GB RAM)

Physical memory benchmarks for F.R.E.D.'s selected local model roster:

| Role                    | Model Identifier                               | Quantization | RAM Usage     |
| :---------------------- | :--------------------------------------------- | :----------- | :------------ |
| **Supervisor**          | `mlx-community/Qwen3-8B-4bit-DWQ-053125`       | 4-bit DWQ    | ~4.73 GB      |
| **VLM (Vision)**        | `mlx-community/Qwen3-VL-4B-Instruct-5bit`      | 5-bit        | ~2.89 GB      |
| **Coder**               | `mlx-community/Qwen2.5-Coder-3B-Instruct-8bit` | 8-bit        | ~3.40 GB      |
| **Total Model Weights** | —                                              | —            | **~11.02 GB** |

### System Memory Map

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        24 GB UNIFIED MEMORY                            │
├───────────────────┬───────────────────────────────┬────────────────────┤
│ macOS & Services  │ All 3 Active Models           │ Dynamic Headroom   │
│ (~5.0 – 5.5 GB)   │ (~11.02 GB Weights)           │ (~7.5 – 8.0 GB)    │
│                   │ Qwen3-8B + Qwen3-VL + Coder3B │ KV Caches & Metal  │
└───────────────────┴───────────────────────────────┴────────────────────┘
```

- **KV Cache Control:** Quantized KV cache enabled (`--kv-bits 4`) across runtimes to prevent long-context memory bloat.
- **Context Caps:** Supervisor context window is capped at 8,192 tokens for orchestration, reserving larger context allowances for repository traversal in the Coder agent.
- **Metal Cache Scrubbing:** Explicit eviction (`gc.collect()` and `mlx.core.metal.clear_cache()`) clears temporary tensor buffers after heavy multi-step loops.

---

## 3. Cognitive Memory Hierarchy

F.R.E.D. separates active working context from long-term storage to keep prompts small and token generation fast:

### 3.1 Short-Term Memory (STM)

- **Sliding Window + Rolling Summary:** Raw message history preserves the most recent $N$ turns (e.g., 6 messages). Older messages are compressed by a background summarizer node into a persistent `working_summary` prepended to the prompt.
- **Agentic Scratchpad:** LangGraph state maintains a `task_plan` and `scratchpad` to track tool evaluations, preventing circular failure loops.

### 3.2 Long-Term Memory (LTM)

Long-term memory is retrieved explicitly via tool calls rather than indiscriminately injected into every turn:

- **Semantic Memory (Facts):** ChromaDB collection (`semantic_kb`) scored using **Time-Weighted Vector Retrieval** (semantic similarity combined with a recency decay penalty) via `query_facts()`.
- **Episodic Memory (Past Interactions):** Durable conversational history saved via LangGraph's native SQLite checkpointer (`SqliteSaver`), enabling task resumption across sessions.
- **Procedural Memory (Playbooks):** Reusable execution playbooks stored in `fred/memory/playbooks/` as Markdown documents, retrieved via `query_playbooks()`.

### 3.3 Continuous Learning Loop

Following task completion, an asynchronous **Memory Consolidation Node** extracts new entities and updates or invalidates outdated facts in ChromaDB without adding latency to the primary user interaction.

---

## 4. F.R.E.D. Project Hierarchy (MCP-Ready)

```text
FRED/
├── pyproject.toml              # Managed by `uv`
├── README.md                   # System specification & architecture
├── credentials/                # Local OAuth keys (in .gitignore)
│   ├── credentials.json
│   └── token.json
│
├── mcp_servers/                # 🛠️ THE HANDS: Independent local servers (Model Context Protocol)
│   └── gmail_mcp/
│       ├── __init__.py
│       ├── server.py           # Gmail tools exposed via standard MCP
│       └── auth.py             # OAuth lifecycle management
│
└── fred/                       # 🧠 THE BRAIN: Main application package
    ├── __init__.py
    ├── main.py                 # Application entrypoint (`uv run fred.py --mode [cli|web|app]`)
    │
    ├── core/                   # Orchestration (LangGraph)
    │   ├── graph.py            # LangGraph nodes, router, and edges
    │   ├── state.py            # TypedDict state schemas across all tiers
    │   └── hitl.py             # Non-bypassable approval gates & audit logs
    │
    ├── memory/                 # Cognitive Memory Subsystem
    │   ├── checkpointer.py     # Episodic: LangGraph SQLite state saver
    │   ├── vector_store.py     # Semantic: ChromaDB wrapper with time-weighted decay
    │   ├── playbooks/          # Procedural: Agent markdown playbooks
    │   └── consolidator.py     # Background reflection and memory refinement
    │
    ├── models/                 # Model & MLX Runtime Management
    │   ├── manager.py          # Weight loading and Metal cache maintenance
    │   ├── supervisor.py       # Qwen3-8B orchestration & router
    │   ├── coder.py            # Qwen2.5-Coder-3B execution wrapper
    │   └── vision.py           # Qwen3-VL-4B multimodal wrapper
    │
    ├── tools/                  # Tool Execution Layer
    │   ├── mcp_client.py       # Client interface to local MCP servers
    │   ├── web_reader.py       # Trafilatura HTML & image metadata extractor
    │   └── workspace.py        # Safe inspection tools (view_file, grep, diff proposal)
    │
    ├── pipeline/               # Pre-processing & Normalization
    │   ├── normalizer.py       # Language ID & translation routing
    │   └── slang.py            # Vector mapping for colloquial abbreviations
    │
    └── interfaces/             # User Interaction Layer
        ├── cli.py              # Interactive terminal workspace (`rich`)
        ├── web.py              # Multimodal browser interface (`gradio`)
        └── tauri_app/          # Desktop dock wrapper configuration
```

---

## 5. Tool Definitions & Security Boundaries

### Personal Context & Communications

- `read_gmail_inbox` / `get_email_thread`: Read-only OAuth2 access (`gmail.readonly`) returning structured JSON.
- `read_calendar_events`: Read-only Google Calendar agenda checking.
- `read_telegram_messages`: Read-only message retrieval via Telethon.
- `draft_communication` / `propose_calendar_event`: Prepares payload proposals; strictly non-executable without explicit human approval.

### Web & Scraped Content

- `read_web_page`: Trafilatura-based static text and image extractor with Playwright fallback for dynamic sites.
- `search_web_duckduckgo` / `search_web_tavily`: Reasoning-gated web searches, logged and hop-capped.

### Local Workspace (Read-Only & Diff Proposals)

- `view_file` & `list_directory`: Local source file inspection.
- `search_files_grep`: Targeted regular expression search across project paths.
- `propose_code_diff`: Outputs standard unified diffs; direct disk write APIs are withheld.
- `execute_safe_command`: Strictly whitelisted terminal evaluation (`pytest`, `ruff check`, `git status`, `git diff`).

---

## 6. Omnichannel Interfaces

- **Workspace CLI (`uv run fred.py --mode cli`):** Terminal UI powered by `rich`, featuring streaming reasoning tokens, formatted diff reviews, and execution logs.
- **Multimodal Web App (`uv run fred.py --mode web`):** Local Gradio application with file and image drag-and-drop support for UI mocks and screenshots.
- **Desktop App Wrapper (`uv run fred.py --mode app`):** Persistent macOS desktop integration via a lightweight Tauri wrapper.

---

## 7. Phased Implementation Roadmap

1. **Phase 1 — Model Sandbox & Hardware Validation:**  
   Implement `fred/models/manager.py` using `mlx-lm` and `mlx-vlm`. Verify that loading `Qwen3-8B`, `Qwen3-VL-4B`, and `Qwen2.5-Coder-3B` remains within the memory budget and releases Metal allocations cleanly.
2. **Phase 2 — Core Graph Skeleton & ReAct Tier:**  
   Construct the base LangGraph state machine with the Supervisor model. Wire the `read_gmail` tool and verify structured JSON output end-to-end.
3. **Phase 3 — Multi-Tier Graph Routing:**  
   Implement the Tier 2 Plan-and-Execute DAG (wiring `read_web_page`) and Tier 3 Reflexion loop for the Coder agent with automated lint checking.
4. **Phase 4 — Cognitive Memory Integration:**  
   Deploy the sliding window summarizer, connect ChromaDB for time-weighted fact retrieval, and configure the SQLite checkpointer.
5. **Phase 5 — Omnichannel UI:**  
   Hook up the `rich` CLI and `gradio` web interfaces to the compiled graph.
6. **Phase 6 — HITL & Security Audit:**  
   Verify that external write actions cannot bypass human approval and ensure immutable SQLite logging across all tool calls.
