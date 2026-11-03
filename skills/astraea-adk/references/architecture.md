# Astraea-ADK — Panduan Arsitektur & Mekanisme Internal

Dokumen ini menjelaskan rancangan internal, siklus eksekusi, dan mekanisme deterministik yang membuat Astraea-ADK ringan, hemat token, dan tangguh di lingkungan produksi.

---

## 1. 10-Phase Deterministic Agent Turn Pipeline

Setiap interaksi giliran agen yang diproses oleh `execute_turn` melewati 10 fase yang terisolasi secara berurutan:

```
[Phase 1: Preflight Audit]
      │ Token budget & cancellation check
      ▼
[Phase 2: Assemble Cached Prompt]
      │ Byte-stable prefix check (SHA-256) via LEGION_CACHE_BOUNDARY
      ▼
[Phase 3: Watchdog Invocation]
      │ Request ke ModelRouter (dengan sliding window rate-limit & failover)
      ▼
[Phase 4: Tool Intent Detection & Self-Repair]
      │ LIFO stack repair menambal JSON terpotong (max_tokens truncation)
      ▼
[Phase 5: Pre-Execution Governance (CoV)]
      │ DeterministicVerifier memeriksa path traversal (..) & injection
      ▼
[Phase 6: Execution & 50KB Spill Guard]
      │ Eksekusi asinkron/thread + output spill guard (51.200 byte cutoff)
      ▼
[Phase 7: Circuit Breaker & Monotonic Escalation]
      │ Hash signature tracking & evaluasi SmartGuardian (WARN/TERMINATE)
      ▼
[Phase 8: Post-Execution Verification]
      │ Hasil tool dikemas ke riwayat pesan role="tool"
      ▼
[Phase 9: Context Compaction]
      │ Two-Tier compaction (Tier 1 potong output lama, Tier 2 gulung riwayat)
      ▼
[Phase 10: Turn Finalizer]
      │ Bekukan SessionState (frozen=True) dan hasilkan TurnResult
```

---

## 2. Byte-Stable Prompt Caching Boundary

### Masalah
Penyedia LLM (OpenAI, Anthropic, Gemini, DeepSeek) menawarkan diskon biaya hingga 90% untuk token prefix yang identik antar-panggilan (*Prompt Caching*). Jika urutan deklarasi tool berubah atau teks dinamis disisipkan di atas instruksi sistem, seluruh cache akan terinvalidasi (*cache miss*).

### Solusi AstraeaADK
- `LEGION_CACHE_BOUNDARY`: Penanda pemisah statis vs dinamis.
- Di atas batas: `soul_prompt` + `system_prompt` + skema tool yang diurutkan secara alfabetis deterministik. Hash SHA-256 diverifikasi pada RAM.
- Di bawah batas: Konteks dinamis giliran, riwayat percakapan, dan hasil eksekusi tool.
- Hasil terukur pada benchmark internal framework: prefix byte-stable 100% konsisten lintas 20 putaran. Tingkat cache hit aktual di sisi provider bergantung pada kebijakan dan pelaporan masing-masing provider, sehingga tidak digaransikan di dokumen ini.

---

## 3. Two-Tier Context Compaction

Mencegah pembengkakan jendela konteks pada percakapan panjang tanpa membuang instruksi penting:

1. **Tier 1 (Tool Output Pruning)**:
   Output tool dari putaran sebelumnya diringkas menjadi ringkasan 1 baris (`[Output ringkas: ... (hasil lengkap tersimpan)]`).
2. **Tier 2 (History Folding)**:
   Jika total token masih mendekati budget, separuh riwayat percakapan terlama digulung menjadi satu blok ringkasan sistem.
3. **Immutability of Anchor**:
   Pesan pertama (system prompt dan instruksi awal) tidak pernah dibuang atau diubah.

---

## 4. LIFO Stack Self-Healing Tool Repair

Ketika LLM terpotong pada batas `max_tokens` di tengah panggilan tool JSON:
- Alih-alih membuang token dan memanggil LLM ulang (*retry request*), AstraeaADK menggunakan parser stack LIFO di RAM.
- Memperbaiki kurung kurawal/siku yang tidak tertutup, membersihkan *trailing commas*, serta menormalkan literal Python (`True`, `False`, `None`) menjadi format JSON standar.
- Pengujian benchmark membuktikan 50/50 sampel JSON rusak pulih dalam 16 ms dengan 0 token LLM tambahan.

---

## 5. Strict Chain-of-Command & Anti-Cycle Guard

Pada orkestrasi bertingkat (misal `@cos` $\rightarrow$ `@cto` $\rightarrow$ `@engineer`):
- **Call Stack Tracking**: Setiap amplop membawa tuple riwayat pemanggil `active_call_stack`.
- **Anti-Cycle Guard**: Jika agen bawahan mencoba mendelegasikan kembali ke agen yang sudah ada di stack pemanggil (misal `@cto` memanggil `@cos` kembali), sistem langsung mendeteksi siklus dan membatalkan rekursi.
- **Max Delegation Depth**: Kedalaman delegasi dibatasi keras oleh `max_delegation_depth` pada `OrchestrationPolicy`.
- **Parallel Mutation Lock**: Selama fase brainstorming paralel (Proposer), pemanggilan tool mutasi (`risk_tier >= 1`) otomatis dicegah agar tidak terjadi konflik data (*race condition*).
