"""
Contoh 1: Multi-Agent Mixture-of-Agents (MoA) Debate
Menggunakan Astraea ADK (AstraeaADK)

Skenario:
Dua agen spesialis (@cto dan @pm) berdiskusi dalam beberapa putaran 
untuk merumuskan solusi optimal terkait migrasi sistem perbankan.
Argumen dari kedua spesialis disintesis oleh agen agregator (@supervisor).
"""

import asyncio
import os
from pathlib import Path
from AstraeaADK import (
    LLMSpec,
    AgentRoster,
    OrchestrationPolicy,
    contract_message,
    run_moa_debate,
)

# 1. Muat .env jika ada
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


async def main() -> None:
    print("=== Astraea ADK: Multi-Agent MoA Debate Demo ===")

    # Konfigurasi LLM Settings
    model_cfg = {
        "provider": "openrouter",
        "model": "google/gemini-2.0-flash-001",
        "temperature": 0.3,
        "max_tokens": 1024,
    }

    # 2. Definisikan Roster Agen Spesialis
    spec_cto = LLMSpec(
        handle="@cto",
        agent_name="Chief Technology Officer",
        soul_prompt="Kamu adalah CTO yang mengutamakan reliabilitas, zero-downtime, dan keamanan.",
        system_prompt="Berikan perspektif teknis arsitektur dan mitigasi risiko downtime.",
        model_settings=model_cfg,
    )

    spec_pm = LLMSpec(
        handle="@pm",
        agent_name="Product Manager",
        soul_prompt="Kamu adalah PM yang berorientasi pada time-to-market, pengalaman pengguna, dan biaya.",
        system_prompt="Berikan perspektif bisnis, target rilis kuartal ini, dan dampak terhadap user.",
        model_settings=model_cfg,
    )

    spec_supervisor = LLMSpec(
        handle="@supervisor",
        agent_name="Executive MoA Synthesizer",
        soul_prompt="Kamu adalah penengah objektif yang menggabungkan keunggulan teknis dan kebutuhan bisnis.",
        system_prompt="Sintesiskan titik temu kompromi terbaik dari argumen @cto dan @pm dalam poin terstruktur.",
        model_settings=model_cfg,
    )

    roster = AgentRoster([spec_cto, spec_pm, spec_supervisor])

    # 3. Buat Amplop Pesan Masukan
    envelope = contract_message(
        sender="@user",
        target=["@cto", "@pm"],
        content="Bagaimana strategi migrasi basis data core banking dari monolitik ke microservices tanpa downtime?",
    )

    # 4. Jalankan MoA Debate (2 Putaran Diskusi + 1 Sintesis Akhir)
    policy = OrchestrationPolicy(
        max_discussion_rounds=2,
        max_parallel_proposers=4,
        allow_proposer_tier1_mutations=False,  # Proposer paralel dilarang mutasi data berbahaya
    )

    print("\n[+] Memulai orkestrasi MoA debate...")
    result = await run_moa_debate(
        envelope=envelope,
        roster=roster,
        proposer_handles=["@cto", "@pm"],
        aggregator_handle="@supervisor",
        policy=policy,
    )

    # 5. Tampilkan Hasil Sintesis
    print(f"\n[+] Status Eksekusi: {result.status}")
    print(f"[+] Total Putaran Diskusi: {result.rounds_executed}")
    print(f"[+] Total Token Dipakai: {result.total_tokens_used}")
    print("\n--- HASIL SINTESIS AKHIR (@supervisor) ---")
    print(result.final_text)


if __name__ == "__main__":
    asyncio.run(main())
