# Astraea-ADK — Contoh Kode Produksi & Pola Desain Siap Pakai

Berikut adalah implementasi end-to-end yang dapat disalin dan langsung dijalankan untuk berbagai kebutuhan proyek.

---

## Contoh 1: Executive Office Multi-Agent (Autonomous Triage + Delegasi)

Kasus: `@cos` menerima pertanyaan strategis, mendelegasikan analisis arsitektur ke `@cto` dan analisis produk ke `@pm`, lalu menyatukan hasilnya.

```python
import asyncio
from AstraeaADK import (
    AgentRoster,
    LLMSpec,
    OrchestrationPolicy,
    contract_message,
    dispatch_envelope,
)

# 1. Definisikan Roster Tim
roster = AgentRoster([
    LLMSpec(
        handle="@cos",
        agent_name="Chief of Staff",
        soul_prompt="Kamu adalah koordinator eksekutif yang berpikir sistemik dan tajam.",
        system_prompt=(
            "Tinjau masalah yang masuk. Identifikasi aspek teknis dan produk.\n"
            "Gunakan comm:delegate untuk menugaskan @cto (aspek teknis) dan @pm (aspek produk).\n"
            "Setelah menerima hasil dari spesialis, sintesiskan menjadi rencana aksi eksekutif."
        ),
        tool_permissions=["comm:delegate"],
    ),
    LLMSpec(
        handle="@cto",
        agent_name="Chief Technology Officer",
        soul_prompt="Kamu adalah arsitek sistem yang mengutamakan keandalan dan skalabilitas.",
        system_prompt="Berikan rekomendasi teknis konkret, risiko infrastruktur, dan estimasi beban.",
    ),
    LLMSpec(
        handle="@pm",
        agent_name="Head of Product",
        soul_prompt="Kamu adalah pemimpin produk yang fokus pada nilai pengguna dan kecepatan rilis.",
        system_prompt="Tentukan batasan rilis, prioritas fitur bertahap, dan mitigasi risiko bisnis.",
    ),
])

async def main():
    envelope = contract_message(
        sender="@ceo",
        target=["@cos"],
        content="Kita perlu meluncurkan fitur AI real-time recommendation di aplikasi mobile dalam 6 minggu.",
    )

    policy = OrchestrationPolicy(
        max_discussion_rounds=1,
        max_delegation_depth=2,
        proposer_timeout_seconds=45.0,
    )

    result = await dispatch_envelope(envelope=envelope, roster=roster, policy=policy)

    print(f"Status Orkestrasi: {result.status}")
    print(f"Mode Terpilih    : {result.mode}")
    print(f"Spesialis Aktif  : {result.proposer_handles}")
    print("\n=== KEPUTUSAN EKSEKUTIF ===")
    print(result.final_content)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Contoh 2: Agen Peneliti dengan Local Knowledge Graph Memory (Obsidian Vault)

Kasus: Agen mencari informasi di dalam folder catatan `.md`, membaca seksi relevan tanpa memuat seluruh dokumen, lalu menulis temuan baru dengan tautan dua-arah (`[[Wiki-Links]]`).

```python
import asyncio
from pathlib import Path
from AstraeaADK import (
    LLMSpec,
    SessionState,
    contract_message,
    execute_turn,
    register_graph_memory_tools,
)

vault_dir = Path("./my_knowledge_vault")
vault_dir.mkdir(exist_ok=True)

# 1. Hubungkan Memory Graph
memory = register_graph_memory_tools(vault_path=vault_dir)

# 2. Definisikan Peneliti
researcher_spec = LLMSpec(
    handle="@researcher",
    agent_name="Autonomous Research Agent",
    soul_prompt="Kamu adalah analis pengetahuan yang teliti dan berbasis fakta terdokumentasi.",
    system_prompt=(
        "Sebelum menjawab, selalu gunakan graph:locate untuk mencari catatan relevan.\n"
        "Gunakan graph:read_section untuk membaca seksi spesifik.\n"
        "Jika ada pengetahuan baru penting, gunakan graph:learn_and_link untuk mencatatnya."
    ),
    tool_permissions=["graph:*"],
)

async def main():
    state = SessionState(session_id="research_01")
    msg = contract_message(
        sender="@user",
        target="@researcher",
        content="Cari informasi tentang prosedur failover basis data dan catat jika ada update konfigurasi baru.",
    )

    turn = await execute_turn(spec=researcher_spec, envelope=msg, session_state=state)
    print("Hasil Riset:", turn.final_content)
    print("Tool Terpanggil:", [call["tool_name"] for call in turn.tool_history])

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Contoh 3: Integrasi MCP Filesystem Server dengan Real-Time Token Streaming

Kasus: Menghubungkan tool server MCP ke agen dan menyiarkan token jawaban kata-demi-kata ke terminal.

```python
import asyncio
from AstraeaADK import (
    LLMSpec,
    SessionState,
    StreamEvent,
    StreamEventType,
    contract_message,
    execute_turn,
    mount_mcp_server,
    unmount_mcp_tools,
)

async def on_stream(event: StreamEvent) -> None:
    if event.event_type == StreamEventType.TOKEN:
        print(event.delta, end="", flush=True)
    elif event.event_type == StreamEventType.THOUGHT:
        # Warna abu-abu untuk pemikiran internal
        print(f"\033[90m{event.delta}\033[0m", end="", flush=True)
    elif event.event_type == StreamEventType.TOOL_CALL:
        print(f"\n[Memanggil Tool: {event.tool_name}]...")

async def main():
    # 1. Pasang Server MCP
    receipt = await mount_mcp_server(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "./data_dir"],
        name_prefix="fs",
        risk_tier=1,
    )
    print(f"Tool MCP Aktif: {receipt.registered_tool_names}\n")

    spec = LLMSpec(
        handle="@assistant",
        agent_name="Filesystem Assistant",
        soul_prompt="Kamu adalah asisten pengelola data.",
        system_prompt="Gunakan tool fs:* untuk membaca atau menyusun berkas sesuai permintaan pengguna.",
        tool_permissions=["fs:*"],
    )

    state = SessionState(session_id="mcp_stream_demo")
    msg = contract_message(
        sender="@user",
        target="@assistant",
        content="Daftar berkas di direktori kerja dan buatkan ringkasan singkat dari salah satu berkas.",
    )

    try:
        result = await execute_turn(
            spec=spec,
            envelope=msg,
            session_state=state,
            on_event=on_stream,
        )
    finally:
        await unmount_mcp_tools(receipt.mount_id)

if __name__ == "__main__":
    asyncio.run(main())
```
