"""
LOCOMO (dataset resmi locomo10.json, sampel conv-26) melalui Astraea-ADK.

Menegakkan tiga persyaratan harness yang ditemukan lewat pengujian langsung
terhadap perilaku graph memory:
  1. Cap mutasi per sesi (bawaan MarkdownGraphMemory = 5 per session_id per instance)
     membuang 52 dari 57 note secara senyap. Di sini budget dinaikkan dan SETIAP
     MutationReceipt diperiksa; penanaman gagal = run berhenti.
  2. Judul/keyword note versi lama hanya berisi ID sesi sehingga graph:locate
     (pencarian indeks judul/keyword, BUKAN full-text) tidak pernah cocok dengan
     kueri topikal. Di sini keyword diturunkan dari kosakata isi note itu sendiri
     (summary + observation dataset), ditambah nama penutur dan tanggal sesi.
  3. Vault dipertahankan di workspace untuk audit, dan panggilan tool per soal dicatat.

Desain memori: riwayat aktif = 14 turn terakhir (jendela kerja) + seluruh sesi lama
sebagai note graph memory (summary + observation resmi dataset per sesi, dirantai
kronologis) + satu note profil agregat per penutur.
Pemilihan soal: maksimal 5 soal per kategori resmi 1-4 (multi-hop, temporal,
open-domain, single-hop), urutan dataset. Scorer: containment / token-F1 longgar
yang sama dengan rujukan terbuka yang beredar, agar hasil dapat dibandingkan.

CATATAN KEJUJURAN: metodologi mengikuti LOCOMO, subset 20 soal dari 199 soal
conv-26; bukan skor leaderboard resmi. Kategori resmi LOCOMO: 1=multi-hop,
2=temporal, 3=open-domain, 4=single-hop, 5=adversarial.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VAULT = BASE_DIR / "locomo-vault"
MODEL = os.environ.get("TEST_PRIMARY_MODEL", "deepseek-v4.1-flash-1017")
PER_CAT = int(os.environ.get("LOCOMO_PER_CAT", "5"))

ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import AstraeaADK  # noqa: E402
from AstraeaADK import (  # noqa: E402
    LLMSpec,
    MarkdownGraphMemory,
    SessionState,
    TurnPolicy,
    clear_tool_registry,
    contract_message,
    execute_registered_tool,
    execute_turn,
    register_graph_memory_tools,
)
from AstraeaADK.memory import MutationRequest  # noqa: E402

CATEGORY_NAMES = {1: "Multi-Hop", 2: "Temporal", 3: "Open-Domain", 4: "Single-Hop", 5: "Adversarial"}
STOPWORDS = set(
    "the a an and or of to in on at for with was is are were had has have did do does "
    "when what who whom which that this it its she he her his they them their went go "
    "going been be am as by from about into after before last next time day days week "
    "month year yesterday today tomorrow one two also just like really got get".split()
)


def tokens_of(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) >= 4 and t not in STOPWORDS]


def keywords_for(text: str, extra: List[str], cap: int = 60) -> tuple:
    freq = Counter(tokens_of(text))
    kws = [w for w, _ in freq.most_common(cap)]
    for e in extra:
        el = e.lower().strip()
        if el and el not in kws:
            kws.append(el)
    return tuple(kws[: cap + len(extra)])


def normalize_tokens(text: str) -> Set[str]:
    cleaned = re.sub(r"[^a-zA-Z0-9_\s]", " ", (text or "").lower())
    return set(cleaned.split())


def check_locomo_answer(pred: Any, gold: Any) -> bool:
    """Scorer containment / token-F1 longgar (rujukan terbuka yang beredar)."""
    if gold is None:
        p_str = str(pred or "").lower().strip()
        return not p_str or "tidak" in p_str or "none" in p_str or "unanswerable" in p_str
    p_lower = str(pred or "").lower().strip()
    g_lower = str(gold).lower().strip()
    if not p_lower or not g_lower:
        return False
    if g_lower in p_lower:
        return True
    gold_tokens = normalize_tokens(g_lower)
    pred_tokens = normalize_tokens(p_lower)
    stop_words = {"a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is", "was"}
    meaningful_gold = gold_tokens - stop_words
    if meaningful_gold and meaningful_gold <= pred_tokens:
        return True
    if meaningful_gold and pred_tokens:
        overlap = len(meaningful_gold & pred_tokens)
        precision = overlap / len(pred_tokens)
        recall = overlap / len(meaningful_gold)
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        if f1 >= 0.6 or recall >= 0.75:
            return True
    return False


async def plant_memory(sample: Dict[str, Any]) -> Dict[str, Any]:
    if VAULT.exists():
        shutil.rmtree(VAULT)
    VAULT.mkdir(parents=True)
    writer = MarkdownGraphMemory(VAULT, skill_gate=lambda _: True, max_mutations_per_session=100000)
    conv = sample["conversation"]
    speaker_a = conv.get("speaker_a", "Caroline")
    speaker_b = conv.get("speaker_b", "Melanie")
    summaries = sample.get("session_summary", {})
    observations = sample.get("observation", {})

    session_nums = sorted(
        int(k.split("_")[1]) for k in conv.keys() if re.fullmatch(r"session_\d+", k)
    )
    receipts: List[str] = []
    prev_node: str | None = None
    per_persona_facts: Dict[str, List[str]] = {speaker_a: [], speaker_b: []}

    for n in session_nums:
        date_time = conv.get(f"session_{n}_date_time", "")
        summary = summaries.get(f"session_{n}_summary", "") or ""
        obs = observations.get(f"session_{n}_observation", {}) or {}
        fact_lines: List[str] = []
        for persona, items in obs.items():
            for item in items:
                if isinstance(item, list) and item:
                    fact_lines.append(f"- ({persona}) {item[0]}")
                    if persona in per_persona_facts:
                        per_persona_facts[persona].append(f"[session {n}, {date_time}] {item[0]}")
        content = summary.strip()
        if fact_lines:
            content += "\n\nObservations:\n" + "\n".join(fact_lines)
        if not content:
            continue
        kws = keywords_for(content, [speaker_a, speaker_b, f"session {n}", date_time])
        receipt = await writer.learn_and_link(
            MutationRequest(
                session_id="locomo-ingest",
                folder="sessions",
                title=f"Session {n} - {date_time}",
                note_type="experience",
                keywords=kws,
                content=content,
                linked_nodes=(prev_node,) if prev_node else (),
            )
        )
        receipts.append(str(getattr(receipt, "action_taken", "?")))
        node_id = getattr(receipt, "node_id", None)
        if node_id:
            prev_node = node_id

    for persona, facts in per_persona_facts.items():
        if not facts:
            continue
        content = "\n".join(f"- {f}" for f in facts)
        kws = keywords_for(content, [persona, "profile", speaker_a, speaker_b])
        receipt = await writer.learn_and_link(
            MutationRequest(
                session_id="locomo-ingest",
                folder="profiles",
                title=f"Profile {persona}",
                note_type="experience",
                keywords=kws,
                content=content,
                linked_nodes=(),
            )
        )
        receipts.append(str(getattr(receipt, "action_taken", "?")))

    files = sorted(p.relative_to(VAULT).as_posix() for p in VAULT.rglob("*.md"))
    created = sum(1 for r in receipts if r == "CREATED")
    report = {
        "receipts_total": len(receipts),
        "receipts_created": created,
        "receipt_actions": Counter(receipts),
        "md_files_on_disk": len(files),
    }
    if created != len(receipts) or len(files) != len(receipts):
        raise RuntimeError(f"Penanaman tidak lengkap: {report}")
    return {k: (dict(v) if isinstance(v, Counter) else v) for k, v in report.items()}


def build_recent_history(sample: Dict[str, Any]) -> List[Dict[str, Any]]:
    conv = sample["conversation"]
    speaker_a = conv.get("speaker_a", "Caroline")
    recent: List[Dict[str, Any]] = []
    for key in sorted((k for k in conv if re.fullmatch(r"session_\d+", k)),
                      key=lambda k: int(k.split("_")[1]), reverse=True):
        for turn in reversed(conv[key]):
            if len(recent) < 14 and isinstance(turn, dict):
                speaker = turn.get("speaker", "User")
                recent.append({
                    "role": "user" if speaker == speaker_a else "assistant",
                    "content": f"{speaker}: {turn.get('text', '')}",
                })
    recent.reverse()
    return [{
        "role": "system",
        "content": (
            "ANCHOR: Riwayat sesi percakapan aktif (jendela terbaru). Kamu memiliki ingatan "
            "jangka panjang di Graph Memory berisi seluruh sesi lama. Gunakan graph:locate "
            "dengan kata kunci topikal lalu graph:read_section untuk membaca faktanya."
        ),
    }] + recent


def select_questions(sample: Dict[str, Any]) -> List[Dict[str, Any]]:
    picked: List[Dict[str, Any]] = []
    counts: Counter = Counter()
    for q in sample.get("qa", []):
        cat = q.get("category")
        if cat in (1, 2, 3, 4) and counts[cat] < PER_CAT:
            picked.append(q)
            counts[cat] += 1
    return picked


async def main() -> None:
    data = json.loads((DATA_DIR / "locomo10.json").read_text(encoding="utf-8"))
    sample = data[0]
    sample_id = sample.get("sample_id", "conv-26")
    questions = select_questions(sample)
    print(f"=== LOCOMO {sample_id}: {len(questions)} soal terpilih ===", flush=True)

    plant_report = await plant_memory(sample)
    print(f"Penanaman graph memory: {plant_report}", flush=True)

    clear_tool_registry()
    register_graph_memory_tools(vault_path=VAULT, skill_gate=lambda _: True, max_mutations_per_session=5)
    history = build_recent_history(sample)

    spec = LLMSpec(
        handle="@locomo-agent",
        agent_name="LoCoMo Long-Term Memory Agent",
        soul_prompt="Agen dengan kemampuan memori jangka panjang dan penarikan fakta yang akurat.",
        system_prompt=(
            "Kamu adalah asisten percakapan dengan memori jangka panjang. Jawab pertanyaan "
            "secara ringkas dan faktual. Fakta sesi lama tersimpan di Graph Memory: gunakan "
            "graph:locate dengan kata kunci dari pertanyaan, lalu graph:read_section untuk "
            "membaca isinya sebelum menjawab. Jawab dalam Bahasa Inggris sesuai pertanyaan. "
            "Jangan mengarang informasi; bila setelah mencari tetap tidak ada, katakan tidak ditemukan."
        ),
        tool_permissions=["graph:*"],
        model_settings={"provider": "custom", "model": MODEL, "temperature": 0.0},
    )

    # Pra-uji: apakah locate menemukan kandidat untuk setiap soal?
    preflight: Dict[str, int] = {}
    for i, q in enumerate(questions):
        out = await execute_registered_tool(spec, "graph:locate", {"query": q.get("question", "")})
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        try:
            parsed = json.loads(text)
            preflight[str(i)] = len(parsed.get("candidates", []))
        except Exception:
            preflight[str(i)] = -1
    hits = sum(1 for v in preflight.values() if v and v > 0)
    print(f"Pra-uji locate: {hits}/{len(questions)} soal punya kandidat.", flush=True)

    results: List[Dict[str, Any]] = []
    t_start = time.perf_counter()
    for i, q in enumerate(questions):
        q_text = q.get("question", "")
        gold = q.get("answer", "")
        cat = q.get("category", 0)
        t0 = time.perf_counter()
        pred, status, p_tok, c_tok, tool_calls = "", "UNKNOWN", 0, 0, []
        try:
            res = await execute_turn(
                spec,
                contract_message(sender="@user", target="@locomo-agent", content=q_text),
                SessionState(session_id=f"locomo-{sample_id}", history=tuple(history)),
                policy=TurnPolicy(max_tool_rounds=8),
            )
            pred = res.content or ""
            status = res.status
            p_tok = getattr(res, "prompt_tokens", 0) or 0
            c_tok = getattr(res, "completion_tokens", 0) or 0
            tool_calls = [
                {"tool_name": tr.get("tool_name"), "status": tr.get("status")}
                for tr in (getattr(res, "tool_results", None) or [])
            ]
        except Exception as exc:
            status = f"EXCEPTION: {type(exc).__name__}"
            pred = f"[Error: {exc}]"
        ok = check_locomo_answer(pred, gold)
        entry = {
            "id": i + 1,
            "category": cat,
            "category_name": CATEGORY_NAMES.get(cat, f"Cat-{cat}"),
            "question": q_text,
            "ground_truth": gold,
            "prediction": pred,
            "correct": ok,
            "status": status,
            "tool_calls": tool_calls,
            "preflight_locate_candidates": preflight.get(str(i)),
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
        }
        results.append(entry)
        _save(results, plant_report, preflight, t_start, sample_id)
        print(f"[{i+1}/{len(questions)}] [{entry['category_name']}] {'BENAR' if ok else 'SALAH'} "
              f"(gold='{gold}', tools={len(tool_calls)}, {entry['elapsed_seconds']}s)", flush=True)

    _save(results, plant_report, preflight, t_start, sample_id)
    correct = sum(1 for r in results if r["correct"])
    print(f"\n=== LOCOMO SELESAI: {correct}/{len(results)} = {correct/len(results)*100:.1f}% ===")


def _save(results, plant_report, preflight, t_start, sample_id) -> None:
    cats: Dict[str, Dict[str, int]] = {}
    for r in results:
        c = cats.setdefault(r["category_name"], {"total": 0, "correct": 0})
        c["total"] += 1
        c["correct"] += 1 if r["correct"] else 0
    for c in cats.values():
        c["accuracy_pct"] = round(c["correct"] / c["total"] * 100.0, 1) if c["total"] else 0.0
    correct = sum(1 for r in results if r["correct"])
    meta = {
        "astraeaadk_version": AstraeaADK.__version__,
        "astraeaadk_path": AstraeaADK.__file__,
        "model": MODEL,
        "provider": "custom",
        "sample_id": sample_id,
        "selection": "maks 5 soal per kategori resmi 1-4, urutan dataset",
        "total_questions": len(results),
        "correct": correct,
        "accuracy_pct": round(correct / len(results) * 100.0, 1) if results else 0.0,
        "total_prompt_tokens": sum(r["prompt_tokens"] for r in results),
        "total_completion_tokens": sum(r["completion_tokens"] for r in results),
        "elapsed_seconds": round(time.perf_counter() - t_start, 1),
        "categories": cats,
        "planting_report": plant_report,
        "preflight_locate_hits": sum(1 for v in preflight.values() if v and v > 0),
        "vault_path": str(VAULT),
    }
    out = {"meta": meta, "results": results}
    (BASE_DIR / "results_locomo.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
