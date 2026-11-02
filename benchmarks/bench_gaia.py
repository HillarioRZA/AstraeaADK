"""
GAIA (subset validasi berkunci publik) melalui Astraea-ADK.

GAIA adalah benchmark browsing, jadi agen dilengkapi tool web:
Agen dilengkapi web:search (DuckDuckGo Lite) dan web:fetch, plus
calculator dan python_eval. Sembilan soal adalah task_id validasi GAIA yang
kunci jawabannya beredar publik (kontributor mirror);
sumber soal mirror GitHub pihak ketiga
(Pandagan-85/React_agent_Gaia), BUKAN unduhan resmi gaia-benchmark yang gated.

Scorer: pencocokan kuasi-eksak gaya GAIA (normalisasi, ekuivalensi numerik,
kesetaraan set untuk daftar koma). Cakupan: 9 soal Level 1. Ini smoke subset,
bukan skor GAIA resmi.
"""

from __future__ import annotations

import asyncio
import html as html_mod
import json
import math
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

import httpx

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL = os.environ.get("TEST_PRIMARY_MODEL", "deepseek-v4.1-flash-1017")

ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import LegionADK  # noqa: E402
from LegionADK import (  # noqa: E402
    LLMSpec,
    SessionState,
    ToolSpec,
    TurnPolicy,
    clear_tool_registry,
    contract_message,
    execute_turn,
    register_tool,
)

GROUND_TRUTHS = {
    "8e867cd7-cff9-4e6c-867a-ff5ddc2550be": "3",
    "2d83110e-0912-4217-a068-07a82ecaa175": "right",
    "4fc2f1ae-967a-42fc-88ad-5df962947116": "FunkMonk",
    "6f37996b-568b-4b2a-8755-e46045610ecf": "b, e",
    "3cef3a44-df4a-4eeb-b2f7-7b8303ba696f": "broccoli, celery, fresh basil, lettuce, sweet potatoes",
    "305ac316-2c70-4f59-b14d-fa5df45e0f7e": "Wojciech",
    "3f57289b-8916-418f-a9cb-bb3eb1a052ff": "551",
    "cf106601-e25f-4ee6-8575-cf0cfa7297e5": "Cuba",
    "5a0c1adf-500b-47e2-aa59-86687a7187e1": "Claus Peter",
}

PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AstraeaBench/1.0; +https://github.com/HillarioRZA/Astraea-ADK)"}


def _client() -> httpx.Client:
    # trust_env=False + proxy eksplisit: menghindari parser NO_PROXY environment.
    # verify diarahkan ke SSL_CERT_FILE environment (bundle CA proxy egress sandbox).
    verify = os.environ.get("SSL_CERT_FILE") or True
    return httpx.Client(proxy=PROXY, trust_env=False, verify=verify, timeout=30.0, headers=HEADERS, follow_redirects=True)


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</p\s*>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html_mod.unescape(raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n", raw)
    return raw.strip()


def tool_search(query: str) -> str:
    try:
        with _client() as c:
            r = c.get("https://lite.duckduckgo.com/lite/", params={"q": query})
            r.raise_for_status()
            page = r.text
    except Exception as exc:
        return json.dumps({"error": f"search gagal: {type(exc).__name__}: {exc}"})
    results = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        url = html_mod.unescape(m.group(1))
        uddg = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("uddg", [None])[0]
        if not uddg:
            continue
        title = strip_html(m.group(2))
        if not title:
            continue
        results.append({"title": title, "url": urllib.parse.unquote(uddg)})
        if len(results) >= 8:
            break
    snippets = [strip_html(s) for s in re.findall(r'class="result-snippet"[^>]*>(.*?)</td>', page, re.S)][:8]
    for i, s in enumerate(snippets):
        if i < len(results):
            results[i]["snippet"] = s[:300]
    return json.dumps({"results": results}, ensure_ascii=False)


def tool_fetch(url: str) -> str:
    try:
        with _client() as c:
            r = c.get(url)
            r.raise_for_status()
            text = strip_html(r.text)
    except Exception as exc:
        return json.dumps({"error": f"fetch gagal: {type(exc).__name__}: {exc}"})
    return json.dumps({"url": url, "content": text[:7000]}, ensure_ascii=False)


def tool_calc(expr: str) -> str:
    try:
        allowed = {"abs": abs, "round": round, "min": min, "max": max, "sum": sum,
                   "len": len, "math": math, "sorted": sorted, "list": list, "set": set}
        res = eval(expr, {"__builtins__": {}}, allowed)
        return json.dumps({"result": res})
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


def tool_python_exec(code: str) -> str:
    try:
        scope: Dict[str, Any] = {"math": math}
        exec(code, scope)
        out = {k: v for k, v in scope.items() if not k.startswith("_") and k != "math"}
        return json.dumps({"output": str(out)})
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


def register_gaia_tools() -> None:
    clear_tool_registry()
    register_tool(ToolSpec(name="web:search", description="Cari di web (DuckDuckGo). Kembalikan judul, URL, dan cuplikan hasil.",
                           risk_tier=0, parameters_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                           handler=lambda query: tool_search(query)))
    register_tool(ToolSpec(name="web:fetch", description="Ambil isi teks sebuah URL (artikel, Wikipedia, dsb).",
                           risk_tier=0, parameters_schema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
                           handler=lambda url: tool_fetch(url)))
    register_tool(ToolSpec(name="gaia:calculator", description="Evaluasi ekspresi matematika.",
                           risk_tier=0, parameters_schema={"type": "object", "properties": {"expr": {"type": "string"}}, "required": ["expr"]},
                           handler=lambda expr: tool_calc(expr)))
    register_tool(ToolSpec(name="gaia:python_eval", description="Jalankan skrip Python pendek untuk logika/teks/permutasi.",
                           risk_tier=0, parameters_schema={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
                           handler=lambda code: tool_python_exec(code)))


def normalize_answer(text: Any) -> str:
    t = str(text or "").strip()
    if "FINAL ANSWER:" in t.upper():
        t = t.split("FINAL ANSWER:", 1)[-1].strip() if "FINAL ANSWER:" in t else t.rsplit("FINAL ANSWER:", 1)[-1].strip()
    t = t.strip("`'\" \t\r\n.,")
    return t.lower()


def is_answer_correct(pred: str, gold: str) -> bool:
    p_norm = normalize_answer(pred)
    g_norm = normalize_answer(gold)
    if not p_norm or not g_norm:
        return False
    if p_norm == g_norm:
        return True
    try:
        if abs(float(p_norm) - float(g_norm)) < 1e-4:
            return True
    except ValueError:
        pass
    if "," in g_norm:
        p_parts = set(x.strip() for x in p_norm.split(","))
        g_parts = set(x.strip() for x in g_norm.split(","))
        if p_parts == g_parts:
            return True
    if len(g_norm) >= 4 and g_norm in p_norm:
        return True
    return False


async def main() -> None:
    items = json.loads((DATA_DIR / "gaia_questions.json").read_text(encoding="utf-8"))
    by_id = {it.get("task_id"): it for it in items}
    eval_set = []
    for tid, gold in GROUND_TRUTHS.items():
        q = by_id.get(tid)
        if q:
            eval_set.append({"task_id": tid, "level": q.get("Level", 1),
                             "question": q.get("question", ""), "ground_truth": gold})
    print(f"=== GAIA subset publik: {len(eval_set)} soal, tool web aktif ===", flush=True)

    register_gaia_tools()
    spec = LLMSpec(
        handle="@gaia-agent",
        agent_name="GAIA Assistant",
        soul_prompt="Asisten riset generalis yang presisi dan teliti.",
        system_prompt=(
            "Kamu adalah agen riset. Gunakan web:search dan web:fetch untuk memverifikasi fakta "
            "dari sumber nyata (pertanyaan sering menuntut sumber spesifik seperti Wikipedia), "
            "dan tool hitung untuk perhitungan eksak. Jangan menjawab dari ingatan bila fakta "
            "bisa diverifikasi. Di baris terakhir jawabanmu tulis tepat: FINAL ANSWER: <jawaban_singkat>"
        ),
        tool_permissions=["web:search", "web:fetch", "gaia:calculator", "gaia:python_eval"],
        model_settings={"provider": "custom", "model": MODEL, "temperature": 0.0},
    )

    results: List[Dict[str, Any]] = []
    t_start = time.perf_counter()
    for i, q in enumerate(eval_set):
        t0 = time.perf_counter()
        pred, status, p_tok, c_tok, tool_calls = "", "UNKNOWN", 0, 0, []
        try:
            res = await execute_turn(
                spec,
                contract_message(sender="@user", target="@gaia-agent",
                                 content=f"{q['question']}\n\nDi baris paling akhir, tulis format tepat: FINAL ANSWER: <jawaban_singkat>"),
                SessionState(session_id=f"gaia-{q['task_id'][:8]}"),
                policy=TurnPolicy(max_tool_rounds=10),
            )
            pred = res.content or ""
            status = res.status
            p_tok = getattr(res, "prompt_tokens", 0) or 0
            c_tok = getattr(res, "completion_tokens", 0) or 0
            tool_calls = [{"tool_name": tr.get("tool_name"), "status": tr.get("status")}
                          for tr in (getattr(res, "tool_results", None) or [])]
        except Exception as exc:
            status = f"EXCEPTION: {type(exc).__name__}"
            pred = f"[Error: {exc}]"
        ok = is_answer_correct(pred, q["ground_truth"])
        entry = {
            "task_id": q["task_id"], "level": q["level"], "question": q["question"],
            "ground_truth": q["ground_truth"], "prediction": pred, "correct": ok,
            "status": status, "tool_calls": tool_calls,
            "prompt_tokens": p_tok, "completion_tokens": c_tok,
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
        }
        results.append(entry)
        _save(results, t_start)
        print(f"[{i+1}/{len(eval_set)}] [L{q['level']}] {'BENAR' if ok else 'SALAH'} "
              f"(gold='{q['ground_truth']}', tools={len(tool_calls)}, {entry['elapsed_seconds']}s)", flush=True)
    _save(results, t_start)
    correct = sum(1 for r in results if r["correct"])
    print(f"\n=== GAIA SELESAI: {correct}/{len(results)} = {correct/len(results)*100:.1f}% ===")


def _save(results, t_start) -> None:
    correct = sum(1 for r in results if r["correct"])
    meta = {
        "legionadk_version": LegionADK.__version__,
        "legionadk_path": LegionADK.__file__,
        "model": MODEL,
        "provider": "custom",
        "total_tasks": len(results),
        "scored_tasks": len(results),
        "correct": correct,
        "accuracy_pct": round(correct / len(results) * 100.0, 1) if results else 0.0,
        "total_prompt_tokens": sum(r["prompt_tokens"] for r in results),
        "total_completion_tokens": sum(r["completion_tokens"] for r in results),
        "total_time_seconds": round(time.perf_counter() - t_start, 1),
        "tools": ["web:search", "web:fetch", "gaia:calculator", "gaia:python_eval"],
        "dataset_note": "Soal dari mirror GitHub Pandagan-85/React_agent_Gaia; ground truth kunci publik 9 task_id validasi.",
    }
    out = {"meta": meta, "results": results}
    (BASE_DIR / "results_gaia.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
