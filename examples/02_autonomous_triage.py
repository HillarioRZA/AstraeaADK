"""
Contoh 2: Autonomous Triage & Self-Delegation
Menggunakan Astraea ADK (LegionADK)

Skenario:
Agen koordinator / Chief of Staff (@cos) menerima masalah bisnis yang kompleks.
@cos secara mandiri menganalisis kebutuhan, membaca daftar direktori agen yang tersedia,
memanggil spesialis yang relevan via tool delegasi, dan menyintesis hasil akhirnya.
"""

import asyncio
import os
from pathlib import Path
from LegionADK import (
    LLMSpec,
    AgentRoster,
    OrchestrationPolicy,
    contract_message,
    run_autonomous_triage,
)

# Muat .env jika ada
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


async def main() -> None:
    print("=== Astraea ADK: Autonomous Triage Demo ===")

    model_cfg = {
        "provider": "openrouter",
        "model": "google/gemini-2.0-flash-001",
        "temperature": 0.2,
        "max_tokens": 1024,
    }

    # Definisikan Roster Lengkap Perusahaan
    spec_cos = LLMSpec(
        handle="@cos",
        agent_name="Chief of Staff",
        soul_prompt="Kamu adalah Chief of Staff eksekutif yang menganalisis persoalan dan mendelegasikan tugas ke spesialis yang tepat.",
        system_prompt="Analisis persoalan dari pengguna. Delegasikan ke spesialis yang relevan (@security, @finance, @legal) lalu buat ringkasan eksekutif.",
        model_settings=model_cfg,
    )

    spec_security = LLMSpec(
        handle="@security",
        agent_name="Head of Information Security",
        soul_prompt="Kamu adalah pakar keamanan siber tingkat ISO 27001 dan GDPR.",
        system_prompt="Berikan penilaian risiko keamanan dan langkah mitigasi dalam 3 poin tegas.",
        model_settings=model_cfg,
    )

    spec_finance = LLMSpec(
        handle="@finance",
        agent_name="Chief Financial Officer",
        soul_prompt="Kamu adalah CFO yang fokus pada efisiensi anggaran, ROI, dan proyeksi arus kas.",
        system_prompt="Berikan estimasi biaya dan dampak finansial secara terukur.",
        model_settings=model_cfg,
    )

    roster = AgentRoster([spec_cos, spec_security, spec_finance])

    # Amplop Masukan dari Pengguna
    envelope = contract_message(
        sender="@user",
        target=["@cos"],
        content="Kami berencana mengadopsi AI Generatif untuk analisis data nasabah prioritas perbankan.",
    )

    policy = OrchestrationPolicy(
        max_discussion_rounds=1,
        max_parallel_proposers=2,
    )

    print("\n[+] Menjalankan Autonomous Triage (@cos)...")
    result = await run_autonomous_triage(
        envelope=envelope,
        roster=roster,
        coordinator_handle="@cos",
        policy=policy,
    )

    print(f"\n[+] Status Eksekusi: {result.status}")
    print(f"[+] Total Token Dipakai: {result.total_tokens_used}")
    print("\n--- KEPUTUSAN & SINTESIS AKHIR (@cos) ---")
    print(result.final_text)


if __name__ == "__main__":
    asyncio.run(main())
