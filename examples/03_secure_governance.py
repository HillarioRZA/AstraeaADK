"""
Contoh 3: Enterprise Security & Governance Guardrails
Menggunakan Astraea ADK (AstraeaADK)

Skenario:
Menunjukkan sistem pertahanan berlapis (defense-in-depth) Astraea ADK:
1. DeterministicVerifier: Mencegah manipulasi direktori kerja (path traversal).
2. ToolCircuitBreaker: Memutus otomatis tool yang gagal berulang kali untuk mencegah pemborosan kuota.
"""

import asyncio
from AstraeaADK import (
    DeterministicVerifier,
    ToolCircuitBreaker,
    CircuitBreakerOpenError,
)


async def main() -> None:
    print("=== Astraea ADK: Security & Governance Demo ===")

    # 1. DeterministicVerifier: Sandbox File System Guardrail
    verifier = DeterministicVerifier(allowed_root="./safe_workspace")

    print("\n[+] Menguji Deterministic Verifier terhadap Path Traversal:")

    # Kasus A: Akses di dalam safe_workspace (Legal)
    is_valid_a, clean_path_a = await verifier.verify("read_file", {"path": "./safe_workspace/report.txt"})
    print(f"  - Akses legal ('./safe_workspace/report.txt'): Valid={is_valid_a}")

    # Kasus B: Manipulasi Path Traversal ../ (Ilegal)
    is_valid_b, msg_b = await verifier.verify("read_file", {"path": "../../etc/passwd"})
    print(f"  - Akses ilegal ('../../etc/passwd'): Valid={is_valid_b} -> Dicegah: {msg_b}")

    # 2. ToolCircuitBreaker: Perlindungan Loop & Kegagalan API Beruntun
    print("\n[+] Menguji Tool Circuit Breaker:")
    breaker = ToolCircuitBreaker(threshold=3, reset_timeout=30.0)

    for i in range(1, 5):
        try:
            # Periksa apakah sirkuit mengizinkan pemanggilan
            breaker.record_attempt("weather_api")
            print(f"  - Panggilan ke-{i} diizinkan.")

            # Simulasikan API downstream timeout/error
            if i <= 3:
                print(f"    [!] Simulasi Error: API downstream timeout pada percobaan ke-{i}")
                breaker.record_failure("weather_api")

        except CircuitBreakerOpenError as e:
            print(f"    [X] CIRCUIT BREAKER AKTIF! Akses diputus: {e}")

    print("\n[+] Tata kelola keamanan berhasil memproteksi runtime.")


if __name__ == "__main__":
    asyncio.run(main())
