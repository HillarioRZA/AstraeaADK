"""
BFCL v3 OFFICIAL-DATASET SUBSET RUN THROUGH ASTRAEA-ADK (LegionADK).

Sama seperti pack terverifikasi 2026-11-02 (pencocokan AST mengikuti semantik BFCL),
dengan perubahan: subset bawaan diperbesar (simple 100 + multiple 100, soal pertama
secara deterministik), versi dan path LegionADK dicatat, provider langsung via
proxy environment (tanpa relay).

CATATAN KEJUJURAN: dataset resmi + evaluasi AST mengikuti BFCL melalui engine
Astraea. Bukan skor leaderboard resmi penyelenggara.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

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

N_SIMPLE = int(os.environ.get("BFCL_N_SIMPLE", "100"))
N_MULTIPLE = int(os.environ.get("BFCL_N_MULTIPLE", "100"))
SUBSET = [("simple", N_SIMPLE), ("multiple", N_MULTIPLE)]


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def reg_name(bfcl_name: str) -> str:
    if "." in bfcl_name:
        return bfcl_name.replace(".", ":", 1)
    return f"bfcl:{bfcl_name}"


def fix_schema(params: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(params))

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            t = node.get("type")
            if t == "dict":
                node["type"] = "object"
            elif t == "tuple":
                node["type"] = "array"
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)
    return out


def value_match(model_val: Any, expected_val: Any) -> bool:
    if isinstance(expected_val, bool) or isinstance(model_val, bool):
        return isinstance(model_val, bool) and isinstance(expected_val, bool) and model_val == expected_val
    if isinstance(expected_val, (int, float)) and isinstance(model_val, (int, float)):
        return float(model_val) == float(expected_val)
    if isinstance(expected_val, str) and isinstance(model_val, str):
        return model_val.strip() == expected_val.strip()
    if isinstance(expected_val, list) and isinstance(model_val, list):
        return len(model_val) == len(expected_val) and all(
            value_match(m, e) for m, e in zip(model_val, expected_val)
        )
    if isinstance(expected_val, dict) and isinstance(model_val, dict):
        return args_match(model_val, expected_val, {})
    if expected_val is None and model_val is None:
        return True
    return model_val == expected_val


def args_match(model_args: Dict[str, Any], gt_params: Dict[str, List[Any]], func_spec: Dict[str, Any]) -> bool:
    properties = (func_spec.get("parameters") or {}).get("properties") or {}
    for param, possible_values in gt_params.items():
        if param not in model_args:
            if "" in possible_values:
                continue
            return False
        if not any(value_match(model_args[param], pv) for pv in possible_values):
            return False
    for param, val in model_args.items():
        if param not in gt_params:
            default = properties.get(param, {}).get("default")
            if default is None or not value_match(val, default):
                return False
    return True


def question_correct(calls: List[Tuple[str, Dict[str, Any]]], ground_truth: List[Dict[str, Any]], func_specs: Dict[str, Any]) -> bool:
    if not calls or not ground_truth:
        return False
    gt = ground_truth[0]
    gt_func = next(iter(gt.keys()))
    if any(name != gt_func for name, _ in calls):
        return False
    return any(args_match(args, gt[gt_func], func_specs.get(gt_func, {})) for _, args in calls)


async def run_question(q: Dict[str, Any], gt_entry: Dict[str, Any]) -> Dict[str, Any]:
    clear_tool_registry()
    recorded: List[Tuple[str, Dict[str, Any]]] = []
    func_specs: Dict[str, Any] = {}
    tool_names: List[str] = []

    for fn in q["function"]:
        orig_name = fn["name"]
        func_specs[orig_name] = fn
        rname = reg_name(orig_name)
        tool_names.append(rname)

        def make_handler(name: str):
            def handler(**kwargs: Any) -> str:
                recorded.append((name, dict(kwargs)))
                return json.dumps({"result": "success", "value": 1})
            return handler

        register_tool(ToolSpec(
            name=rname,
            description=fn.get("description", ""),
            risk_tier=0,
            parameters_schema=fix_schema(fn.get("parameters") or {"type": "object", "properties": {}}),
            handler=make_handler(orig_name),
        ))

    user_text = q["question"][0][0]["content"]
    spec = LLMSpec(
        handle="@bfcl",
        agent_name="BFCL Eval Agent",
        soul_prompt="Asisten function calling yang presisi.",
        system_prompt=(
            "You are an assistant with access to functions. For the user's request, call the single "
            "most appropriate function with arguments taken exactly from the request. Do not answer "
            "from memory when a function applies, and do not invent argument values."
        ),
        tool_permissions=tool_names,
        model_settings={"provider": "custom", "model": MODEL, "temperature": 0.0},
    )

    result: Dict[str, Any] = {
        "id": q["id"],
        "model_calls": [],
        "ground_truth": gt_entry.get("ground_truth", []),
        "correct": False,
        "status": "",
        "error": "",
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    try:
        res = await execute_turn(
            spec,
            contract_message(sender="@user", target="@bfcl", content=user_text),
            SessionState(session_id=f"bfcl-{q['id']}"),
            policy=TurnPolicy(max_tool_rounds=3),
        )
        result["status"] = res.status
        result["prompt_tokens"] = getattr(res, "prompt_tokens", 0) or 0
        result["completion_tokens"] = getattr(res, "completion_tokens", 0) or 0
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    result["model_calls"] = [{"name": n, "arguments": a} for n, a in recorded]
    result["correct"] = question_correct(recorded, gt_entry.get("ground_truth", []), func_specs)
    return result


async def main() -> None:
    all_results: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}
    t0 = time.perf_counter()
    for category, limit in SUBSET:
        questions = load_jsonl(DATA_DIR / f"BFCL_v3_{category}.json")
        answers = {a["id"]: a for a in load_jsonl(DATA_DIR / f"BFCL_v3_{category}_possible.json")}
        picked = [q for q in questions if q.get("id") in answers and q.get("question") and q.get("function")][:limit]
        cat_results = []
        for q in picked:
            r = await run_question(q, answers[q["id"]])
            r["category"] = category
            cat_results.append(r)
            print(f"[{category}] {r['id']}: {'BENAR' if r['correct'] else 'SALAH'} "
                  f"(status={r['status']}, calls={len(r['model_calls'])})", flush=True)
        ok = sum(1 for r in cat_results if r["correct"])
        summary[category] = {"n": len(cat_results), "correct": ok,
                             "accuracy": (ok / len(cat_results) * 100.0) if cat_results else 0.0,
                             "ids": [r["id"] for r in cat_results]}
        all_results.extend(cat_results)
        # simpan progres per kategori
        _save(all_results, summary, t0)

    _save(all_results, summary, t0)
    print("\n=== RINGKASAN ===")
    print(json.dumps(_meta(all_results, summary, t0), indent=1))


def _meta(all_results, summary, t0):
    total_ok = sum(1 for r in all_results if r["correct"])
    total_n = len(all_results)
    return {
        "legionadk_version": LegionADK.__version__,
        "legionadk_path": LegionADK.__file__,
        "model": MODEL,
        "provider": "custom (TokenomixAI langsung via proxy environment)",
        "temperature": 0.0,
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
        "total": {"n": total_n, "correct": total_ok,
                  "accuracy": (total_ok / total_n * 100.0) if total_n else 0.0},
        "prompt_tokens": sum(r["prompt_tokens"] for r in all_results),
        "completion_tokens": sum(r["completion_tokens"] for r in all_results),
        "per_category": summary,
    }


def _save(all_results, summary, t0) -> None:
    out = {"meta": _meta(all_results, summary, t0), "results": all_results}
    (BASE_DIR / "results_bfcl.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
