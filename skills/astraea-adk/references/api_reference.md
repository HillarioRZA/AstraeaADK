# Astraea-ADK (`AstraeaADK`) — Ringkasan Lengkap Kontrak API

Spesifikasi teknis lengkap untuk seluruh kelas kontrak (*Pydantic v2 frozen models*), fungsi orkestrasi, mesin runtime, tata kelola keamanan, dan memori graf.

---

## 1. Top-Level Public Exports

Dapat diimpor langsung via `import AstraeaADK` atau `from AstraeaADK import (...)`:

```python
from AstraeaADK import (
    # Core & Event Streaming
    LLMSpec, MessageEnvelope, CancellationToken, MoAMetadata, contract_message,
    StreamEvent, StreamEventType, emit_stream_event,
    # Protocol (MoA Orchestration)
    AgentRoster, OrchestrationPolicy, OrchestrationResult, ProposalRecord,
    dispatch_envelope, run_moa_debate, run_autonomous_triage,
    extract_mentions, resolve_recipient_handles, extract_delegated_targets,
    register_comm_delegate_tool, COMM_DELEGATE_SCHEMA, DEFAULT_TRIAGE_HANDLES,
    build_aggregator_dynamic_context,
    # Runtime Turn Engine
    execute_turn, SessionState, TurnPolicy, TurnResult,
    compact_turn_history, compact_context_two_tier, estimate_tokens,
    # Memory (Knowledge Graph)
    MarkdownGraphMemory, register_graph_memory_tools,
    FileLockManager, GraphIndexer, GraphNavigator, GraphMutator,
    # Governance & Safety
    DeterministicVerifier, SmartGuardian, ToolCircuitBreaker,
    # Tools, RBAC & MCP Bridge
    ToolSpec, register_tool, execute_registered_tool,
    clear_tool_registry, get_registered_tool, list_registered_tools, unregister_tool,
    mount_mcp_server, unmount_mcp_tools, MCPMountReceipt,
    # Gateway & Routing
    ModelRouter, LEGION_CACHE_BOUNDARY,
    assemble_cached_system_prompt, assemble_cached_system_prompt_from_spec,
    repair_malformed_tool_call, parse_and_repair_json,
)
```

---

## 2. Core Subsystem (`AstraeaADK.core`)

### `LLMSpec` (`frozen=True`, `extra="forbid"`)
- `handle: str`: Handle agen diawali `@` dalam lowercase (misal `"@coordinator"`).
- `agent_name: str`: Nama peran agen yang deskriptif.
- `soul_prompt: str`: Persona, filosofi, gaya komunikasi statis agen.
- `system_prompt: str`: SOP tugas teknis dan batasan kerja statis agen.
- `tool_permissions: Tuple[str, ...]`: Pola izin tool (`"ns:tool"`, `"ns:*"`, `"*"`).
- `model_settings: Optional[Mapping[str, Any]]`: Kamus imutabel model (`provider`, `model`, `temperature`, `max_tokens`, `fallback_models`).

### `MessageEnvelope` (`frozen=True`)
- `envelope_id: str`: ID unik pesan (default: `"msg_<uuid4_hex>"`).
- `sender: str`: Pengenal pengirim (misal `"@user"` atau `"@cto"`).
- `target: Tuple[str, ...]`: Daftar pengenal penerima.
- `content: str`: Konten pesan teks.
- `attachments: Tuple[str, ...]`: Lampiran berkas opsional.
- `reply_to: Optional[str]`: ID pesan yang dibalas.
- `metadata: MoAMetadata`: Metadata MoA (depth, chain-of-command call stack).

### `CancellationToken`
- `pause() -> None`: Menjeda eksekusi secara non-blocking.
- `resume() -> None`: Melanjutkan eksekusi yang dijeda.
- `check_if_paused() -> bool`: True jika sedang dijeda.
- `await wait_if_paused() -> None`: Menunggu hingga resume() dipanggil.
- `cancel(reason: str = "") -> None`: Membatalkan eksekusi secara permanen.
- `is_cancelled -> bool`: True jika dibatalkan.
- `raise_if_cancelled() -> None`: Melempar `asyncio.CancelledError` jika dibatalkan.

### `StreamEvent` & `StreamEventType`
- `event_type: StreamEventType`: `TOKEN`, `THOUGHT`, `TOOL_CALL`, `TOOL_RESULT`, `TURN_START`, `TURN_END`.
- `agent_handle: str`: Handle agen yang sedang aktif memancarkan event.
- `delta: str`: Potongan teks token baru atau reasoning.
- `tool_name: Optional[str]`: Nama tool saat tool call/result.
- `payload: Optional[Dict[str, Any]]`: Argumen tool atau metadata.

---

## 3. Protocol Orchestration Layer (`AstraeaADK.protocol`)

### `dispatch_envelope`
Pintu masuk universal orkestrasi:
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

### `run_moa_debate`
Debat paralel multi-putaran antar-spesialis disintesis oleh agregator:
```python
async def run_moa_debate(
    envelope: MessageEnvelope,
    roster: AgentRoster,
    *,
    aggregator_handle: str = "@supervisor",
    proposer_handles: Optional[Sequence[str]] = None,
    policy: Optional[OrchestrationPolicy] = None,
    token: Optional[CancellationToken] = None,
    on_event: Optional[Callable[[StreamEvent], Coroutine[Any, Any, None]]] = None,
    ...
) -> OrchestrationResult
```

### `run_autonomous_triage`
Triase otonom koordinator memilih spesialis via tool `comm:delegate`:
```python
async def run_autonomous_triage(
    envelope: MessageEnvelope,
    roster: AgentRoster,
    *,
    coordinator_handle: str = "@cos",
    aggregator_handle: Optional[str] = None,
    policy: Optional[OrchestrationPolicy] = None,
    token: Optional[CancellationToken] = None,
    on_event: Optional[Callable[[StreamEvent], Coroutine[Any, Any, None]]] = None,
    ...
) -> OrchestrationResult
```

### `OrchestrationPolicy` (`frozen=True`)
- `max_discussion_rounds: int = 1`: Jumlah putaran perdebatan antar-proposer.
- `max_delegation_depth: int = 3`: Batas kedalaman rekursi Strict Chain-of-Command.
- `proposer_timeout_seconds: float = 60.0`: Batas waktu per proposer (isolasi kegagalan).
- `allow_proposer_tier1_mutations: bool = False`: Blokir mutasi Tier >= 1 saat Proposer paralel demi konkurensi aman.
- `require_all_proposers: bool = False`: Jika False, kegagalan 1 proposer tidak menggagalkan sintesis agregator.

---

## 4. Runtime Turn Engine (`AstraeaADK.runtime`)

### `execute_turn`
Mengeksekusi 1 giliran agen tunggal melalui siklus 10-fase deterministik:
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
    on_event: Optional[Callable[[StreamEvent], Coroutine[Any, Any, None]]] = None,
) -> TurnResult
```

### `TurnResult` (`frozen=True`)
- `status: Literal["COMPLETED", "TOOL_LIMIT_EXCEEDED", "BUDGET_EXCEEDED", "CANCELLED", "TERMINATED", "ERROR"]`
- `final_content: str`: Respon teks final agen.
- `tool_history: Tuple[Dict[str, Any], ...]`: Riwayat panggilan tool dan hasilnya.
- `prompt_tokens: int`, `cached_tokens: int`, `completion_tokens: int`: Statistik token.
- `rounds_count: int`: Jumlah putaran LLM dalam turn ini.
- `is_successful -> bool`: Properti True jika `status == "COMPLETED"`.

---

## 5. Tools & RBAC (`AstraeaADK.tools`)

- `register_tool(name: str, description: str, parameters_schema: Dict[str, Any], risk_tier: Literal[0, 1, 2] = 0, handler: Callable) -> ToolSpec`: Mendaftarkan fungsi native ke registri.
- `mount_mcp_server(command: str, args: List[str], env: Optional[Dict[str, str]] = None, name_prefix: str = "mcp", risk_tier: Literal[0, 1, 2] = 1) -> MCPMountReceipt`: Memasang server eksternal Anthropic MCP via stdio JSON-RPC.
- `unmount_mcp_tools(mount_id: str) -> bool`: Melepas tool MCP dan menghentikan subproses.
- `guard_tool_output(output: str) -> Tuple[str, SpillResult]`: Memastikan output tool tidak melebihi batas aman 50 KB (51.200 byte) dengan pemotongan multi-byte aman.

---

## 6. Memory Subsystem (`AstraeaADK.memory`)

- `register_graph_memory_tools(vault_path: Path, skill_gate: Optional[Callable] = None, max_mutations_per_session: int = 5) -> MarkdownGraphMemory`:
  Mendaftarkan 4 tool pengetahuan lokal:
  1. `graph:locate`: Pencarian Okapi BM25 di RAM + ekspansi tetangga 1-hop (menyertakan `section_id` lengkap `slug#section`).
  2. `graph:inspect_outline`: Membaca struktur daftar heading dan content hash tanpa I/O disk.
  3. `graph:read_section`: Membaca irisan byte via `seek()` biner secara hemat token (toleran input `slug#section` atau format terpisah).
  4. `graph:learn_and_link`: Menulis/memperbarui file Markdown secara atomik dengan OCC hash lock dan verifikasi duplikat Jaccard.
