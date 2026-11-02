# Astraea ADK (LegionADK) — Panduan Lengkap API & Referensi Fungsi

Buku panduan ini mendokumentasikan seluruh fungsi, kelas kontrak (*models*), dan utilitas publik yang tersedia di **Astraea ADK**. Seluruh modul dirancang dengan prinsip **async-first**, **Pydantic v2 immutability (`frozen=True`)**, **100% role-agnostic**, serta bebas ketergantungan pada database eksternal.

---

## 📑 Daftar Isi

- [1. Core Subsystem (`LegionADK.core`)](#1-core-subsystem-legionadkcore)
  - [1.1 `LLMSpec`](#11-llmspec)
  - [1.2 `MessageEnvelope`](#12-messageenvelope)
  - [1.3 `CancellationToken`](#13-cancellationtoken)
  - [1.4 `contract_message`](#14-contract_message)
- [2. Protocol Orchestration Layer (`LegionADK.protocol`)](#2-protocol-orchestration-layer-legionadkprotocol)
  - [2.1 `dispatch_envelope`](#21-dispatch_envelope)
  - [2.2 `run_moa_debate`](#22-run_moa_debate)
  - [2.3 `run_autonomous_triage`](#23-run_autonomous_triage)
  - [2.4 `extract_mentions`](#24-extract_mentions)
  - [2.5 `register_comm_delegate_tool`](#25-register_comm_delegate_tool)
  - [2.6 `extract_delegated_targets`](#26-extract_delegated_targets)
  - [2.7 `AgentRoster`, `OrchestrationPolicy`, `OrchestrationResult`](#27-kontrak-data-protokol)
- [3. Runtime Turn Engine Layer (`LegionADK.runtime`)](#3-runtime-turn-engine-layer-legionadkruntime)
  - [3.1 `execute_turn`](#31-execute_turn)
  - [3.2 `compact_turn_history`](#32-compact_turn_history)
  - [3.3 `compact_context_two_tier`](#33-compact_context_two_tier)
  - [3.4 `estimate_tokens`](#34-estimate_tokens)
  - [3.5 `SessionState`, `TurnPolicy`, `TurnResult`](#35-kontrak-data-runtime)
- [4. Tools & RBAC Subsystem (`LegionADK.tools`)](#4-tools--rbac-subsystem-legionadktools)
  - [4.1 `register_tool`](#41-register_tool)
  - [4.2 `execute_registered_tool`](#42-execute_registered_tool)
  - [4.3 `authorize_tool_call`](#43-authorize_tool_call)
  - [4.4 `guard_tool_output`](#44-guard_tool_output)
  - [4.5 Manajemen Registri: `list_registered_tools`, `get_registered_tool`, `clear_tool_registry`](#45-utilitas-manajemen-registri)
- [5. Gateway & Routing Layer (`LegionADK.gateway`)](#5-gateway--routing-layer-legionadkgateway)
  - [5.1 `ModelRouter`](#51-modelrouter)
  - [5.2 `assemble_cached_system_prompt_from_spec`](#52-assemble_cached_system_prompt_from_spec)
  - [5.3 `repair_malformed_tool_call`](#53-repair_malformed_tool_call)
  - [5.4 `parse_and_repair_json`](#54-parse_and_repair_json)
- [6. Governance & Security Layer (`LegionADK.governance`)](#6-governance--security-layer-legionadkgovernance)
  - [6.1 `DeterministicVerifier`](#61-deterministicverifier)
  - [6.2 `SmartGuardian`](#62-smartguardian)
  - [6.3 `ToolCircuitBreaker`](#63-toolcircuitbreaker)
- [7. Memory Layer: Local Knowledge Graph (`LegionADK.memory`)](#7-memory-layer-local-knowledge-graph-legionadkmemory)
  - [7.1 `MarkdownGraphMemory`](#71-markdowngraphmemory)
  - [7.2 `register_graph_memory_tools`](#72-register_graph_memory_tools)
  - [7.3 `GraphIndexer`](#73-graphindexer)
  - [7.4 `GraphNavigator`](#74-graphnavigator)
  - [7.5 `GraphMutator`](#75-graphmutator)
  - [7.6 `FileLockManager`](#76-filelockmanager)

---

## 1. Core Subsystem (`LegionADK.core`)

Modul dasar yang mendefinisikan identitas agen, pesan komunikasi, dan token pembatalan eksekusi.

### 1.1 `LLMSpec`

Kelas data beku (*immutable Pydantic v2 model*) yang merepresentasikan identitas, persona, instruksi sistem, dan izin operasional seorang agen.

```python
from LegionADK.core.llm_spec import LLMSpec
```

#### Atribut Utama:
* `handle: str`: Pengenal unik agen dengan awalan `@` (contoh: `"@coordinator"`, `"@cto"`, `"@pm"`).
* `agent_name: str`: Nama lengkap/gelar peran yang deskriptif.
* `soul_prompt: str`: Persona fundamental, filosofi, gaya berpikir, dan nada komunikasi agen.
* `system_prompt: str`: SOP tugas teknis, batasan kerja, dan arahan penyelesaian masalah.
* `tool_permissions: Sequence[str]`: Daftar izin pemanggilan tool berbasis pola (contoh: `["comm:delegate"]`, `["graph:*"]`, `["*"]`). Default: `()`.
* `model_settings: Optional[Dict[str, Any]]`: Konfigurasi inferensi model yang dikemas dalam dictionary:
  * `"provider": str`: Nama penyedia LLM (`"custom"`, `"openai"`, `"anthropic"`, `"gemini"`). Default: `"custom"`.
  * `"model": str`: Nama model yang dituju (contoh: `"deepseek-v4.1-flash"`). Default: `"deepseek-v4.1-flash"`.
  * `"temperature": float`: Parameter keacakan inferensi (default: `0.2`).
  * `"max_tokens": int`: Batas token output (default: `4096`).
  * `"fallback_models": Sequence[Union[str, Tuple[str, str]]]`: Daftar model cadangan otomatis jika model utama mengalami kendala rate-limit (HTTP 429) atau server down (5xx).

#### Contoh Penggunaan:
```python
spec = LLMSpec(
    handle="@architect",
    agent_name="Enterprise Systems Architect",
    soul_prompt="Kamu adalah arsitek sistem yang berorientasi pada determinisme dan keandalan tinggi.",
    system_prompt="Analisis setiap kebutuhan arsitektur dan berikan rekomendasi modul yang terukur.",
    tool_permissions=["comm:delegate", "graph:*"],
    model_settings={
        "provider": "custom",
        "model": "deepseek-v4.1-flash",
        "temperature": 0.2,
        "max_tokens": 4096,
        "fallback_models": ["gemini/gemini-1.5-flash", ("openai", "gpt-4o-mini")],
    },
)
```

---

### 1.2 `MessageEnvelope`

Format amplop pesan standar untuk pertukaran pesan antar-pengguna, antar-agen, maupun delegasi sistem.

```python
from LegionADK.core.llm_spec import MessageEnvelope
```

#### Atribut Utama:
* `sender: str`: Pengenal entitas pengirim (contoh: `"user"`, `"@coordinator"`).
* `target: Sequence[str]`: Daftar pengenal entitas penerima (contoh: `["@cto"]`, `["@cto", "@pm"]`).
* `content: str`: Isi utama pesan teks.
* `reply_to: Optional[str]`: ID pesan sebelumnya yang dibalas.
* `attachments: Sequence[str]`: Jalur berkas atau referensi lampiran yang disertakan.
* `metadata: Optional[MoAMetadata]`: Metadata perutean multi-agen (putaran MoA, daftar proposal, peran koordinator).

#### Contoh Penggunaan:
```python
envelope = MessageEnvelope(
    sender="user",
    target=["@coordinator"],
    content="Tolong koordinasikan tim untuk merancang strategi peluncuran produk baru.",
)
```

---

### 1.3 `CancellationToken`

Pengontrol pembatalan asinkron yang aman (*thread-safe & coroutine-safe*) untuk menghentikan putaran inferensi atau eksekusi tool di tengah jalan secara deterministik.

```python
from LegionADK.core.llm_spec import CancellationToken
```

#### Metode:
* `cancel()`: Membatalkan proses aktif seketika.
* `is_cancelled -> bool`: Mengembalikan status apakah proses telah dibatalkan.
* `raise_if_cancelled()`: Memicu `asyncio.CancelledError` jika token telah dibatalkan.

#### Contoh Penggunaan:
```python
token = CancellationToken()

# Di task terpisah atau event handler timeout:
# token.cancel()

# Di dalam coroutine yang berjalan:
token.raise_if_cancelled()
```

---

### 1.4 `contract_message`

Fungsi utilitas untuk memvalidasi dan mengemas pesan mentah menjadi objek `MessageEnvelope` yang sesuai kontrak ADK.

```python
from LegionADK.core.llm_spec import contract_message

envelope = contract_message(
    sender="user",
    target=["@architect", "@security"],
    content="Diskusikan rancangan arsitektur autentikasi token.",
)
```

---

## 2. Protocol Orchestration Layer (`LegionADK.protocol`)

Lapisan tingkat tinggi yang mengatur alur orkestrasi Mixture-of-Agents (MoA), debat multi-putaran, triase otonom, dan pendelegasian berjenjang (*Strict Chain-of-Command*).

### 2.1 `dispatch_envelope`

Pintu masuk (*facade router*) utama orkestrasi. Menganalisis target amplop dan isi pesan secara otomatis untuk memilih mode eksekusi yang paling tepat.

```python
from LegionADK.protocol import dispatch_envelope
```

#### Tanda Tangan Fungsi:
```python
async def dispatch_envelope(
    envelope: MessageEnvelope,
    roster: AgentRoster,
    *,
    policy: Optional[OrchestrationPolicy] = None,
    default_aggregator: str = "@supervisor",
    triage_handles: Sequence[str] = ("@cos", "@secretary", "@coordinator"),
    router: Optional[ModelRouter] = None,
    verifier: Optional[DeterministicVerifier] = None,
    guardian: Optional[SmartGuardian] = None,
    signature_breaker: Optional[ToolCircuitBreaker] = None,
    token: Optional[CancellationToken] = None,
    session_states: Optional[Dict[str, SessionState]] = None,
    depth: int = 0,
    active_call_stack: Tuple[str, ...] = (),
) -> OrchestrationResult
```

#### Logika Penentuan Rute:
1. **Cara 2 (`run_autonomous_triage`)**: Dipilih jika `envelope.target` hanya berisi 1 koordinator yang terdaftar di `triage_handles`.
2. **Cara 1 (`run_moa_debate`)**: Dipilih jika `envelope.target` berisi $\ge 2$ agen, atau pesan menyebutkan beberapa `@handle` spesialis bersama target agregator.
3. **Standalone (`execute_turn`)**: Dipilih jika target adalah 1 agen spesialis biasa tanpa instruksi delegasi multi-agen.

#### Nilai Kembalian:
Mengembalikan objek `OrchestrationResult` beku (*frozen*) dengan atribut:
* `status`: `"COMPLETED"` | `"ERROR"` | `"CANCELLED"`.
* `final_content`: Teks sintesis eksekutif akhir atau jawaban agen.
* `mode`: Mode yang dieksekusi (`"AUTONOMOUS_TRIAGE"`, `"MOA_DEBATE"`, atau `"STANDALONE"`).
* `proposals`: Tuple `ProposalRecord` dari semua agen proposer yang berpartisipasi.
* `rounds_completed`: Jumlah putaran diskusi yang telah berjalan.
* `session_states`: Pemetaan status sesi terbaru untuk setiap agen.

#### Contoh Penggunaan:
```python
result = await dispatch_envelope(
    envelope=MessageEnvelope(sender="user", target=["@coordinator"], content="Evaluasi migrasi ke microservices."),
    roster=roster,
)
print("Hasil Orkestrasi:", result.final_content)
```

---

### 2.2 `run_moa_debate`

Menjalankan proses debat multi-putaran eksplisit antar-proposer (Cara 1). Agen-agen proposer dieksekusi secara paralel untuk menyusun draf awal, melakukan kritik silang (*cross-critique*), dan hasilnya disintesiskan kembali oleh agregator.

```python
from LegionADK.protocol import run_moa_debate
```

#### Tanda Tangan Fungsi:
```python
async def run_moa_debate(
    envelope: MessageEnvelope,
    roster: AgentRoster,
    *,
    aggregator_handle: str = "@supervisor",
    proposer_handles: Optional[Sequence[str]] = None,
    policy: Optional[OrchestrationPolicy] = None,
    router: Optional[ModelRouter] = None,
    verifier: Optional[DeterministicVerifier] = None,
    guardian: Optional[SmartGuardian] = None,
    signature_breaker: Optional[ToolCircuitBreaker] = None,
    token: Optional[CancellationToken] = None,
    session_states: Optional[Dict[str, SessionState]] = None,
    depth: int = 0,
    active_call_stack: Tuple[str, ...] = (),
) -> OrchestrationResult
```

#### Parameter Kunci:
* `aggregator_handle`: Handle agen yang bertugas merumuskan keputusan akhir (default: `"@supervisor"`).
* `proposer_handles`: Daftar eksplisit agen proposer (contoh: `["@cto", "@pm"]`). Jika `None`, sistem otomatis mengekstrak mention dari `envelope.content`.
* `policy.max_discussion_rounds`: Jumlah putaran debat. Jika $\ge 2$, putaran berikutnya memuat konteks kritik silang antar-draf proposer.

#### Contoh Penggunaan:
```python
result = await run_moa_debate(
    envelope=MessageEnvelope(sender="user", target=["@cto", "@pm"], content="Rancang arsitektur API caching."),
    roster=roster,
    aggregator_handle="@supervisor",
)
```

---

### 2.3 `run_autonomous_triage`

Menjalankan proses triase dan pendelegasian otonom (Cara 2). Koordinator mengevaluasi topik dan secara cerdas memilih spesialis dari roster menggunakan tool `comm:delegate` atau teks terstruktur.

```python
from LegionADK.protocol import run_autonomous_triage
```

#### Tanda Tangan Fungsi:
```python
async def run_autonomous_triage(
    envelope: MessageEnvelope,
    roster: AgentRoster,
    *,
    coordinator_handle: str = "@cos",
    aggregator_handle: Optional[str] = None,
    policy: Optional[OrchestrationPolicy] = None,
    router: Optional[ModelRouter] = None,
    verifier: Optional[DeterministicVerifier] = None,
    guardian: Optional[SmartGuardian] = None,
    signature_breaker: Optional[ToolCircuitBreaker] = None,
    token: Optional[CancellationToken] = None,
    session_states: Optional[Dict[str, SessionState]] = None,
    depth: int = 0,
    active_call_stack: Tuple[str, ...] = (),
    initial_triage_turn: Optional[TurnResult] = None,
    initial_targets: Optional[Sequence[str]] = None,
) -> OrchestrationResult
```

#### Fitur & Keunggulan Khusus:
* **Zero Double-Triage Ingestion (`initial_triage_turn`)**: Jika koordinator telah memanggil delegasi pada giliran sebelumnya, giliran tersebut langsung diinjeksikan sehingga LLM koordinator tidak dipanggil dua kali di Fase 1.
* **Jalur Cepat (Fast-Path)**: Jika koordinator menjawab langsung tanpa mendelegasikan tugas ke spesialis manapun, hasilnya langsung dikembalikan sebagai `STANDALONE` tanpa latensi tambahan.
* **Anti-Cycle Guard**: Mendeteksi jika hierarki memanggil kembali agen yang sedang menunggu di `active_call_stack`, seketika menghentikan rekursi dengan status `ERROR`.

---

### 2.4 `extract_mentions`

Parser deterministik untuk mengekstrak pengenal `@handle` agen yang valid dari teks pesan.

```python
from LegionADK.protocol import extract_mentions

# Kebal terhadap blok kode Markdown dan alamat email:
text = "Silakan @architect berdiskusi dengan @security. Hubungi admin@company.com jika ada kendala."
mentions = extract_mentions(text, roster=roster)
# Hasil: ['@architect', '@security']
```

---

### 2.5 `register_comm_delegate_tool`

Mendaftarkan tool `comm:delegate` ke registri in-memory ADK secara idempotent.

```python
from LegionADK.protocol import register_comm_delegate_tool

tool_spec = register_comm_delegate_tool()
# Tool 'comm:delegate' terdaftar dengan parameter `targets` (list string) dan `instructions` (string).
```

---

### 2.6 `extract_delegated_targets`

Mengekstraksi daftar target delegasi dari pemanggilan tool terstruktur `comm:delegate` maupun dari teks konten agen.

```python
from LegionADK.protocol import extract_delegated_targets

# Tanda Tangan Fungsi:
# extract_delegated_targets(
#     content: str = "",
#     tool_calls: Optional[Sequence[Dict[str, Any]]] = None,
#     roster: Optional[AgentRoster] = None,
# ) -> List[str]

# Contoh: Mengekstrak target delegasi dari hasil eksekusi agen
targets = extract_delegated_targets(
    content=turn_result.content,
    tool_calls=[tr.get("tool_call") for tr in turn_result.tool_results if tr.get("tool_call")],
    roster=roster,
)
# Mengembalikan list handle yang valid, misal: ['@architect', '@security']
```

---

### 2.7 Kontrak Data Protokol

```python
from LegionADK.protocol import AgentRoster, OrchestrationPolicy, OrchestrationResult, ProposalRecord
```

* **`AgentRoster(agents: Sequence[LLMSpec])`**: Kumpulan agen yang terdaftar dalam ekosistem.
  * `roster.get_spec("@handle") -> Optional[LLMSpec]`: Mengambil spesifikasi agen berdasarkan handle.
  * `roster.build_directory_summary() -> str`: Merakit ringkasan direktori peran tim untuk prompt koordinator triase.
  * `roster.list_handles() -> List[str]`: Mengembalikan seluruh handle agen yang aktif di roster.
* **`OrchestrationPolicy`**:
  * `max_discussion_rounds: int = 1`: Putaran debat antar-proposer.
  * `max_delegation_depth: int = 3`: Batas kedalaman delegasi hierarkis (Strict Chain-of-Command).
  * `max_parallel_proposers: int = 5`: Jumlah maksimum agen proposer yang dapat dieksekusi bersamaan.
  * `allow_proposer_tier1_mutations: bool = False`: Menegakkan mode read-only paralel untuk mencegah balapan data (*race condition*).
* **`ProposalRecord`**: Catatan draf usulan tiap proposer (handle, putaran ke-N, status, isi usulan).
* **`OrchestrationResult`**: Hasil akhir orkestrasi multi-agen beku (*immutable*).

---

## 3. Runtime Turn Engine Layer (`LegionADK.runtime`)

Mesin eksekusi inti yang mengendalikan siklus hidup 10 fase (*10-Phase Pipeline*) dari sebuah giliran interaksi agen.

### 3.1 `execute_turn`

Fungsi utama yang mengeksekusi satu giliran interaksi agen secara otonom dari awal hingga akhir.

```python
from LegionADK.runtime import execute_turn
```

#### Tanda Tangan Fungsi:
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

#### 10 Fase yang Dijalankan:
1. **Preflight Governance Check**: Memverifikasi token pembatalan, kuota sesi, dan aturan guardian.
2. **History & Context Budget Compaction**: Memastikan total token riwayat berada dalam batas `context_token_budget`.
3. **Cached System Prompt Assembly**: Merakit prompt sistem statis di atas `LEGION_CACHE_BOUNDARY` untuk memaksimalkan cache hit.
4. **Watchdog-Monitored LLM Call**: Pemanggilan model dengan pengawas timeout dan penanganan kesalahan.
5. **Tool Execution with Verifier & Guard**: Mengeksekusi panggilan fungsi yang diminta model setelah diverifikasi oleh RBAC dan DeterministicVerifier.
6. **Guardian Observation & Loop Circuit Breaker**: Mengevaluasi potensi loop berulang atau instruksi anomali.
7. **Context Compaction**: Kompresi bertingkat jika interaksi menghasilkan output berukuran besar.
8. **Tool Results Synthesis**: Mengirim hasil tool kembali ke model untuk diringkas (multi-round tool execution).
9. **Session State Synchronization**: Memperbarui status riwayat percakapan.
10. **Finalization to Frozen TurnResult**: Mengunci hasil giliran dalam objek `TurnResult` yang beku.

#### Contoh Penggunaan:
```python
state = SessionState(session_id="sess_001")
result = await execute_turn(
    spec=architect_spec,
    envelope=MessageEnvelope(sender="user", target=["@architect"], content="Berapa estimasi kapasitas server?"),
    session_state=state,
)
print("Jawaban:", result.content)
print("Status Sesi Baru:", result.session_state)
```

---

### 3.2 `compact_turn_history` & `compact_context_two_tier`

Utilitas manajemen jendela token (*context window management*) cerdas:

```python
from LegionADK.runtime import compact_turn_history, compact_context_two_tier
```

* **`compact_turn_history(history, budget, system_overhead, ...)`**: Mengompresi riwayat percakapan agar muat dalam batas token target tanpa menghapus instruksi inti sistem.
* **`compact_context_two_tier(messages, budget, ...)`**:
  * *Tingkat 1 (Pruning)*: Memotong teks hasil tool yang sudah lewat menjadi cuplikan ringkas (*truncated snippet*).
  * *Tingkat 2 (Summarization)*: Merangkum giliran tertua menjadi satu entri ringkasan terstruktur jika tingkat 1 belum mencukupi.

---

### 3.3 `estimate_tokens`

Fungsi deterministik untuk menghitung estimasi jumlah token teks secara cepat di RAM tanpa overhead jaringan.

```python
from LegionADK.runtime import estimate_tokens

tokens = estimate_tokens("Teks analisis arsitektur sistem.")
```

---

### 3.4 Kontrak Data Runtime

* **`SessionState`**: Objek status sesi beku yang melacak `session_id`, `history` (daftar pesan), serta `metadata`.
* **`TurnPolicy`**: Konfigurasi batasan giliran agen:
  * `max_tool_rounds: int = 5`: Batas maksimum pemanggilan tool bolak-balik dalam satu giliran.
  * `api_timeout_seconds: float = 60.0`: Batas waktu timeout panggilan API LLM per putaran.
  * `context_token_budget: Optional[int]`: Anggaran kuota token maksimum untuk konteks percakapan.
* **`TurnResult`**: Hasil akhir satu giliran yang memuat `status`, `content`, `reasoning`, `tool_results`, `prompt_tokens`, `cached_tokens`, `completion_tokens`, dan `session_state`.

---

## 4. Tools & RBAC Subsystem (`LegionADK.tools`)

Sistem pendaftaran perkakas in-memory dengan kontrol akses berbasis peran (RBAC), pembatasan risiko (*risk tier*), serta perlindungan luapan keluaran data masif (*Output Spill Guard*).

### 4.1 `register_tool`

Mendaftarkan tool kustom ke dalam registri in-memory ADK.

```python
from LegionADK.tools import ToolSpec, register_tool
```

#### Tanda Tangan:
```python
def register_tool(
    tool: Optional[ToolSpec] = None,
    *,
    name: str = "",
    description: str = "",
    parameters_schema: Optional[Dict[str, Any]] = None,
    risk_tier: Literal[0, 1, 2] = 0,
    handler: Optional[Callable[..., Any]] = None,
    allow_overwrite: bool = True,
) -> ToolSpec
```

#### Klasifikasi Tingkat Risiko (*Risk Tier*):
* `risk_tier = 0`: Operasi baca-saja (*read-only* / murni query). Aman dijalankan oleh Proposer secara paralel.
* `risk_tier = 1`: Operasi mutasi data lokal (menulis berkas, memperbarui graf). Dilarang saat agen berjalan secara paralel guna mencegah konflik konkurensi.
* `risk_tier = 2`: Operasi berisiko tinggi (eksekusi kode eksternal, modifikasi sistem kritis). Membutuhkan audit keamanan SmartGuardian tingkat lanjut.

#### Contoh Penggunaan:
```python
def hitung_estimasi(core_count: int) -> str:
    return f"Estimasi kapasitas: {core_count * 500} req/sec"

spec = register_tool(
    name="calc:estimate_capacity",
    description="Menghitung estimasi kapasitas server berdasarkan jumlah CPU core.",
    parameters_schema={
        "type": "object",
        "properties": {
            "core_count": {"type": "integer", "description": "Jumlah CPU core"}
        },
        "required": ["core_count"],
    },
    risk_tier=0,
    handler=hitung_estimasi,
)
```

---

### 4.2 `execute_registered_tool`

Mengeksekusi tool terdaftar melalui pipeline keamanan terpadu: **RBAC Check $\to$ Token Cancel Check $\to$ Argument Verification $\to$ Handler Call $\to$ Output Spill Guard**.

```python
from LegionADK.tools import execute_registered_tool

# Tanda Tangan Fungsi:
# async def execute_registered_tool(
#     spec: LLMSpec,
#     tool_name: str,
#     arguments: Optional[Dict[str, Any]] = None,
#     token: Optional[CancellationToken] = None,
# ) -> Tuple[bool, Any]

success, result = await execute_registered_tool(
    spec=architect_spec,
    tool_name="calc:estimate_capacity",
    arguments={"core_count": 8},
)
print("Status Keberhasilan:", success)
print("Hasil Eksekusi Tool:", result)
```

---

### 4.3 `authorize_tool_call`

Memvalidasi apakah seorang agen memiliki hak izin untuk memanggil tool tertentu berdasarkan aturan `tool_permissions` pada `LLMSpec`.

Mendukung pencocokan:
1. *Exact match*: `"calc:estimate_capacity"`
2. *Namespace wildcard*: `"calc:*"`
3. *Universal wildcard*: `"*"`

---

### 4.4 `guard_tool_output`

Mencegah ledakan token (*token explosion*) saat eksekusi tool menghasilkan luapan output besar (melebihi ambang batas default 50 KB). Teks otomatis dipotong dengan penanda aman, dan payload lengkap disimpan ke disk temporer.

```python
from LegionADK.tools import guard_tool_output

safe_output, spill_result = await guard_tool_output(huge_text_data)
```

---

### 4.5 Utilitas Manajemen Registri

* `list_registered_tools() -> List[ToolSpec]`: Mengembalikan seluruh tool yang aktif di registri.
* `get_registered_tool(name: str) -> Optional[ToolSpec]`: Mencari tool berdasarkan nama (*case-insensitive*).
* `unregister_tool(name: str) -> bool`: Menghapus tool dari registri.
* `clear_tool_registry() -> None`: Mengosongkan seluruh isi registri in-memory.

---

## 5. Gateway & Routing Layer (`LegionADK.gateway`)

Lapisan komunikasi ke penyedia model LLM (*foundation models*) dengan optimasi biaya, manajemen beban, dan perbaikan otomatis payload.

### 5.1 `ModelRouter`

Router inferensi multi-penyedia yang mengelola lalu lintas kuota RPM/TPM, penyeimbangan beban, *failover cascade*, serta pendinginan mandiri (*auto-cooldown*) saat terkena error HTTP 429/5xx.

```python
from LegionADK.gateway import ModelRouter

router = ModelRouter()
# Otomatis membaca konfigurasi dari berkas .env / model_list.json
```

#### Metode Kunci:
* `invoke(model_name, messages, tools, ...)`: Menjalankan pemanggilan inferensi asinkron ke model terbaik yang tersedia.
* `record_failure(provider, error_code)`: Mencatat kegagalan dan mengaktifkan isolasi pendinginan otonom.

---

### 5.2 `assemble_cached_system_prompt_from_spec`

Merakit prompt sistem statis agen dengan menempatkan pembatas `LEGION_CACHE_BOUNDARY` dan memverifikasi hash SHA-256 in-memory. Menjamin prompt sistem di atas pembatas 100% byte-stable sehingga memaksimalkan efisiensi *Prompt Caching* penyedia LLM.

```python
from LegionADK.gateway import assemble_cached_system_prompt_from_spec

full_system_prompt = assemble_cached_system_prompt_from_spec(
    spec=architect_spec,
    dynamic_context="Konteks dinamis tambahan yang berubah-ubah per giliran.",
)
```

---

### 5.3 `repair_malformed_tool_call` & `parse_and_repair_json`

Mesin penyembuh mandiri (*self-healing*) yang memperbaiki panggilan tool atau dokumen JSON yang terpotong oleh batasan token (`max_tokens`), memperbaiki kurung kurawal/siku yang hilang, membersihkan *trailing commas*, dan menormalkan tipe data Python/JavaScript.

```python
from LegionADK.gateway import parse_and_repair_json

broken_json = '{"targets": ["@cto", "@pm"], "note": "unfinished string'
repaired_dict = parse_and_repair_json(broken_json)
# Menghasilkan dict valid: {'targets': ['@cto', '@pm'], 'note': 'unfinished string'}
```

---

## 6. Governance & Security Layer (`LegionADK.governance`)

Sistem pengawasan keamanan, evaluasi risiko eksekusi aksi, dan pemutus sirkuit kegagalan.

### 6.1 `DeterministicVerifier`

Verifikator deterministik (*Chain-of-Verification*) yang memvalidasi integritas argumen tool sebelum dijalankan. Memastikan parameter berkas tidak keluar dari direktori kerja yang sah (*anti-path traversal*).

```python
from LegionADK.governance import DeterministicVerifier
from LegionADK.tools import get_registered_tool

# Inisialisasi dengan allowed_root
verifier = DeterministicVerifier(allowed_root=".")
tool_spec = get_registered_tool("fs:read_file")

# Verifikasi argumen secara asinkron
verdict = await verifier.verify(
    spec=architect_spec,
    tool=tool_spec,
    arguments={"path": "../../etc/passwd"},
    context_messages=None,
)
print("Boleh dieksekusi?", verdict.is_valid)  # False - Akses traversal ditolak
print("Alasan penolakan:", verdict.reason)
```

---

### 6.2 `SmartGuardian`

Pengawas keamanan berbasis analisis AST Python dan pola perilaku agen. Mendeteksi loop kosong yang berulang, pola injeksi instruksi berbahaya (*prompt injection*), dan menghasilkan laporan terstruktur `GuardianReport`.

```python
from LegionADK.governance import SmartGuardian

guardian = SmartGuardian()
# Memantau dan mencatat event perilaku setiap giliran agen secara otomatis
```

---

### 6.3 `ToolCircuitBreaker`

Sakelar proteksi yang melacak tingkat kegagalan tool pada penyedia layanan hulu (*upstream*). Jika sebuah tool mengalami kegagalan beruntun melebihi ambang batas, sirkuit terbuka (*CIRCUIT OPEN*) dan panggilan berikutnya langsung ditolak tanpa membebani layanan luar.

```python
from LegionADK.governance import ToolCircuitBreaker

breaker = ToolCircuitBreaker(threshold=3, reset_timeout=60.0)
```

---

## 7. Memory Layer: Local Knowledge Graph (`LegionADK.memory`)

Infrastruktur memori graf pengetahuan lokal berbasis Markdown yang bekerja mandiri di sistem berkas lokal tanpa dependensi pada server basis data eksternal.

### 7.1 `MarkdownGraphMemory`

Fasad terpadu yang memadukan seluruh fungsionalitas memori graf (Indexer, LockManager, Navigator, dan Mutator) ke dalam satu antarmuka yang bersih.

```python
from LegionADK.memory import MarkdownGraphMemory

memory = MarkdownGraphMemory(vault_root="./vault")
```

#### Metode Utama:
* `locate(query: str, top_k: int = 5) -> LocateResult`: Menemukan dokumen graf yang paling relevan berdasarkan pencarian istilah dan penelusuran relasi.
* `inspect_outline(document_slug: str) -> NodeOutline`: Membaca kerangka dokumen (daftar heading) tanpa memuat seluruh teks ke memori.
* `read_section(document_slug: str, heading: str) -> SectionPayload`: Membaca bagian/seksi spesifik dari dokumen secara hemat token.
* `learn_and_link(request: MutationRequest) -> MutationReceipt`: Menyimpan pengetahuan baru atau memperbarui dokumen yang sudah ada dengan penautan `[[Wiki-Links]]` timbal balik secara atomik.

---

### 7.2 `register_graph_memory_tools`

Mendaftarkan 4 perkakas standar graf memori ke dalam permission registry ADK secara instan berdasarkan jalur vault yang ditentukan:
1. `graph:locate` (Risk Tier 0)
2. `graph:inspect_outline` (Risk Tier 0)
3. `graph:read_section` (Risk Tier 0)
4. `graph:learn_and_link` (Risk Tier 1)

```python
from LegionADK.memory import register_graph_memory_tools

# Mendaftarkan tools memori langsung menggunakan vault_path
registered_tools = register_graph_memory_tools(vault_path="./vault")
```

---

### 7.3 `GraphIndexer`

Pengindeks dokumen Markdown lokal berbasis regex dan AST. Mengekstraksi metadata YAML frontmatter, tag `#topik`, tautan dua arah `[[target|alias]]`, dan menyusun relasi graf in-memory secara inkremental.

---

### 7.4 `GraphNavigator`

Mesin penelusuran relasi graf dokumen yang memanfaatkan algoritma Dijkstra dan Breadth-First Search (BFS) untuk menemukan rantai keterkaitan informasi antar-dokumen.

---

### 7.5 `GraphMutator`

Mutator dokumen Markdown yang aman terhadap *path traversal*, membersihkan nama slug, memutakhirkan frontmatter YAML, dan mengimplementasikan *Optimistic Concurrency Control (OCC)* berbasis hash untuk mencegah konflik penulisan konkuren.

---

### 7.6 `FileLockManager`

Pengelola kunci konkurensi berkas asinkron (*atomic file locking*) dengan batas waktu (*timeout*) dan pencegahan kebuntuan (*deadlock avoidance*) yang kompatibel dengan sistem berkas Windows (NTFS) dan POSIX.

```python
from LegionADK.memory import FileLockManager

lock_mgr = FileLockManager()
async with lock_mgr.acquire("path/to/doc.md"):
    # Operasi penulisan aman terhadap balapan proses antar-agen
    pass
```

---

## 🎯 Panduan Praktik Terbaik & Pola Penggunaan

1. **Gunakan `dispatch_envelope` sebagai Titik Masuk Utama**:
   Biarkan fasad orkestrator menentukan apakah sebuah pesan harus ditangani secara tunggal, melalui debat paralel, atau melalui triase otonom.
2. **Definisikan Izin Tool Minimal (*Principle of Least Privilege*)**:
   Hanya berikan izin `comm:delegate` atau `graph:learn_and_link` pada agen yang benar-benar memerlukan wewenang tersebut.
3. **Optimalkan Cache Hit dengan `soul_prompt` yang Statis**:
   Pastikan atribut `soul_prompt` dan `system_prompt` pada `LLMSpec` tidak berubah-ubah di waktu proses (*runtime*) agar mekanisme *Byte-Stable Prompt Caching Boundary* memberikan penghematan biaya token yang optimal (>90% Cache HIT).
