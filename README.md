# Astraea-ADK (`LegionADK`)

[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-pydantic%20%2B%20httpx-success.svg)]()
[![API Reference](https://img.shields.io/badge/docs-API%20Reference-blueviolet.svg)](documentation.md)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

**Astraea-ADK** (`LegionADK`) adalah runtime eksekusi agen tunggal dan multi-agen (*Mixture-of-Agents*) untuk Python. Inti framework ini dibangun hanya di atas pustaka standar Python, `pydantic>=2.0`, dan `httpx`—tanpa ketergantungan pada database vektor eksternal, server graf, maupun lapisan pembungkus (*wrapper*) prompt yang berat.

![Astraea ADK System Architecture](docs/assets/system_architecture.png)

---

## Masalah Teknis yang Diselesaikan

Framework agen umumnya bermasalah ketika dibawa ke beban kerja nyata karena empat hal:

1. **Invalidasi Prompt Cache Antar-Turn**: Menyisipkan konteks dinamis di tempat yang salah atau urutan deklarasi *tool* yang berubah-ubah membuat *prefix cache* pada penyedia LLM selalu meleset (*cache miss*).
2. **Konteks Membengkak karena Output Tool & RAG**: Membuang seluruh isi dokumen *skill* ke *system prompt* atau membiarkan satu panggilan *tool* mengembalikan ratusan kilobyte teks mentah langsung ke riwayat pesan.
3. **Biaya & Latensi Ekstraksi Memori**: Menggunakan panggilan LLM tambahan hanya untuk mengekstrak *entity/triple* pengetahuan atau meminta LLM mengulang panggilan ketika JSON `tool_calls` terpotong batas `max_tokens`.
4. **Konflik Tulis pada Agen Paralel**: Beberapa agen yang dieksekusi bersamaan melalui `asyncio.gather` memodifikasi state atau berkas yang sama tanpa penguncian (*locking*) dan tanpa kontrol konkurensi.

---

## Arsitektur & Mekanisme Internal

| Modul | Mekanisme Teknis |
| :--- | :--- |
| **`core/`** | Kontrak identitas `LLMSpec`, amplop komunikasi `MessageEnvelope`, dan `CancellationToken` (mendukung `pause()`/`resume()` terpisah dari `cancel()`). Seluruh struktur bersarang dikunci *immutable* menggunakan `MappingProxyType`. |
| **`gateway/`** | Memisahkan identitas statis dan konteks giliran dengan penanda `LEGION_CACHE_BOUNDARY` (diverifikasi via SHA-256), mengekspor skema *tool* secara terurut alfabetis, menangani *rate-limit* RPM/TPM beserta *cooldown failover* per provider, dan menambal JSON `tool_calls` yang terpotong dengan parser *stack LIFO* di RAM. |
| **`tools/`** | Registri *tool* in-memory dengan otorisasi RBAC (`exact`, `namespace:*`, `*` / `ALL`) dan **50 KB Output Spill Guard** (`51.200 bytes`) yang memotong luapan teks secara aman pada batas karakter UTF-8 multi-byte serta menyimpan output utuh ke disk. |
| **`governance/`** | `DeterministicVerifier` (CoV) memeriksa argumen *tool* berisiko (`risk_tier >= 1`) terhadap *path traversal* dan injeksi perintah sebelum dieksekusi, lalu mengembalikan pesan penolakan ke riwayat `role: "tool"` agar model melakukan *self-repair*. Dilengkapi `ToolCircuitBreaker` (berbasis hash tanda tangan panggilan) dan eskalasi sesi monoton via `SmartGuardian`. |
| **`runtime/`** | Siklus eksekusi 10 fase *stateless* (`execute_turn`) dengan kompresi konteks dua lapis di RAM (`compact_context_two_tier`): memangkas output *tool* lama menjadi ringkasan 1 baris (Tier 1) dan menggulung separuh riwayat terlama menjadi blok ringkasan (Tier 2) tanpa menyentuh jangkar *system prompt*. |
| **`memory/`** | **Autonomous Graph Memory** di atas folder berkas Markdown (`.md`). Memindai *frontmatter*, heading, dan `[[wikilink]]` dalam mode biner (`rb`), mencatat `(start_byte, end_byte)` setiap sub-bab, serta menyajikan pengetahuan dalam 3 langkah: pencarian pintu masuk dengan **Okapi BM25** (`graph:locate`), pembacaan struktur sub-bab di RAM (`graph:inspect_outline`), dan pembacaan irisan byte sub-bab via `seek()` (`graph:read_section`). |
| **`protocol/`** | Orkestrator multi-agen yang mendukung debat paralel (`run_moa_debate`), triase mandiri oleh koordinator (`run_autonomous_triage`), serta delegasi hierarkis berjenjang (*Strict Chain-of-Command*) dengan proteksi siklus tumpukan panggilan (*anti-cycle call stack guard*) dan pemblokiran *tool* mutasi (`risk_tier >= 1`) selama fase *brainstorming* paralel. |

---

## Instalasi & Konfigurasi

Instal paket distribusi biner menggunakan `pip`:

```bash
pip install astraea-adk


Salin berkas konfigurasi contoh examples/.env.example menjadi .env di direktori kerja Anda:
CUSTOM_PROVIDER_API_KEY=your_api_key_here
CUSTOM_PROVIDER_BASE_URL=[https://api.your-provider.com/v1](https://api.your-provider.com/v1)

TEST_PRIMARY_PROVIDER=custom
TEST_PRIMARY_MODEL=deepseek-v4.1-flash

# Opsional — Provider Resmi & Lokal:
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GEMINI_API_KEY=AIzaSy...
# OLLAMA_BASE_URL=http://localhost:11434/v1
# VLLM_BASE_URL=http://localhost:8000/v1


Contoh Penggunaan Cepat
1. Orkestrasi Multi-Agen & Strict Chain-of-Command (LegionADK.protocol)
Fungsi dispatch_envelope menganalisis target amplop dan memilih jalur eksekusi secara otomatis:
Triase Otonom (AUTONOMOUS_TRIAGE): Jika pesan dikirim ke satu koordinator (misal @cos atau @secretary), koordinator mengevaluasi direktori tim dan mendelegasikan tugas ke spesialis yang relevan.
Debat Eksplisit (EXPLICIT_MOA): Jika pesan ditujukan ke \ge 2 agen atau menyebut beberapa @handle, para Proposer berjalan paralel lalu disintesis oleh @Aggregator.
Agen Tunggal (STANDALONE): Jika pesan ditujukan ke satu agen biasa tanpa delegasi.
import asyncio
from LegionADK import (
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
        soul_prompt="Koordinator yang memetakan masalah ke kepala divisi terkait.",
        system_prompt="Gunakan comm:delegate untuk menugaskan analisis teknis ke @cto dan produk ke @pm.",
        tool_permissions=["comm:delegate"],
    ),
    LLMSpec(
        handle="@cto",
        agent_name="Chief Technology Officer",
        soul_prompt="Fokus pada keandalan sistem, isolasi proses, dan struktur data.",
        system_prompt="Berikan spesifikasi teknis yang terukur.",
        tool_permissions=["comm:delegate"],
    ),
    LLMSpec(
        handle="@pm",
        agent_name="Product Manager",
        soul_prompt="Fokus pada jadwal rilis, ruang lingkup fitur, dan mitigasi risiko bisnis.",
        system_prompt="Berikan batasan rilis dan prioritas eksekusi.",
    ),
])

async def main() -> None:
    env = contract_message(
        sender="@user",
        target=["@cos"],
        content="Rancang rencana mitigasi lonjakan beban API 300% tanpa menurunkan kualitas respons.",
    )

    result = await dispatch_envelope(
        envelope=env,
        roster=roster,
        policy=OrchestrationPolicy(
            max_discussion_rounds=1,
            max_delegation_depth=3,
            allow_proposer_tier1_mutations=False,
        ),
    )

    print(f"Mode & Status : {result.mode} | {result.status}")
    print(f"Proposers     : {list(result.proposer_handles)}")
    print(f"Token Usage   : prompt={result.total_prompt_tokens}, cached={result.total_cached_tokens}")
    print(result.final_content)

asyncio.run(main())


2. Autonomous Graph Memory (LegionADK.memory)
Mendaftarkan 4 tool navigasi dan penulisan pengetahuan di atas folder Markdown lokal (kompatibel dengan vault Obsidian maupun berkas SKILL.md open-source):
from pathlib import Path
from LegionADK import register_graph_memory_tools

# Mendaftarkan:
# 1. graph:locate (tier 0 - pencarian Okapi BM25 + peta tetangga 1-hop EXTRACTED > INFERRED)
# 2. graph:inspect_outline (tier 0 - daftar sub-bab, estimasi token, & content_hash di RAM)
# 3. graph:read_section (tier 0 - baca irisan byte sub-bab via seek() + 50KB spill guard)
# 4. graph:learn_and_link (tier 1 - tulis/append/replace atomik dengan OCC hash & Jaccard check)
memory = register_graph_memory_tools(
    vault_path=Path("./vault"),
    skill_gate=lambda session_id: True,
    max_mutations_per_session=5,
)

health = memory.check_health()
print(f"Nodes: {health.total_nodes}, Edges: {health.total_edges}, Orphans: {health.orphan_nodes}")


Menjalankan Skrip Contoh (examples/)
Repositori ini menyertakan 4 skrip contoh siap pakai di dalam direktori examples/:
Berkas
Deskripsi
examples/01_quickstart_moa_debate.py
Diskusi eksplisit multi-putaran antar-spesialis (run_moa_debate) yang disintesis oleh agregator.
examples/02_autonomous_triage.py
Triase mandiri oleh koordinator (run_autonomous_triage) dan pendelegasian berjenjang (Strict Chain-of-Command).
examples/03_secure_governance.py
Demonstrasi RBAC, penolakan path traversal oleh DeterministicVerifier (CoV), self-repair agen, dan eskalasi SmartGuardian.
examples/04_graph_memory.py
Penelusuran bertahap 3-lapis pada MarkdownGraphMemory dan penulisan pengetahuan baru secara atomik.

Jalankan contoh langsung dari terminal:
python examples/01_quickstart_moa_debate.py
python examples/02_autonomous_triage.py
python examples/03_secure_governance.py
python examples/04_graph_memory.py


Referensi lengkap seluruh kelas kontrak, tanda tangan fungsi, dan parameter tersedia di documentation.md.
Lisensi
Proyek ini dilindungi di bawah lisensi Proprietary & Confidential. Hak Cipta © Hillario RZA.
