# Benchmark Astraea-ADK

Dokumen ini memuat dua keluarga pengukuran yang **tidak boleh dicampur**:

1. **Pilar A mengukur framework.** Efisiensi mesin Astraea-ADK (waktu import, overhead per giliran, stabilitas cache, efisiensi token graph memory, pemulihan JSON) dengan mock LLM 0 ms, sehingga yang terukur adalah kode framework, bukan kecepatan atau kemampuan provider.
2. **Benchmark dataset asli mengukur model yang tersalurkan melalui harness.** BFCL v3, TAU-bench, dan LOCOMO dijalankan terhadap dataset resmi masing-masing. Angka pada bagian ini terutama mencerminkan kemampuan model yang dipakai; kontribusi framework adalah harness-nya (registri tool, izin, verifikasi, graph memory) dan apakah harness itu menghambat atau membantu model.

Seluruh pengukuran dilakukan pada **3 November 2026** terhadap paket distribusi `astraea-adk` **1.5.1** yang terpasang dari PyPI (bukan build lokal), Python 3.12, pada VM bersama (shared CPU). Bagian live memakai model `deepseek-v4.1-flash-1017` via gateway OpenAI-compatible, temperature 0.0. Skrip reproduksi tersedia di folder [`benchmarks/`](benchmarks/).

Hasil suite internal (Pilar A + skenario pemodelan Pilar B) versi sebelumnya tetap tercatat di [README](README.md#hasil-benchmark). Dokumen ini adalah catatan pengukuran 1.5.1.

---

## 1. Pilar A: Efisiensi Mesin (diukur ulang pada 1.5.1)

| Kode | Benchmark | Hasil Pengukuran 1.5.1 | Status |
| :---: | :--- | :--- | :---: |
| **E1** | Cold-Start Import & RAM Footprint | `1052.88 ms \| Peak RAM: 10.16 MB` | **PASS (< 50 MB)** |
| **E2** | 10-Phase Engine Overhead (100 Tool Turns) | `1039.1 ms total (10.39 ms/turn)` | **PASS** |
| **E3** | Byte-Stable Prefix & Tool Cache Retention | `100% Identik Lintas 20 Turn` | **PASS (0 Drift)** |
| **E4** | Progressive Disclosure Token Efficiency | `Baca 20/42872 tok (Hemat 99.95%, 16.5ms)` | **PASS (> 95% Hemat)** |
| **E5** | LIFO Stack Malformed JSON Recovery (50x) | `50/50 Pulih \| 16.84 ms \| 0 LLM Retry Tok` | **PASS (100% Pulih)** |

Metode identik dengan yang dijelaskan di README. Angka latensi diukur pada VM bersama dan akan lebih cepat pada hardware lokal atau server khusus; E2 khususnya dibaca sebagai orde besaran (sekitar 10 ms per giliran), bukan konstanta.

### Efisiensi token orkestrasi (perbandingan indikatif)

Pada tugas sintesis multi-agen yang identik (mode AUTONOMOUS_TRIAGE, model `deepseek-v4.1-flash-1017`, temperature 0.2, 2 run per sisi, semua jawaban benar):

| Sistem | Rata-rata Prompt Token |
| :--- | ---: |
| Astraea-ADK 1.5.0 (jalur delegasi MoA) | 13.048 |
| Astraea-ADK 1.0.1 (jalur delegasi MoA) | 16.202 |
| LangGraph (run delegasi yang sebanding) | 11.123 |

Sampel ini kecil (n=2 per sisi) dan latensinya didominasi variansi provider, sehingga tabel ini dibaca sebagai indikasi efisiensi token jalur delegasi, bukan klaim keunggulan umum.

---

## 2. BFCL v3 (dataset resmi): 93,0%

- **Cakupan:** 200 soal pertama yang deterministik dari dataset resmi Berkeley Function Calling Leaderboard v3: kategori `simple` 100 soal dan `multiple` 100 soal. Berkas soal dan jawaban diambil dari mirror HuggingFace resmi penyelenggara (`gorilla-llm/Berkeley-Function-Calling-Leaderboard`).
- **Metode:** setiap soal dijalankan lewat jalur turn standar Astraea (`execute_turn`), model `deepseek-v4.1-flash-1017`, temperature 0.0. Penilaian memakai pencocokan AST terhadap jawaban yang dianggap sah oleh dataset, sebagaimana metodologi resmi BFCL untuk kategori single-turn.
- **Hasil:** **93,0% (186/200)**; simple 93,0% (93/100), multiple 93,0% (93/100). Interval kepercayaan 95% kira-kira ±3,5 poin. Waktu total 910,2 detik; pemakaian token 593.392 prompt + 227.021 completion.
- **Analisis kegagalan (14 soal):** 7 soal murni perbedaan konvensi format ekspresi dataset (mis. operator pangkat `^` vs `**`, spasi pada polinomial, kapitalisasi string); 1 soal model mengeluarkan panggilan kedua yang tidak perlu; **hanya 1 dari 200 soal berupa pemilihan fungsi yang benar-benar salah**; sisanya perbedaan granularitas nilai (mis. nilai boolean opsional yang diisi berbeda dari ground truth).

> Ini adalah pengukuran terhadap dataset dan metodologi resmi pada subset 200 soal, **bukan** skor leaderboard resmi BFCL. Perbandingan yang sah adalah kolom Single-Turn pada leaderboard v3, bukan angka Overall yang turut mencakup kategori multi-turn dan deteksi halusinasi.

Reproduksi: `python benchmarks/bench_bfcl_v3.py` (dataset diunduh otomatis; subset dapat diperbesar lewat variabel lingkungan `BFCL_N_SIMPLE` dan `BFCL_N_MULTIPLE`).

---

## 3. TAU-bench Retail (dataset resmi): 30,0%

- **Cakupan:** 20 tugas pertama dari 115 tugas test domain retail pada dataset resmi TAU-bench (Sierra Research).
- **Harness yang ditegakkan:**
  1. **User simulator LLM sungguhan** (model yang sama) yang memegang instruksi privat tugas dan mengungkap detail secara bertahap, sebagaimana desain resmi TAU-bench. Instruksi privat tidak pernah diberikan kepada agen.
  2. **Reward ketat gaya resmi:** state database akhir agen harus **persis sama** dengan state emas yang dihasilkan dengan memutar ulang (replay) aksi annotator melalui implementasi tool yang sama, **dan** semua string `outputs` yang disyaratkan tugas harus benar-benar diucapkan agen kepada pengguna.
  3. **Kelimabelas tool retail terdaftar lengkap**, termasuk `modify_pending_order_items` dan `transfer_to_human_agents`.
- **Hasil:** **reward 30,0% (6/20)** dengan **0 pelanggaran kebijakan**. Tugas yang lulus: 0, 1, 6, 7, 11, 12. Waktu total 1.294,5 detik; token agen 1.131.208 prompt + 197.008 completion, token simulator 210.170 + 69.875.
- **Analisis kegagalan:** 11 tugas gagal hanya pada state database, 1 hanya pada `outputs` (state benar, tetapi satu angka yang disyaratkan tidak pernah diucapkan), 2 pada keduanya. Mekanisme kegagalan dominan terukur jelas: **model menghilangkan karakter `#` di depan ID pesanan** (kunci pesanan berbentuk `#W...` dan environment mencocokkan secara persis). Tercatat 17 dari 20 tugas melakukan setidaknya satu panggilan tanpa `#`; tugas yang agennya pulih ke bentuk yang benar lulus, yang tidak pulih gagal persis pada pesanan tersebut, beberapa berakhir pada eskalasi ke agen manusia setelah kebuntuan "order not found".

> Batas kejujuran: environment adalah reimplementasi yang setia dari data resmi (bukan kode environment penyelenggara), simulator memakai model yang sama dengan agen, dan cakupan baru 20 dari 115 tugas. Angka ini bukan skor resmi TAU-bench; ia adalah pengukuran internal dengan reward berstandar resmi pada subset tersebut.

Reproduksi: `python benchmarks/bench_tau.py` (mengkloning dataset resmi secara dangkal; jumlah tugas lewat `TAU_N_TASKS`).

---

## 4. LOCOMO (dataset resmi): 50,0%

- **Cakupan:** sampel **conv-26** dari dataset resmi LOCOMO (`locomo10.json`, snap-research): 20 soal yang diambil berstrata lintas kategori resmi (multi-hop, temporal, open-domain, single-hop; adversarial dikecualikan), dari total 199 soal pada sampel ini.
- **Persyaratan harness yang ditegakkan** (ditemukan lewat pengujian langsung terhadap perilaku graph memory; tanpa ketiganya pengukuran runtuh menjadi 0% karena kegagalan pipeline, bukan kegagalan penalaran):
  1. **Anggaran mutasi sesi dinaikkan.** Graph memory membatasi penulisan per sesi sebagai pengaman anti-runaway (bawaan 5 mutasi per `session_id`). Ingestion satu percakapan panjang harus menaikkan batas ini secara eksplisit, dan **setiap receipt mutasi wajib diperiksa**: mutasi yang ditolak batas tidak melempar error, ia hanya tidak tertulis.
  2. **Kata kunci ingestion diturunkan dari isi catatan.** `graph:locate` adalah pencarian atas indeks judul/kata kunci (BM25), bukan pencarian full-text. Catatan yang kata kuncinya hanya berisi ID sesi tidak akan pernah ditemukan oleh pertanyaan topikal.
  3. **Vault dipertahankan** sesudah run agar rantai ingestion sampai jawaban dapat diaudit.
- **Ingestion:** 21 catatan tertulis dan terverifikasi (1 per sesi percakapan berisi ringkasan + fakta observasi dataset, ditambah 2 catatan agregat per persona). Uji pra-terbang: `graph:locate` menemukan kandidat untuk **20 dari 20 soal** sebelum agen dijalankan.
- **Hasil:** **50,0% (10/20)**. Per kategori: Multi-Hop **80%** (4/5), Temporal **60%** (3/5), Single-Hop **60%** (3/5), Open-Domain **0%** (0/5). Waktu 185,2 detik; token 306.711 prompt + 36.674 completion.
- **Catatan scorer dan kegagalan:** penilaian memakai scorer longgar containment/token-F1 (ambang 0,5). Kategori Open-Domain berisi soal spekulatif ("would X likely...") dengan jawaban emas sangat singkat ("Likely no") yang sulit dikreditkan scorer containment terhadap jawaban model yang beralasan dan berhedging, termasuk ketika arah jawabannya sejalan. Setidaknya satu jawaban yang benar secara semantik terskor salah karena morfologi frasa. Kegagalan temporal berupa inferensi tanggal relatif; satu kegagalan single-hop adalah batas cakupan ingestion berbasis ringkasan dibanding turn mentah.

> Angka ini adalah pengukuran metodologi LOCOMO pada 20 dari 199 soal satu sampel percakapan, bukan skor leaderboard resmi.

Reproduksi: `python benchmarks/bench_locomo.py` (dataset diunduh otomatis; jumlah soal per kategori lewat `LOCOMO_PER_CATEGORY`).

---

## 5. GAIA: belum diterbitkan sebagai angka

Dataset validasi GAIA bersifat gated, dan subset berkunci publik yang dapat diakses hanya memberi **satu soal yang dapat diskor**. Pada soal tersebut (soal yang sama pada semua run), agen **dengan** tool web (`web:search` + `web:fetch`) menjawab **benar**, sedangkan run tanpa tool web menjawab salah dari ingatan model. Ini membuktikan rantai browsing bekerja ujung-ke-ujung, tetapi n=1 bukan skor dan tidak diterbitkan sebagai angka. Skor GAIA akan diterbitkan bila tersedia akses dataset yang sah dengan jumlah soal yang layak.

---

## 6. Apa yang angka-angka ini bukan

- Bukan skor leaderboard resmi untuk BFCL, TAU-bench, LOCOMO, maupun GAIA. Tidak ada pengajuan ke penyelenggara mana pun.
- Angka Bagian 2 sampai 4 **mengukur model** (`deepseek-v4.1-flash-1017`) yang bekerja melalui harness Astraea. Model lain akan menghasilkan angka lain; yang dapat diklaim dari framework adalah bahwa harness tidak menghalangi, menyediakan tool dan memori yang dapat ditemukan model, dan mencatat setiap kegagalan secara transparan.
- Angka Pilar A mengukur framework pada satu VM bersama. Hardware berbeda menghasilkan angka berbeda; yang stabil adalah orde besarannya dan sifat-sifat yang diuji (0 drift cache, 99,95% penghematan token progressive disclosure, 50/50 pemulihan tanpa token retry).

## 7. Reproduksi

```bash
pip install astraea-adk==1.5.1
cp examples/.env.example .env   # isi CUSTOM_PROVIDER_API_KEY dan model yang dipakai

python benchmarks/bench_bfcl_v3.py
python benchmarks/bench_tau.py
python benchmarks/bench_locomo.py
python benchmarks/bench_gaia.py
```

Setiap skrip menulis berkas `results_*.json` berisi metadata lengkap (versi paket dan path instalasinya, model, temperature, jumlah soal, pemakaian token) beserta rincian per soal, sehingga setiap angka di dokumen ini dapat ditelusur kembali ke run yang menghasilkannya.
