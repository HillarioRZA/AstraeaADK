---
name: astraea-adk
description: >-
  Use this skill whenever the user wants to develop, build, configure, or debug AI agents and multi-agent workflows using the Astraea-ADK (AstraeaADK) framework. Provides the complete public API specifications, architectural patterns (Mixture-of-Agents, Autonomous Triage, Strict Chain-of-Command), Knowledge Graph Memory, MCP bridge, Governance (CoV, SmartGuardian), real-time streaming, and production code examples.
---

# Astraea-ADK (`AstraeaADK`) Developer Guide & Skill

**Astraea-ADK** adalah runtime dan framework orkestrasi multi-agen (*Mixture-of-Agents / MoA*) berperforma tinggi dan aman untuk Python (>=3.10). Keputusan orkestrasi bersifat probabilistik (digerakkan oleh LLM), sedangkan governance dan invariantnya deterministik: permission registry, verifikasi CoV, batas kedalaman delegasi, dan circuit breaker.
Distribusi PyPI: `pip install astraea-adk`
Nama paket impor Python: `import AstraeaADK`

Framework ini didesain **role-agnostic**, berbasis pustaka standar Python + `pydantic>=2.0` (`frozen=True`) + `httpx`, tanpa ketergantungan pada database vektor eksternal atau graph database berat.

---

## 🚀 Quick Navigation & Referensi Lengkap

- [Panduan Arsitektur & Mekanisme Internal](./references/architecture.md) — 10-phase pipeline, byte-stable prompt caching boundary, LIFO stack repair, two-tier compaction.
- [Katalog Lengkap API & Kontrak Data](./references/api_reference.md) — Tanda tangan lengkap seluruh fungsi, class, dan enum publik.
- [Boilerplate Siap Pakai & Pola Desain](./references/examples.md) — Template copy-pasteable untuk berbagai use-case produksi.

---

## 1. Konfigurasi Lingkungan (`.env`)

AstraeaADK otomatis membaca variabel lingkungan untuk gateway routing LLM:

```dotenv
# Kustom Endpoint (Ollama, vLLM, OpenRouter, TokenomixAI, dsb)
CUSTOM_PROVIDER_BASE_URL=https://api.your-provider.com/v1
CUSTOM_PROVIDER_API_KEY=your_api_key_here

# Model Default
TEST_PRIMARY_PROVIDER=custom
TEST_PRIMARY_MODEL=deepseek-v4.1-flash

# Provider Resmi (Opsional)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIzaSy...

# Proxy Korporasi (Dihormati otomatis & aman terhadap IPv6 [::1])
# HTTP_PROXY=http://proxy:8080
# HTTPS_PROXY=http://proxy:8080
# NO_PROXY=localhost,127.0.0.1,[::1]
```

---

## 2. Pola Alur Kerja Utama

### Pola A: Single-Agent Turn dengan Governance (`execute_turn`)

Gunakan ketika menjalankan satu agen mandiri dengan validasi keamanan dan batasan tool:

```python
import asyncio
from AstraeaADK import (
    LLMSpec,
    SessionState,
    contract_message,
    execute_turn,
    register_tool,
)

# 1. Daftarkan Tool
def cek_kuota(user_id: str) -> str:
    return f"Sisa kuota untuk {user_id}: 1500 kredit"

register_tool(
    name="billing:check_quota",
    description="Memeriksa sisa kuota pengguna berdasarkan user_id.",
    parameters_schema={
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
        "required": ["user_id"],
    },
    risk_tier=0,  # 0: Read-only, aman dijalankan paralel
    handler=cek_kuota,
)

# 2. Definisikan Agen
spec = LLMSpec(
    handle="@support",
    agent_name="Customer Support Agent",
    soul_prompt="Kamu adalah agen customer support yang ramah dan solutif.",
    system_prompt="Gunakan billing:check_quota untuk menjawab pertanyaan kuota.",
    tool_permissions=["billing:check_quota"],
)

async def main():
    state = SessionState(session_id="sess_123")
    msg = contract_message(sender="@user", target="@support", content="Berapa sisa kuota saya dengan ID usr_42?")
    
    result = await execute_turn(spec=spec, envelope=msg, session_state=state)
    print("Jawaban:", result.content)
    print("Status :", result.status)

asyncio.run(main())
```

---

### Pola B: Debat Multi-Putaran Eksplisit (`run_moa_debate`)

Gunakan ketika dua atau lebih spesialis perlu saling mengevaluasi ide (*cross-critique*) sebelum dirumuskan oleh seorang agregator/supervisor:

```python
import asyncio
from AstraeaADK import (
    AgentRoster,
    LLMSpec,
    OrchestrationPolicy,
    contract_message,
    run_moa_debate,
)

roster = AgentRoster([
    LLMSpec(
        handle="@cto",
        agent_name="CTO",
        soul_prompt="Fokus pada skalabilitas, latensi, dan kesederhanaan arsitektur.",
        system_prompt="Berikan solusi arsitektural yang tahan lonjakan trafik.",
    ),
    LLMSpec(
        handle="@pm",
        agent_name="Product Manager",
        soul_prompt="Fokus pada time-to-market, pengalaman pengguna, dan biaya rilis.",
        system_prompt="Berikan pertimbangan kepraktisan fitur dan jadwal rilis.",
    ),
    LLMSpec(
        handle="@supervisor",
        agent_name="Supervisor",
        soul_prompt="Arbiter netral yang menyeimbangkan trade-off.",
        system_prompt="Sintesiskan usulan @cto dan @pm menjadi satu keputusan final yang jelas.",
    ),
])

async def main():
    envelope = contract_message(
        sender="@user",
        target=["@cto", "@pm"],
        content="Bagaimana rencana migrasi database monolithic ke microservices tanpa downtime?",
    )

    result = await run_moa_debate(
        envelope=envelope,
        roster=roster,
        proposer_handles=["@cto", "@pm"],
        aggregator_handle="@supervisor",
        policy=OrchestrationPolicy(max_discussion_rounds=2),
    )

    print("=== SINTESIS AKHIR SUPERVISOR ===")
    print(result.final_content)

asyncio.run(main())
```

---

### Pola C: Triase Otonom & Pendelegasian Berjenjang (`run_autonomous_triage`)

Gunakan ketika koordinator (misal `@cos` / Chief of Staff) menganalisis masalah, membaca direktori tim secara mandiri, lalu memanggil tool delegasi `comm:delegate` untuk mendelegasikan tugas ke spesialis terkait:

```python
import asyncio
from AstraeaADK import (
    AgentRoster,
    LLMSpec,
    OrchestrationPolicy,
    contract_message,
    dispatch_envelope,
)

roster = AgentRoster([
    LLMSpec(
        handle="@cos",
        agent_name="Chief of Staff",
        soul_prompt="Koordinator eksekutif yang menganalisis kebutuhan tugas.",
        system_prompt="Tinjau masalah dan gunakan comm:delegate(targets=['@cto', ...], topic=...) untuk mendelegasikan.",
        tool_permissions=["comm:delegate"],
    ),
    LLMSpec(
        handle="@cto",
        agent_name="CTO",
        soul_prompt="Ahli infrastruktur dan keandalan sistem.",
        system_prompt="Analisis aspek teknis dan sampaikan rekomendasi konkret.",
        tool_permissions=["comm:delegate"],  # Mendukung hierarki berjenjang @cos -> @cto -> bawahan
    ),
    LLMSpec(
        handle="@security",
        agent_name="Head of Security",
        soul_prompt="Penjaga kepatuhan dan mitigasi celah keamanan.",
        system_prompt="Analisis aspek kerentanan dan privasi data.",
    ),
])

async def main():
    # dispatch_envelope otomatis mendeteksi target tunggal @cos dan mengaktifkan AUTONOMOUS_TRIAGE
    envelope = contract_message(
        sender="@user",
        target=["@cos"],
        content="Kami ingin membuka API publik untuk integrasi pembayaran pihak ketiga.",
    )

    result = await dispatch_envelope(
        envelope=envelope,
        roster=roster,
        policy=OrchestrationPolicy(
            max_discussion_rounds=1,
            max_delegation_depth=2,  # Batas kedalaman Strict Chain-of-Command
            allow_proposer_tier1_mutations=False,  # Cegah konflik tulis pada fase brainstorming paralel
        ),
    )

    print(f"Mode Operasi : {result.mode}")
    print(f"Proposers    : {list(result.proposer_handles)}")
    print(result.final_content)

asyncio.run(main())
```

---

### Pola D: Autonomous Graph Memory Lokal (Obsidian Vault Compatible)

Penyimpanan pengetahuan persisten lokal berbasis file Markdown dengan penelusuran 3 tahap (*progressive disclosure* hemat token hingga >95%):

```python
from pathlib import Path
from AstraeaADK import register_graph_memory_tools

# Mendaftarkan 4 tool ke registri:
# 1. graph:locate (Okapi BM25 di RAM + tetangga 1-hop)
# 2. graph:inspect_outline (daftar heading & byte range di RAM tanpa I/O)
# 3. graph:read_section (baca irisan byte via binary seek() + 50KB spill guard)
# 4. graph:learn_and_link (tulis atomik via FileLockManager, Jaccard dedup & OCC hash check)
memory = register_graph_memory_tools(
    vault_path=Path("./vault"),
    skill_gate=lambda session_id: True,
    max_mutations_per_session=5,
)

health = memory.check_health()
print(f"Knowledge Graph: {health.total_nodes} nodes, {health.total_edges} edges")
```

---

### Pola E: Model Context Protocol (MCP) Bridge

Memasang tool dari server MCP eksternal ke Permission Registry. Penting: bridge AstraeaADK **tidak men-spawn proses server**. Pemanggil menyediakan objek sesi MCP yang sudah terhubung (misalnya dari MCP client SDK, lewat transport stdio atau SSE) yang memiliki metode `list_tools()` dan `call_tool(name, arguments)`. Risk tier selalu ditetapkan oleh pemanggil, tidak pernah dibaca dari anotasi server.

```python
from AstraeaADK import mount_mcp_server, unmount_mcp_tools

async def setup_mcp(mcp_session):
    # mcp_session: sesi MCP yang SUDAH terhubung, disediakan aplikasi pemanggil
    receipt = await mount_mcp_server(
        "fs",  # namespace untuk tool MCP ini
        mcp_session,
        default_risk_tier=1,
    )
    print("Tool MCP terdaftar:", receipt.registered_tools)
    # Contoh: ('fs:list_directory', 'fs:read_file', 'fs:write_file')
    return receipt

def teardown_mcp(receipt):
    # unmount_mcp_tools bersifat sinkron (tanpa await); menerima MCPMountReceipt
    # atau string namespace dan mengembalikan jumlah tool yang dicopot
    removed = unmount_mcp_tools(receipt)
    print("Tool dicopot:", removed)
```

---

### Pola F: Real-Time Event & Token Streaming

Meneruskan token dan status eksekusi secara langsung ke UI/CLI tanpa memutus kontrak data statis. `StreamEventType` adalah alias `Literal` string, bukan Enum, jadi bandingkan `event.event_type` dengan string literalnya. Nilai yang valid: `TURN_STARTED`, `TOKEN_DELTA`, `TOOL_START`, `COV_REJECTED`, `TOOL_END`, `PROPOSER_DONE`, `AGGREGATOR_START`, `TURN_FINISHED`. Field `StreamEvent` hanya `event_type`, `agent_handle`, `delta` (potongan token, khusus TOKEN_DELTA), `detail` (nama tool, putaran debat, atau alasan penolakan CoV), dan `timestamp`.

```python
from AstraeaADK import StreamEvent, dispatch_envelope

async def stream_callback(event: StreamEvent) -> None:
    if event.event_type == "TOKEN_DELTA":
        print(event.delta, end="", flush=True)
    elif event.event_type == "TOOL_START":
        print(f"\n[Tool mulai] {event.detail}")
    elif event.event_type == "TOOL_END":
        print(f"\n[Tool selesai] {event.detail}")
    elif event.event_type == "COV_REJECTED":
        print(f"\n[CoV menolak tool] {event.detail}")

# Berikan callback ke on_event pada execute_turn, run_moa_debate, atau dispatch_envelope
result = await dispatch_envelope(envelope, roster, on_event=stream_callback)
```

---

## 3. Aturan Emas & Panduan Desain Agen AstraeaADK

1. **Gunakan `contract_message` untuk Seluruh Amplop**: Jangan instansiasi manual dictionary mentah; gunakan `contract_message` agar metadata, reply-to, dan id amplop terstandarisasi.
2. **Jaga `soul_prompt` dan `system_prompt` Statis**: AstraeaADK memverifikasi digest SHA-256 prompt statis untuk menjaga **Prompt Caching** penyedia LLM. Jangan sisipkan data yang dinamis/berubah per-turn ke dalam `soul_prompt`; kirimkan data dinamis lewat konten `MessageEnvelope`.
3. **Patuhi Tingkat Risiko Tool (*Risk Tier*)**:
   - `risk_tier=0`: Hanya baca/hitung (aman dipanggil paralel oleh banyak Proposer).
   - `risk_tier=1`: Mutasi berkas/data lokal (dilarang saat Proposer paralel; hanya diizinkan untuk agen tunggal atau Agregator).
   - `risk_tier=2`: Eksekusi eksternal/kritis (memerlukan pengawasan `SmartGuardian`).
4. **Gunakan `dispatch_envelope` sebagai Titik Masuk Universal**: Serahkan evaluasi mode (STANDALONE, EXPLICIT_MOA, AUTONOMOUS_TRIAGE) kepada facade dispatcher.
