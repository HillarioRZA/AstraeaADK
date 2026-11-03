"""
Contoh 4: Local Knowledge Graph Memory
Menggunakan Astraea ADK (AstraeaADK)

Skenario:
Astraea ADK menyediakan mesin memori graf lokal persisten berformat Obsidian-compatible markdown vault:
1. GraphIndexer: Membaca vault markdown lokal dan membentuk indeks graf relasi antar-catatan ([[WikiLink]]).
2. GraphMutator: Menulis memori baru atau memperbarui seksi catatan secara atomik dengan perlindungan balapan data (FileLockManager).
3. GraphNavigator: Melakukan pencarian topik cerdas (BM25) dan penelusuran graf multi-hop (1-hop & multi-hop neighbours).
4. register_graph_memory_tools: Mendaftarkan 4 tool otonom agar agen LLM dapat membaca dan menulis memori secara mandiri.
"""

import asyncio
from pathlib import Path
from AstraeaADK import (
    GraphIndexer,
    GraphMutator,
    GraphNavigator,
    FileLockManager,
    MutationRequest,
    register_graph_memory_tools,
)


async def main() -> None:
    print("=== Astraea ADK: Local Knowledge Graph Memory Demo ===")

    vault_dir = Path("./sample_vault")
    vault_dir.mkdir(exist_ok=True)

    # 1. Inisialisasi Komponen Sub-Sistem Memori Graf
    lock_mgr = FileLockManager()
    indexer = GraphIndexer(vault_dir)
    mutator = GraphMutator(indexer=indexer, lock_manager=lock_mgr)
    navigator = GraphNavigator(indexer)

    print("\n[+] 1. Menulis Catatan Pengetahuan Awal (Mutator)...")

    # Catatan 1: Arsitektur Gateway
    req_gateway = MutationRequest(
        session_id="session-init",
        folder="architecture",
        title="Gateway Overview",
        note_type="note",
        mode="create",
        content=(
            "# Gateway Overview\n\n"
            "Gerbang inferensi multi-provider dengan sistem isolasi kuota RPM/TPM.\n"
            "Terhubung erat dengan sistem proteksi [[governance/circuit-breaker]].\n"
        ),
        linked_nodes=("governance/circuit-breaker",),
    )
    res1 = await mutator.learn_and_link(req_gateway)
    print(f"  - Node 1 dibuat: {res1.node_id} (Status: {res1.action_taken})")

    # Catatan 2: Circuit Breaker Governance
    req_breaker = MutationRequest(
        session_id="session-init",
        folder="governance",
        title="Circuit Breaker",
        note_type="note",
        mode="create",
        content=(
            "# Circuit Breaker\n\n"
            "Mencegah pemborosan kuota LLM saat endpoint upstream mengalami error berulang kali.\n"
            "Dipicu otomatis oleh kegagalan koneksi di [[architecture/gateway-overview]].\n"
        ),
        linked_nodes=("architecture/gateway-overview",),
    )
    res2 = await mutator.learn_and_link(req_breaker)
    print(f"  - Node 2 dibuat: {res2.node_id} (Status: {res2.action_taken})")

    # 2. Re-Index & Telusuri Hubungan Graf Dua-Arah (Bidirectional Backlinks)
    print("\n[+] 2. Menelusuri Relasi Graf (Navigator)...")
    indexer.build_full_index()

    gateway_node = indexer.get_node("architecture/gateway-overview")
    if gateway_node:
        print(f"  - Node Terpilih: {gateway_node.title}")
        print(f"  - Outgoing Links (Forward): {list(gateway_node.outgoing_links)}")

    # 3. Pencarian Berbasis Progressive Disclosure (BM25)
    print("\n[+] 3. Pencarian Topik Relevan (Progressive Disclosure)...")
    locate_result = navigator.locate(query="circuit breaker kuota", max_candidates=3)
    for cand in locate_result.candidates:
        print(f"  - Ditemukan: {cand.node_id} ({cand.title})")

    # 4. Registrasi 4 Autonomous Memory Tools untuk Agen LLM
    print("\n[+] 4. Mendaftarkan Tool Memori Otonom untuk LLM...")
    memory_facade = register_graph_memory_tools(vault_path=vault_dir)
    print("  - 4 Tool otonom berhasil didaftarkan ke sistem:")
    print("    * graph:locate (Pencarian topik via BM25)")
    print("    * graph:inspect_outline (Inspeksi struktur dokumen tanpa boros token)")
    print("    * graph:read_section (Lazy-read seksi spesifik via seek biner)")
    print("    * graph:learn_and_link (Menulis memori baru dengan relasi wikilink)")

    print("\n[+] Selesai: Sistem memori graf lokal persisten berfungsi optimal.")


if __name__ == "__main__":
    asyncio.run(main())
