# Astraea ADK (LegionADK)
### Enterprise-Grade Mixture-of-Agents (MoA) Orchestration & Autonomous Agent Development Kit

[![PyPI version](https://img.shields.io/badge/pypi-v1.0.0-blue.svg)](https://pypi.org/project/astraea-adk/)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2%20(frozen=True)-green.svg)](https://docs.pydantic.dev/)
[![Binary Wheel](https://img.shields.io/badge/distribution-C--Extension%20Native%20Binary-darkviolet.svg)]()
[![Architecture](https://img.shields.io/badge/architecture-Role--Agnostic%20MoA-orange.svg)]()
[![Checkpoints](https://img.shields.io/badge/test%20suite-O1--O12%20PASS%20100%25-brightgreen.svg)]()
[![API Documentation](https://img.shields.io/badge/docs-API%20Reference-informational.svg)](documentation.md)
[![License](https://img.shields.io/badge/license-Proprietary%20%26%20Confidential-red.svg)](LICENSE)

**Astraea ADK (`LegionADK`)** adalah framework dan runtime tingkat enterprise untuk perancangan, orkestrasi, tata kelola keamanan (*governance*), memori graf lokal (*local graph memory*), serta komunikasi sistem multi-agen berbasis **Mixture-of-Agents (MoA)**.

Dirancang dari nol dengan fokus pada determinisme matematis, pencegahan balapan data (*race condition*), efisiensi biaya inferensi token LLM, dan keandalan tingkat produksi (*production-grade resilience*).

---

## 📑 Daftar Isi

- [🚀 Instalasi](#-instalasi)
- [🏗 Arsitektur Sistem (Layer Breakdown)](#-arsitektur-sistem-layer-breakdown)
- [✨ Fitur Utama (Core Highlights)](#-fitur-utama-core-highlights)
- [📖 Dokumentasi Lengkap API (documentation.md)](documentation.md)
- [💡 Panduan Penggunaan Cepat (Quickstart)](#-panduan-penggunaan-cepat-quickstart)
  - [1. Cara 1: Diskusi Multi-Putaran Eksplisit (run_moa_debate)](#1-cara-1-diskusi-multi-putaran-eksplisit-run_moa_debate)
  - [2. Cara 2: Triase Otonom & Pendelegasian Mandiri (run_autonomous_triage)](#2-cara-2-triase-otonom--pendelegasian-mandiri-run_autonomous_triage)
  - [3. Tata Kelola Keamanan & Circuit Breaker (Governance)](#3-tata-kelola-keamanan--circuit-breaker-governance)
- [📁 Folder Contoh (Examples)](#-folder-contoh-examples)
- [🛡 Distribusi & Lisensi](#-distribusi--lisensi)

---

## 🚀 Instalasi

Astraea ADK didistribusikan secara resmi via PyPI dalam format **Protected Machine Binary Wheels** (C-Extension native `.pyd` untuk Windows dan `.so` untuk Linux & macOS) yang teroptimasi performa tinggi dan aman:

```bash
pip install astraea-adk
```

### Kebutuhan Sistem:
* Python 3.10, 3.11, atau 3.12 (64-bit)
* Sistem Operasi: Linux (x86_64), Windows (x86_64), atau macOS (x86_64 / Apple Silicon ARM64)
* Kunci API LLM (OpenAI, Anthropic, Gemini, Groq, atau OpenRouter)

---

## 🏗 Arsitektur Sistem (Layer Breakdown)

![Astraea ADK System Architecture](docs/assets/system_architecture.png)

Astraea ADK dibangun dengan arsitektur 5-lapisan modular dengan batas tanggung jawab (*separation of concerns*) yang terisolasi ketat:

### 1. Protocol Layer (MoA Orchestration Engine)
* **MoA Orchestration**: Mengelola eksekusi Mixture-of-Agents adaptif. Agen koordinator menganalisis persoalan secara mandiri, membagi peran, dan mendistribusikan tugas ke spesialis terkait.
* **Multi-Agent Debate**: Memfasilitasi pertukaran ide, sintesis kompromi, dan evaluasi silang (*cross-critique*) multi-putaran antar-spesialis sebelum draf akhir disatukan kembali oleh peran agregator.
* **Strict Chain-of-Command**: Mengatur hierarki delegasi berjenjang (atasan ke bawahan) dengan batas kedalaman eksekusi terkontrol, pelacakan tumpukan panggilan (*call stack tracking*), serta pencegahan siklus delegasi (*anti-cycle protection*).

### 2. Runtime Layer (10-Phase Agent Turn Engine)
* **10-Phase Turn Pipeline**: Menjalankan setiap interaksi giliran agen melalui tahapan deterministik—mulai dari audit tata kelola awal (*preflight*), perakitan prompt dinamis, pemanggilan model terawasi (*watchdog invocation*), eksekusi aksi, evaluasi keamanan pasca-eksekusi, hingga finalisasi status.
* **Context Compaction & Token Budgeting**: Pengelolaan kuota token proaktif dengan strategi reduksi riwayat dua tingkat (*summarization & eviction*), menjaga relevansi konteks percakapan panjang tanpa melampaui jendela konteks model.
* **Immutable State Transitions**: Menjamin seluruh manipulasi status percakapan bersifat beku (*immutable frozen state*), mencegah mutasi data yang tidak terduga antar-giliran.

### 3. Gateway Layer (Resilient I/O & Routing)
* **Model Router & Load Balancer**: Manajemen lalu lintas inferensi multi-penyedia dengan isolasi kuota RPM/TPM, *failover cascade* otomatis, dan pemulihan mandiri (*auto-cooldown*) saat terjadi batasan laju (*rate-limiting*).
* **Byte-Stable Cache Boundary**: Segmentasi prompt statis dan dinamis dengan verifikasi hash deterministik untuk memastikan efisiensi biaya tertinggi dan retensi *prompt caching* penyedia LLM (>90% Cache HIT).
* **Self-Healing Tool Repair**: Mekanisme penanganan anomali otomatis yang mampu memperbaiki payload JSON yang terpotong atau mengalami inkonsistensi sintaks sebelum diproses lebih lanjut.

### 4. Governance Layer (Security & Guardrails)
* **Deterministic Verifier**: Validasi parametrik ketat terhadap seluruh aksi agen sebelum dieksekusi, mencegah manipulasi batas direktori kerja (*path traversal*) dan akses file ilegal.
* **Smart Guardian**: Mesin audit perilaku agen secara *real-time* untuk mengevaluasi risiko eksekusi kode berbahaya, manipulasi instruksi (*prompt injection*), dan pola loop anomali.
* **Circuit Breaker**: Pemutus otomatis akses tool eksternal saat terjadi kegagalan beruntun guna mencegah pembengkakan biaya dan kehabisan kuota API.

### 5. Memory Layer (Dual-Layer Persistent Graph Memory)
* **Local Graph Memory Engine**: Penyimpanan relasional lokal bebas ketergantungan database eksternal berbasis Obsidian-compatible markdown vault dan indeks graf atomic.
* **Bidirectional Relationship Index**: Pencarian asosiatif multivariat dengan traversal kedalaman kustom untuk menyajikan konteks memori yang tajam dan relevan.
* **Atomic File Locking**: Penguncian berkas konkurensi tingkat proses untuk menjamin integritas data memori pada pemanggilan paralel multi-agen.

---

## 💡 Panduan Penggunaan Cepat (Quickstart)

### 1. Cara 1: Diskusi Multi-Putaran Eksplisit (`run_moa_debate`)

Dua atau lebih agen spesialis berdiskusi mencari kompromi terbaik, disintesis oleh agregator:

```python
import asyncio
from LegionADK import (
    LLMSpec,
    AgentRoster,
    OrchestrationPolicy,
    contract_message,
    run_moa_debate,
)

async def main():
    model_cfg = {"provider": "openrouter", "model": "google/gemini-2.0-flash-001"}

    # 1. Definisikan Spesifikasi Agen
    spec_cto = LLMSpec(handle="@cto", agent_name="CTO", model_settings=model_cfg)
    spec_pm = LLMSpec(handle="@pm", agent_name="PM", model_settings=model_cfg)
    spec_supervisor = LLMSpec(handle="@supervisor", agent_name="Supervisor", model_settings=model_cfg)

    roster = AgentRoster([spec_cto, spec_pm, spec_supervisor])

    # 2. Siapkan Amplop Pesan & Kebijakan
    envelope = contract_message(
        sender="@user",
        target=["@cto", "@pm"],
        content="Bagaimana strategi migrasi basis data core banking tanpa downtime?",
    )

    # 3. Jalankan MoA Debate (2 Putaran + 1 Sintesis)
    result = await run_moa_debate(
        envelope=envelope,
        roster=roster,
        proposer_handles=["@cto", "@pm"],
        aggregator_handle="@supervisor",
        policy=OrchestrationPolicy(max_discussion_rounds=2),
    )

    print("Hasil Sintesis:", result.final_text)

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 2. Cara 2: Triase Otonom & Pendelegasian Mandiri (`run_autonomous_triage`)

Agen Chief of Staff (`@cos`) secara mandiri memeriksa direktori agen, memilih siapa yang perlu diajak berkolaborasi, dan merumuskan keputusan akhir:

```python
import asyncio
from LegionADK import (
    LLMSpec,
    AgentRoster,
    OrchestrationPolicy,
    contract_message,
    run_autonomous_triage,
)

async def main():
    model_cfg = {"provider": "openrouter", "model": "google/gemini-2.0-flash-001"}

    spec_cos = LLMSpec(handle="@cos", agent_name="Chief of Staff", model_settings=model_cfg)
    spec_sec = LLMSpec(handle="@security", agent_name="Security Head", model_settings=model_cfg)
    spec_fin = LLMSpec(handle="@finance", agent_name="CFO", model_settings=model_cfg)

    roster = AgentRoster([spec_cos, spec_sec, spec_fin])

    envelope = contract_message(
        sender="@user",
        target=["@cos"],
        content="Kami ingin meluncurkan fitur AI payment di aplikasi mobile perbankan.",
    )

    result = await run_autonomous_triage(
        envelope=envelope,
        roster=roster,
        coordinator_handle="@cos",
        policy=OrchestrationPolicy(max_discussion_rounds=1),
    )

    print("Keputusan Eksekutif:", result.final_text)

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 3. Tata Kelola Keamanan & Circuit Breaker (Governance)

```python
from LegionADK import DeterministicVerifier, ToolCircuitBreaker

# 1. Deterministic Sandbox Guardrail (Anti-Path Traversal)
verifier = DeterministicVerifier(allowed_root="./safe_workspace")
is_valid, clean_path = await verifier.verify("read_file", {"path": "./safe_workspace/data.csv"})

# 2. Tool Circuit Breaker (Anti-Runaway Loops)
breaker = ToolCircuitBreaker(threshold=3, reset_timeout=60.0)
breaker.record_attempt("external_api")
```

---

## 📁 Folder Contoh (Examples)

Kunjungi folder [`examples/`](examples/) untuk melihat implementasi skrip demonstrasi mandiri:
* [`examples/01_quickstart_moa_debate.py`](examples/01_quickstart_moa_debate.py) - Implementasi multi-round debate antar 2 agen spesialis & 1 arbiter.
* [`examples/02_autonomous_triage.py`](examples/02_autonomous_triage.py) - Triase dinamis berbasis tool pemanggilan delegasi `@cos`.
* [`examples/03_secure_governance.py`](examples/03_secure_governance.py) - Pembuktian pertahanan sandbox dan circuit breaker.
* [`examples/04_graph_memory.py`](examples/04_graph_memory.py) - Mesin memori graf lokal persisten (Obsidian-compatible vault, BM25 progressive disclosure, & relasi wikilink dua-arah).

---

## 🛡 Distribusi & Lisensi

Astraea ADK dilindungi oleh lisensi kepemilikan tertutup (*Proprietary and Confidential*). 
Seluruh komponen komputasi runtime didistribusikan dalam format binary mesin C terproteksi. 
Lihat berkas [LICENSE](LICENSE) untuk ketentuan hak cipta dan penggunaan.