# Astraea-ADK (`LegionADK`) — Referensi Lengkap API & Kontrak Data

Dokumen ini memuat spesifikasi teknis untuk seluruh kelas kontrak (*Pydantic v2 frozen models*), fungsi orkestrasi, mesin *turn runtime*, tata kelola keamanan, dan *graph memory* yang diekspor oleh paket `LegionADK`.

---

## Daftar Isi

1. [Ekspor Tingkat Atas (`import LegionADK`)](#1-ekspor-tingkat-atas-import-legionadk)
2. [Core Subsystem (`LegionADK.core`)](#2-core-subsystem-legionadkcore)
3. [Gateway & Routing Subsystem (`LegionADK.gateway`)](#3-gateway--routing-subsystem-legionadkgateway)
4. [Tools & RBAC Subsystem (`LegionADK.tools`)](#4-tools--rbac-subsystem-legionadktools)
5. [Governance & Security Subsystem (`LegionADK.governance`)](#5-governance--security-subsystem-legionadkgovernance)
6. [Runtime Turn Engine (`LegionADK.runtime`)](#6-runtime-turn-engine-legionadkruntime)
7. [Autonomous Graph Memory (`LegionADK.memory`)](#7-autonomous-graph-memory-legionadkmemory)
8. [Protocol & MoA Orchestrator (`LegionADK.protocol`)](#8-protocol--moa-orchestrator-legionadkprotocol)
9. [Terminal Interaktif REPL CLI (`LegionADK.interactive_cli`)](#9-terminal-interaktif-repl-cli-legionadkinteractive_cli)
10. [Catatan Rilis & Ringkasan Pembaruan (v1.5.0 & v1.5.1)](#10-catatan-rilis--ringkasan-pembaruan-v150--v151)

---

## 1. Ekspor Tingkat Atas (`import LegionADK`)

Seluruh simbol utama dapat diimpor langsung dari akar paket `LegionADK`:

```python
from LegionADK import (
    # Core & Event Streaming
    LLMSpec, MessageEnvelope, CancellationToken, MoAMetadata, contract_message,
    StreamEvent, StreamEventType, emit_stream_event,
    # Protocol (MoA)
    AgentRoster, OrchestrationPolicy, OrchestrationResult, ProposalRecord,
    dispatch_envelope, run_moa_debate, run_autonomous_triage,
    extract_mentions, resolve_recipient_handles, extract_delegated_targets,
    register_comm_delegate_tool, COMM_DELEGATE_SCHEMA, DEFAULT_TRIAGE_HANDLES,
    build_aggregator_dynamic_context,
    # Runtime
    execute_turn, SessionState, TurnPolicy, TurnResult,
    compact_turn_history, compact_context_two_tier, estimate_tokens,
    # Memory (Knowledge Graph)
    MarkdownGraphMemory, register_graph_memory_tools,
    FileLockManager, GraphIndexer, GraphNavigator, GraphMutator,
    # Governance
    DeterministicVerifier, SmartGuardian, ToolCircuitBreaker,
    # Tools, RBAC & MCP Bridge
    ToolSpec, register_tool, execute_registered_tool,
    clear_tool_registry, get_registered_tool, list_registered_tools, unregister_tool,
    mount_mcp_server, unmount_mcp_tools, MCPMountReceipt,
    # Gateway
    ModelRouter, LEGION_CACHE_BOUNDARY,
    assemble_cached_system_prompt, assemble_cached_system_prompt_from_spec,
    repair_malformed_tool_call, parse_and_repair_json,
)
```


---

## 2. Core Subsystem (`LegionADK.core`)

### 2.1 `LLMSpec`

Kontrak identitas, instruksi statis, izin tool, dan konfigurasi model untuk satu peran agen (`ConfigDict(extra="forbid", frozen=True)`).

```python
from LegionADK.core.llm_spec import LLMSpec
```

Atribut:

- `handle: str` — Pengenal unik agen (dinormalisasi ke lowercase dengan awalan `@`, misal `"@architect"`).
- `agent_name: str` — Nama lengkap peran agen (misal `"Principal Systems Architect"`).
- `soul_prompt: str` — Karakter dasar, cara berpikir, dan prinsip kerja agen.
- `system_prompt: str` — SOP operasional dan batasan kerja statis agen.
- `tool_permissions: Tuple[str, ...]` — Tuple imutabel berisi pola izin tool (contoh: `("comm:delegate", "graph:*")` atau `("*",)`). Default: `()`.
- `model_settings: Mapping[str, Any]` — Konfigurasi model yang dibekukan secara rekursif (`MappingProxyType`). Kunci yang didukung oleh runtime:
  - `"provider"`: `"custom"` | `"openai"` | `"anthropic"` | `"gemini"` | `"ollama"` | `"vllm"` (default: `"custom"`).
  - `"model"`: Nama model target (default: `"deepseek-v4.1-flash"`).
  - `"fallback_models"`: Daftar tuple `(provider, model)` cadangan bila model utama gagal.
  - `"temperature"`: `float` (default: `0.2`).
  - `"max_tokens"`: `Optional[int]` (default: `4096`).
  - `"thinking_level"`: `"low"` | `"medium"` | `"high"` (default: `"medium"`).

Metode:

- `compile_identity() -> str`: Merakit teks identitas kanonis yang 100% deterministik dari `agent_name`, `handle`, `soul_prompt`, dan `system_prompt` untuk perhitungan SHA-256 cache digest.

### 2.2 `MoAMetadata`

Metadata perutean Mixture-of-Agents yang menempel pada `MessageEnvelope` (`frozen=True`).

Atribut:

- `moa_role: Literal["proposer", "aggregator", "standalone"] = "standalone"`
- `layer: int = 1` (wajib ≥ 1)
- `round_index: int = 1` (wajib ≥ 1)
- `proposals: Tuple[Mapping[str, Any], ...] = ()` — Daftar usulan yang telah dibekukan secara rekursif (deep freeze).
- `token_stats: Mapping[str, int] = {}` — Statistik penggunaan token yang dibekukan.

### 2.3 `MessageEnvelope` & `contract_message`

Amplop pesan terstandarisasi untuk komunikasi pengguna-ke-agen maupun antar-agen (`frozen=True`).

Atribut `MessageEnvelope`:

- `envelope_id: str` — ID unik pesan (default otomatis: `"msg_<uuid4_hex>"`).
- `sender: str` — Pengirim pesan (misal `"@user"`, `"@cos"`).
- `target: Tuple[str, ...]` — Tuple penerima pesan (otomatis dikonversi dari `str` atau `Sequence[str]`).
- `content: str` — Isi pesan teks.
- `attachments: Tuple[str, ...] = ()` — Daftar lampiran opsional.
- `reply_to: Optional[str] = None` — Referensi `envelope_id` yang dibalas.
- `metadata: MoAMetadata` — Objek `MoAMetadata` terkait amplop ini.

Fungsi pabrik `contract_message`:

```python
def contract_message(
    sender: str,
    target: Union[str, Sequence[str]],
    content: str,
    *,
    attachments: Optional[Sequence[str]] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[Union[MoAMetadata, Dict[str, Any]]] = None,
) -> MessageEnvelope
```

### 2.4 `CancellationToken`

Objek kontrol interupsi dan penjeda eksekusi asinkron yang memisahkan semantik Pause dan Cancel secara tegas.

Metode & properti:

- `pause() -> None`: Menjeda eksekusi pada titik pemeriksaan berikutnya tanpa membatalkan token.
- `resume() -> None`: Melanjutkan token yang dijeda (tidak akan menghidupkan kembali token yang sudah di-cancel).
- `check_if_paused() -> bool`: Mengembalikan `True` jika token sedang dijeda.
- `await wait_if_paused() -> None`: Menunggu secara non-blocking hingga `resume()` dipanggil.
- `cancel(reason: str = "") -> None`: Membatalkan token secara permanen dan membangunkan semua waiter.
- `is_cancelled -> bool`: Properti status batal.
- `reason -> str`: Alasan pembatalan.
- `raise_if_cancelled() -> None`: Melempar `asyncio.CancelledError` jika dan hanya jika `is_cancelled == True` (tidak melempar saat hanya pause).

### 2.5 `StreamEvent` & Event Streaming System (`stream_events.py`)

Mendukung penerusan token, jejak penalaran (*thinking process*), dan peristiwa eksekusi alat secara *real-time* ke antarmuka terminal/UI tanpa merusak kontrak data statis `TurnResult` dan `OrchestrationResult`.

```python
from LegionADK.core.stream_events import (
    StreamEvent,
    StreamEventType,
    emit_stream_event,
)
```

Tipe Event (`StreamEventType`):

- `StreamEventType.TOKEN` — Potongan teks (*delta token*) konten akhir yang di-stream langsung dari model.
- `StreamEventType.THOUGHT` — Potongan teks penalaran internal (contoh: blok `<think>...</think>` dari DeepSeek R1 atau format `reasoning_content`).
- `StreamEventType.TOOL_CALL` — Model memulai pemanggilan tool (memuat `tool_name` dan `arguments`).
- `StreamEventType.TOOL_RESULT` — Tool selesai dieksekusi (memuat `tool_name`, `status`, dan `info`).
- `StreamEventType.TURN_START` — Putaran agen dimulai.
- `StreamEventType.TURN_END` — Putaran agen selesai beserta status final.

Fungsi `dispatch_envelope`, `execute_turn`, `run_moa_debate`, dan `run_autonomous_triage` menerima argumen opsional `on_event: Optional[Callable[[StreamEvent], Coroutine[Any, Any, None]]]`.

---

## 3. Gateway & Routing Subsystem (`LegionADK.gateway`)

### 3.1 `cache_boundary.py`

Menjaga stabilitas byte pada static prefix system prompt agar Prompt Caching penyedia LLM bekerja optimal.

- `LEGION_CACHE_BOUNDARY: str` — Penanda batas antara bagian statis dan konteks dinamis.
- `assemble_cached_system_prompt_from_spec(spec: LLMSpec, dynamic_context: str = "", max_token_budget: Optional[int] = None) -> Tuple[str, str, str]`: Merakit system prompt lengkap dan mengembalikan tuple `(full_system_prompt, system_digest_sha256, tool_digest_sha256)`. Melempar `SystemOverheadExceededError` jika ukuran prefix statis melampaui `max_token_budget`.
- `split_system_prompt_cache_boundary(prompt: str) -> Optional[Tuple[str, str]]`: Memisahkan `(stable_prefix, dynamic_suffix)`.
- `compute_sha256_digest(text: str) -> str`: Menghitung digest SHA-256 heksadesimal.

### 3.2 `ModelRouter` & `UpstreamChannel` (`model_router.py`)

Router inferensi multi-provider dengan pembatas laju sliding window RPM/TPM per kanal, rekonsiliasi tiket token aktual, dan auto-cooldown saat terjadi kegagalan upstream.

```python
router = ModelRouter()
raw_response = await router.execute_routed_completion(
    prompt="...",                    # atau gunakan messages=[...]
    messages=None,
    system_prompt="...",
    primary_provider="custom",
    primary_model="deepseek-v4.1-flash",
    fallback_models=[("openai", "gpt-4o-mini")],
    temperature=0.2,
    max_tokens=4096,
    tools=None,
    thinking_level="medium",
    token=CancellationToken(),
)
```

- `router.trigger_cooldown(provider: str, seconds: int = 60) -> None`: Menandai seluruh kanal di bawah provider sebagai tidak sehat selama `seconds` detik.

### 3.3 `tool_call_repair.py`

Perbaikan deterministik berbasis stack LIFO untuk menambal JSON argumen tool yang terpotong atau menggunakan literal Python (`True`, `False`, `None`, kutip tunggal) di luar string.

```python
parse_and_repair_json(raw_str: str) -> Optional[Dict[str, Any]]
repair_malformed_tool_call(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]
```

### 3.4 Proxy Environment & Sanitasi `NO_PROXY` IPv6 Berkurung (v1.5.1)

Memastikan seluruh panggilan HTTP adapter gateway (Custom REST, OpenAI-Compatible, Anthropic, Gemini) menghormati konfigurasi proxy perusahaan standar (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, dan `no_proxy`) tanpa mengalami kegagalan fatal pada environment yang mendefinisikan alamat IPv6 berkurung seperti `[::1]`.

```python
from LegionADK.gateway.adapter.base_adapter import (
    create_async_client,
    sanitized_proxy_env,
    _normalize_no_proxy,
)
```

- **Akar Masalah**: Parser internal `httpx` (`get_environment_proxies`) tersedak pada kurung siku IPv6 murni `[::1]`, menghasilkan error fatal `InvalidURL: Invalid port: ':1]'` sebelum request dikirim.
- **Normalisasi Sesaat (`sanitized_proxy_env`)**:
  - `[::1]` dinormalkan menjadi `::1` sehingga dikenali sebagai host IPv6 yang valid.
  - `[::1]:port` dinormalkan menjadi `all://[::1]:port`.
  - Bersifat non-destruktif dan idempoten: `os.environ` asli dikembalikan persis seperti semula begitu objek `AsyncClient` terbentuk.
- **Konstruksi Klien Terpusat (`create_async_client`)**:
  Seluruh adapter gateway membangun klien HTTP menggunakan helper bersama ini dengan parameter `timeout=120.0` dan `trust_env=True`.

---

## 4. Tools & RBAC Subsystem (`LegionADK.tools`)

### 4.1 `ToolSpec` & Fungsi Registri (`permission_registry.py`)

```python
class ToolSpec(BaseModel):
    name: str                                  # Format wajib 'namespace:nama_tool' (dinormalisasi ke lowercase)
    description: str
    risk_tier: Literal[0, 1, 2] = 0            # 0: Read-only, 1: Local mutation, 2: High-risk/External
    parameters_schema: Mapping[str, Any] = ... # Dibekukan rekursif (MappingProxyType)
    handler: Callable[..., Any]                # Fungsi sinkron atau async coroutine
```

Fungsi utama:

- `register_tool(tool: Optional[ToolSpec] = None, *, name: str = "", description: str = "", parameters_schema: Optional[Dict[str, Any]] = None, risk_tier: int = 0, handler: Optional[Callable] = None, allow_overwrite: bool = False) -> ToolSpec`
- `authorize_tool_call(spec: LLMSpec, tool_name: str) -> bool`: Memeriksa apakah `spec.tool_permissions` mengizinkan `tool_name` (mendukung kecocokan persis, wildcard namespace `ns:*`, serta `*` / `ALL`).
- `export_permitted_tools(spec: LLMSpec, format: Literal["openai", "anthropic"] = "openai") -> List[Dict[str, Any]]`: Mengekspor skema tool yang diizinkan untuk agen dalam urutan alfabetis deterministik.
- `await execute_registered_tool(spec: LLMSpec, tool_name: str, arguments: Optional[Dict[str, Any]] = None, token: Optional[CancellationToken] = None) -> str`: Menjalankan pipeline: Cancellation Check → RBAC Check → Lookup → Required Schema Check → Async/Thread Execution → 50KB Output Spill Guard.

Taksonomi eksepsi:

- `ToolPermissionError`: Agen tidak memiliki izin RBAC.
- `ToolNotFoundError`: Nama tool belum terdaftar di registri.
- `ToolArgumentError`: Argumen required pada skema tidak terpenuhi atau tipe tidak valid.
- `ToolExecutionError`: Fungsi handler melempar eksepsi saat dijalankan.

### 4.2 Output Spill Guard 50 KB (`output_spill_guard.py`)

Menjaga agar keluaran tool tidak pernah melebihi batas keras 51.200 bytes (50 KB).

- `process_output_sync(raw_output: str, *, spill_dir: Optional[str] = None, session_id: str = "default") -> SpillResult`: Jika ukuran UTF-8 ≤ 51.200 bita, dikembalikan utuh (`truncated=False`). Jika melampaui batas, isi lengkap disimpan ke berkas `.astraea_spill/spill_<session>_<ts>_<hash>.log` dan teks dipotong secara aman tanpa membelah karakter UTF-8 multi-byte disertai penanda `[OUTPUT_TRUNCATED_EXCEEDED_50KB]`.
- `read_spilled_output_sync(spill_path: str) -> str`: Membaca kembali berkas spill yang sah (menolak pembacaan path arbitrer di luar direktori spill).
- `prune_spill_cache_sync(spill_dir: Optional[str] = None, max_files: int = 50, max_age_seconds: int = 86400) -> int`: Membersihkan berkas spill berdasarkan TTL dan antrean FIFO tanpa menyentuh berkas asing.

### 4.3 Model Context Protocol (MCP) Bridge (`mcp_bridge.py`)

Menjembatani ekosistem perkakas berbasis standar **Anthropic Model Context Protocol (MCP)** melalui protokol standar input/output (stdio JSON-RPC 2.0). Seluruh perkakas yang diekspos oleh server MCP otomatis dikonversi menjadi `ToolSpec` native Astraea ADK dan dapat diatur hak aksesnya dengan RBAC.

```python
from LegionADK.tools import mount_mcp_server, unmount_mcp_tools, MCPMountReceipt
```

Fungsi utama:
- `await mount_mcp_server(command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None, name_prefix: str = "mcp", risk_tier: Literal[0, 1, 2] = 1, timeout: float = 30.0) -> MCPMountReceipt`: Menjalankan subproses server MCP, melakukan handshake inisialisasi, mengambil daftar tool via `tools/list`, dan mendaftarkannya ke registri tool ADK dengan prefiks namespace.
- `await unmount_mcp_tools(mount_id: str) -> bool`: Mencabut seluruh tool yang terpasang dari server MCP tertentu dan menghentikan proses latar belakang secara bersih.

---

## 5. Governance & Security Subsystem (`LegionADK.governance`)

### 5.1 `DeterministicVerifier` (`cov_verifier.py`)

Verifikator pra-eksekusi untuk tool dengan `risk_tier >= 1` (`risk_tier == 0` otomatis lolos passthrough).

```python
verifier = DeterministicVerifier(
    allowed_root="/path/to/workspace", # Opsional: mengunci akses path di dalam root ini
    max_consecutive_rejections=3,
    on_escalation=None,
)
verdict = await verifier.verify(spec, tool_spec, arguments, context_messages)
```

- Memeriksa segmen path traversal (`..`), null byte (`\x00`), ukuran argumen berlebih (> 50 KB), serta pola injeksi shell (`&&`, `;`, `|`, `` ` ``, `$(...)`, `\n`) khusus pada argumen path/perintah tanpa memblokir teks kode yang sah di dalam argumen `content`.
- Mengembalikan `VerificationVerdict(status="APPROVED" | "REJECTED", tool_name=..., risk_tier=..., reasons=(...), limit_reached=bool)`.

### 5.2 `ToolCircuitBreaker` (`circuit_breaker.py`)

Mencegah agen mengulang panggilan tool yang gagal dengan argumen yang persis sama.

```python
compute_tool_signature(tool_name: str, arguments: Any) -> str
# Menghasilkan hash SHA-256 kanonis yang deterministik terhadap urutan kunci
# dictionary, tuple/list, dan set.

cb = ToolCircuitBreaker(threshold: int = 3, on_trip: Optional[Callable[[str, str], None]] = None)
cb.record_tool_outcome(session_id: str, signature: str, success: bool) -> CircuitState
cb.is_open(session_id: str, signature: str) -> bool
cb.prune_idle_sessions(max_idle_seconds: float = 3600.0) -> int
```

### 5.3 `SmartGuardian` (`smart_guardian.py`)

Mesin eskalasi tata kelola sesi dengan tangga status monoton (`CONTINUE` → `WARN` → `FORCE_REPORT` → `TERMINATE`).

```python
event = GovernanceEvent(kind="VERIFICATION_REJECTED" | "REJECTION_LIMIT_REACHED" | "CIRCUIT_OPENED" | "TURN_BREAKER_TRIPPED", session_id=..., tool_name=..., detail=...)
decision = guardian.observe_event(event)  # Mengembalikan GuardianDecision(action=..., report=Optional[GuardianReport])
guardian.get_session_action(session_id: str) -> str
guardian.session_journal(session_id: str) -> Tuple[GovernanceEvent, ...]
```

---

## 6. Runtime Turn Engine (`LegionADK.runtime`)

### 6.1 Kontrak State & Kebijakan (`turn_state.py`)

**`SessionState`** (`frozen=True`) — State percakapan yang dibawa oleh pemanggil antar-giliran:

- `session_id: str` (wajib ≥ 1 karakter)
- `history: Tuple[Dict[str, Any], ...] = ()`
- `turn_count: int = 0`
- `consecutive_empty_turns: int = 0`
- `total_prompt_tokens: int = 0`
- `total_cached_tokens: int = 0`
- `total_completion_tokens: int = 0`

Metode transisi murni:

- `state.with_history(history: Sequence[Dict[str, Any]]) -> SessionState`
- `state.record_turn(prompt_tokens: int, cached_tokens: int, completion_tokens: int, *, empty: bool) -> SessionState`

**`TurnPolicy`** (`frozen=True`):

- `max_turns: int = 10`
- `max_tool_rounds: int = 5`
- `api_timeout_seconds: float = 60.0`
- `context_token_budget: Optional[int] = None`
- `session_token_budget: Optional[int] = None`
- `max_consecutive_empty_turns: int = 3`

**`TurnResult`** (`frozen=True`):

- `status: Literal["COMPLETED", "IN_PROGRESS", "BLOCKED_LOOP", "EXCEEDED_MAX_TURNS", "BUDGET_EXCEEDED", "CANCELLED", "TERMINATED", "ERROR"]`
- `content: str = ""`
- `reasoning: str = ""`
- `tool_results: Tuple[Dict[str, Any], ...] = ()`
- `prompt_tokens: int = 0`
- `cached_tokens: int = 0`
- `completion_tokens: int = 0`
- `rounds_used: int = 0`
- `session_state: SessionState`
- `guardian_report: Optional[GuardianReport] = None`
- `message: str = ""`

### 6.2 `execute_turn` (`turn_facade.py`)

Mengeksekusi satu giliran agen dari Fase 1 (Preflight) hingga Fase 10 (Finalizer).

```python
async def execute_turn(
    spec: LLMSpec,
    envelope: MessageEnvelope,
    session_state: SessionState,
    *,
    router: Optional[ModelRouter] = None,
    verifier: Optional[DeterministicVerifier] = None,
    guardian: Optional[SmartGuardian] = None,
    signature_breaker: Optional[ToolCircuitBreaker] = None,
    token: Optional[CancellationToken] = None,
    policy: Optional[TurnPolicy] = None,
    dynamic_context: str = "",
) -> TurnResult
```

### 6.3 Two-Tier Context Compaction (`turn_compaction.py`)

```python
compact_context_two_tier(messages: List[Any], max_token_budget: int = 8000, preserve_recent_turns: int = 2, custom_counter: Optional[Callable[[str], int]] = None, raise_on_overflow: bool = False, min_history_floor: int = 64) -> List[Dict[str, Any]]
estimate_tokens(target: Any, custom_counter: Optional[Callable[[str], int]] = None) -> int
check_turn_loop_circuit_breaker(consecutive_empty_turns: int, max_allowed: int = 3) -> Tuple[bool, str]
```

---

## 7. Autonomous Graph Memory (`LegionADK.memory`)

### 7.1 Model Kontrak Memori (`graph_models.py`)

Seluruh model bersifat immutable (`frozen=True`, `extra="forbid"`):

- `SectionOffset`: `section_id` (`node_id#slug`), `heading`, `level` (1..6), `start_byte`, `end_byte`, `start_line`, `end_line`, `estimated_tokens`.
- `GraphEdge`: `source_id`, `target_id`, `target_section`, `origin` (`"EXTRACTED"` | `"INFERRED"`), `display_text`.
- `GraphNode`: `node_id`, `title`, `node_type`, `keywords`, `aliases`, `updated`, `content_hash` (SHA-256 16-char), `mtime_ns`, `file_size`, `sections`, `outgoing_links`.
- `NeighborView`: `node_id`, `title`, `node_type`, `edge_origin`, `relation_hint`, `estimated_tokens`.
- `LocateResult`: `candidates`, `neighbors_1hop`, `total_neighbors_found`, `truncated_neighbors`, `telemetry_warning`.
- `NodeOutline`: `node_id`, `title`, `node_type`, `content_hash`, `total_estimated_tokens`, `sections`.
- `SectionPayload`: `node_id`, `section_id`, `heading`, `content`, `truncated_by_spill_guard`, `spill_path`.
- `MutationRequest`: `session_id`, `folder="notes"`, `title`, `note_type="note"`, `mode="create" | "append_section" | "replace_section"`, `content=""`, `linked_nodes=()`, `keywords=()`, `aliases=()`, `target_section=None`, `expected_content_hash=None`.
- `MutationReceipt`: `action_taken` (`"CREATED"` | `"APPENDED_SECTION"` | `"REPLACED_SECTION"` | `"REJECTED_DUPLICATE"` | `"REJECTED_SKILL_GATE"` | `"REJECTED_STALE_HASH"` | `"REJECTED_QUOTA"`), `node_id`, `content_hash`, `dangling_links`, `suggested_targets`.
- `GraphHealthReport`: `total_nodes`, `total_edges`, `dangling_links`, `orphan_nodes`, `zero_hit_locate_ratio`, `locate_thrashing_count`.

### 7.2 `MarkdownGraphMemory` & `register_graph_memory_tools` (`graph_tools.py`)

```python
memory = register_graph_memory_tools(
    vault_path="./vault",
    skill_gate=lambda session_id: True,
    max_mutations_per_session=5,
    default_session_id="default_session",
)
```

Fungsi ini menginstansiasi `MarkdownGraphMemory` sekaligus mendaftarkan 4 tool ke `permission_registry`:

- `graph:locate` (`risk_tier=0`) — Pencarian Okapi BM25 di RAM + ekspansi tetangga 1-hop dengan prioritas EXTRACTED > INFERRED relevan > INFERRED terbaru. Hasil pencarian menyertakan `section_id` lengkap (format `slug#section`) yang siap digunakan langsung oleh model.
- `graph:inspect_outline` (`risk_tier=0`) — Mengambil `NodeOutline` beserta `content_hash` dari RAM tanpa I/O disk.
- `graph:read_section` (`risk_tier=0`) — Membaca irisan byte `[start_byte:end_byte]` via `seek()` biner dengan fallback prefix/Jaccard ≥ 0.75 dan proteksi spill guard 50 KB. Bersifat toleran saat model memasukkan argumen berformat gabungan `slug#heading` maupun argumen terpisah `(document_slug, heading)`.
- `graph:learn_and_link` (`risk_tier=1`) — Menulis atau memperbarui berkas `.md` secara atomik di bawah `FileLockManager`, dilengkapi validasi `skill_gate`, deteksi duplikat Weighted Jaccard (≥ 0.65), verifikasi OCC `expected_content_hash`, dan umpan balik instant lint (`dangling_links`).

### 7.3 `FileLockManager` & Atomic I/O (`file_lock_manager.py`)

```python
lock_mgr = FileLockManager()
async with lock_mgr.acquire(file_path): ...  # Mengunci path kanonis (os.path.normcase(os.path.abspath(path)))
```

- `atomic_write_bytes(target_path, data, *, max_retries=5)` & `atomic_write_text(target_path, text, encoding="utf-8", *, max_retries=5)` — Menulis ke berkas `.tmp_<uuid>.md`, menjalankan `flush()` + `os.fsync()`, lalu memanggil `os.replace()` dengan exponential backoff retry terhadap penguncian sementara NTFS Windows.

---

## 8. Protocol & MoA Orchestrator (`LegionADK.protocol`)

### 8.1 Kontrak Orkestrasi (`moa_models.py`)

**`AgentRoster`** (`frozen=True`) — Direktori tim yang memetakan `@handle` ke `LLMSpec`.

```python
roster = AgentRoster([spec_cos, spec_cto, spec_pm])

roster.get_spec(handle: str) -> Optional[LLMSpec]
roster.list_handles() -> Tuple[str, ...]
roster.build_directory_summary() -> str
```

Mendukung operator `handle in roster`, `roster[handle]`, `len(roster)`, dan iterasi `for spec in roster`.

**`OrchestrationPolicy`** (`frozen=True`):

- `max_discussion_rounds: int = 2`
- `max_parallel_proposers: int = 5`
- `max_delegation_depth: int = 3`
- `allow_proposer_tier1_mutations: bool = False` — Jika `False`, `ParallelProposerGuardVerifier` menolak pemanggilan tool `risk_tier >= 1` selama agen Proposer berjalan paralel.
- `total_token_budget: Optional[int] = None`
- `turn_policy: TurnPolicy = TurnPolicy()`

**`ProposalRecord`** (`frozen=True`):

- `proposer_handle: str`, `agent_name: str`, `layer: int`, `round_index: int`, `content: str`, `latency_ms: float`, `prompt_tokens: int`, `cached_tokens: int`, `completion_tokens: int`, `turn_status: str`.

**`OrchestrationResult`** (`frozen=True`):

- `status: Literal["COMPLETED", "PARTIAL_PROPOSALS", "BUDGET_EXCEEDED", "CANCELLED", "TERMINATED", "ERROR"]`
- `mode: Literal["STANDALONE", "EXPLICIT_MOA", "AUTONOMOUS_TRIAGE"]`
- `final_content: str`
- `aggregator_handle: str`
- `proposer_handles: Tuple[str, ...]`
- `rounds_executed: int`
- `proposals: Tuple[ProposalRecord, ...]`
- `envelopes_log: Tuple[MessageEnvelope, ...]`
- `total_prompt_tokens: int`, `total_cached_tokens: int`, `total_completion_tokens: int`
- `session_states: Mapping[str, SessionState]`
- `is_successful -> bool` (Properti: `True` jika status in `("COMPLETED", "PARTIAL_PROPOSALS")`).

### 8.2 Fungsi Orkestrasi Utama (`orchestrator_facade.py` & `moa_aggregator.py`)

**`dispatch_envelope`** — Router otomatis tingkat atas yang mengarahkan amplop ke `run_autonomous_triage`, `run_moa_debate`, atau `execute_turn` (STANDALONE).

```python
async def dispatch_envelope(
    envelope: MessageEnvelope,
    roster: AgentRoster,
    *,
    policy: Optional[OrchestrationPolicy] = None,
    default_aggregator: str = "@supervisor",
    triage_handles: Sequence[str] = ("@cos", "@secretary", "@coordinator"),
    router: Optional[Any] = None,
    verifier: Optional[DeterministicVerifier] = None,
    guardian: Optional[Any] = None,
    signature_breaker: Optional[Any] = None,
    token: Optional[CancellationToken] = None,
    session_states: Optional[Dict[str, SessionState]] = None,
    depth: int = 0,
    active_call_stack: Tuple[str, ...] = (),
    on_event: Optional[Callable[[StreamEvent], Coroutine[Any, Any, None]]] = None,
) -> OrchestrationResult
```

**`run_moa_debate`** (Cara 1 — Diskusi Multi-Agen Eksplisit):

```python
async def run_moa_debate(
    envelope: MessageEnvelope,
    roster: AgentRoster,
    *,
    aggregator_handle: str = "@supervisor",
    proposer_handles: Optional[Sequence[str]] = None,
    policy: Optional[OrchestrationPolicy] = None,
    router: Optional[Any] = None,
    verifier: Optional[DeterministicVerifier] = None,
    guardian: Optional[Any] = None,
    signature_breaker: Optional[Any] = None,
    token: Optional[CancellationToken] = None,
    session_states: Optional[Dict[str, SessionState]] = None,
    depth: int = 0,
    active_call_stack: Tuple[str, ...] = (),
    on_event: Optional[Callable[[StreamEvent], Coroutine[Any, Any, None]]] = None,
) -> OrchestrationResult
```

**`run_autonomous_triage`** (Cara 2 — Triase Otonom & Strict Chain-of-Command):

```python
async def run_autonomous_triage(
    envelope: MessageEnvelope,
    roster: AgentRoster,
    *,
    coordinator_handle: str = "@cos",
    aggregator_handle: Optional[str] = None,
    policy: Optional[OrchestrationPolicy] = None,
    router: Optional[Any] = None,
    verifier: Optional[DeterministicVerifier] = None,
    guardian: Optional[Any] = None,
    signature_breaker: Optional[Any] = None,
    token: Optional[CancellationToken] = None,
    session_states: Optional[Dict[str, SessionState]] = None,
    depth: int = 0,
    active_call_stack: Tuple[str, ...] = (),
    initial_triage_turn: Optional[TurnResult] = None,
    initial_targets: Optional[Sequence[str]] = None,
    on_event: Optional[Callable[[StreamEvent], Coroutine[Any, Any, None]]] = None,
) -> OrchestrationResult
```

### 8.3 Mention & Delegation Utilities (`mention_router.py`)

- `extract_mentions(text: str, roster: Optional[AgentRoster] = None) -> List[str]`: Mengekstrak `@handle` di luar blok kode Markdown dan mengabaikan format email.
- `resolve_recipient_handles(sender: str, raw_targets: Union[str, Sequence[str]], roster: AgentRoster) -> List[str]`: Mengekspansi `@all` dan membuang handle milik sender (mencegah self-mention loop).
- `register_comm_delegate_tool(allow_overwrite: bool = True) -> ToolSpec`: Mendaftarkan tool `comm:delegate(targets: List[str], topic: str)` (`risk_tier=0`).
- `extract_delegated_targets(content: str = "", tool_calls: Optional[Sequence[Dict[str, Any]]] = None, roster: Optional[AgentRoster] = None) -> List[str]`: Mengekstrak target delegasi gabungan dari argumen `comm:delegate` dan mention di dalam teks jawaban.

---

## 9. Terminal Interaktif REPL CLI (`LegionADK.interactive_cli`)

Modul antarmuka terminal mandiri berbasis Read-Eval-Print Loop (REPL) yang memungkinkan pengguna berinteraksi langsung dengan orkestrator tim multi-agen secara interaktif dengan visualisasi streaming token dan proses penalaran (*thinking*) secara *real-time*.

```bash
# Menjalankan antarmuka terminal interaktif Astraea ADK
python -m LegionADK.interactive_cli
```

Fitur utama:
- **Streaming Token & Penalaran**: Menampilkan token kata per kata secara langsung, memisahkan blok penalaran (*thinking block*) dengan warna kontras abu-abu.
- **Perintah CLI Bawaan**:
  - `/exit` atau `/quit` — Mengakhiri sesi interaktif.
  - `/roster` — Menampilkan direktori agen, spesialisasi peran, dan wewenang tool masing-masing.
  - `/history` — Menampilkan ringkasan riwayat percakapan sesi aktif.
  - `/clear` — Mengosongkan riwayat memori sesi aktif dan memulai percakapan baru.
- **Non-Intrusive**: Berjalan di atas callback hook `on_event` tanpa mengubah kontrak data statis `TurnResult` maupun `OrchestrationResult`.

---

## 10. Catatan Rilis & Ringkasan Pembaruan (v1.5.0 & v1.5.1)

### Versi 1.5.1 (Patch Release)
- **Sanitasi `NO_PROXY` / `no_proxy` untuk IPv6 Berkurung**:
  - Mengatasi kegagalan fatal `httpx.InvalidURL: Invalid port: ':1]'` pada sandbox/lingkungan enterprise yang memuat entri seperti `[::1]` atau `[::1]:port`.
  - Menghadirkan helper bersama `create_async_client` dan context manager non-destruktif `sanitized_proxy_env` di `gateway/adapter/base_adapter.py`.
  - Memperbarui keempat adapter LLM (`custom_adapter`, `openai_compatible`, `anthropic_adapter`, `gemini_adapter`) untuk menggunakan konstruksi klien terpusat.
  - Menjaga 100% kompatibilitas mundur dan integritas variabel lingkungan asli.

### Versi 1.5.0 (Minor Release)
- **Real-Time Event & Token Streaming**:
  - Implementasi modul `LegionADK.core.stream_events` (`StreamEvent`, `StreamEventType`, `emit_stream_event`).
  - Integrasi hook `on_event` pada `execute_turn`, `run_moa_debate`, `run_autonomous_triage`, dan `dispatch_envelope`.
  - Ekstraksi blok penalaran `<think>...</think>` (model DeepSeek R1 / Reasoning) ke variabel penalaran khusus.
- **Terminal Interaktif REPL CLI**:
  - Menghadirkan antarmuka command-line interaktif `interactive_cli.py`.
- **Model Context Protocol (MCP) Bridge**:
  - Penambahan modul `LegionADK.tools.mcp_bridge` (`mount_mcp_server`, `unmount_mcp_tools`, `MCPMountReceipt`).
- **Optimasi Konteks & UX Tool Memory**:
  - Peningkatan kemudahan model pada `graph:locate` (penyertaan `section_id` lengkap) dan `graph:read_section` (toleran input `slug#section`).
  - MoA Context Pruning & Truncation Guard untuk mencegah luapan token pada layer agregasi multi-agen.
- **Dukungan Proxy Korporasi**:
  - Adapter gateway menghormati variabel lingkungan proxy standar (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`).

