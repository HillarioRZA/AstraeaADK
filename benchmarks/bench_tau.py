"""
TAU-BENCH RETAIL (dataset resmi Sierra Research) melalui Astraea-ADK.

Menegakkan tiga hal yang kerap dilonggarkan reimplementasi tidak resmi:
  1. ADA user simulator (LLM dengan instruksi resmi per tugas, membuka percakapan
     dan mengungkap rincian bertahap, mengakhiri dengan ###STOP###), bukan
     instruksi simulator yang diserahkan utuh ke agen.
  2. Reward gaya resmi: keadaan akhir DB agen dibandingkan persis dengan DB emas
     hasil replay aksi annotator melalui implementasi tool yang sama, ditambah
     pemeriksaan outputs yang wajib diucapkan agen. Bukan sekadar nama tool cocok.
  3. Tool lengkap untuk 20 tugas pertama termasuk modify_pending_order_items,
     list_all_product_types, transfer_to_human_agents, dan calculate.

Penyimpangan yang tersisa dan diakui: simulator memakai model yang sama dengan
agen (deepseek-v4.1-flash-1017), implementasi environment adalah reimplementasi
setia dari data resmi (bukan kode environment penyelenggara), dan cakupan hanya
20 dari 115 tugas test. Angka ini TIDAK identik dengan skor leaderboard resmi.

State DB yang dibandingkan: users + orders (products statis). Kesetaraan dihitung
dengan perbandingan mendalam setelah normalisasi urutan kunci.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL = os.environ.get("TEST_PRIMARY_MODEL", "deepseek-v4.1-flash-1017")
N_TASKS = int(os.environ.get("TAU_N_TASKS", "20"))
MAX_USER_MSGS = int(os.environ.get("TAU_MAX_USER_MSGS", "16"))

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


# ---------------------------------------------------------------------------
# Pemuatan tugas resmi
# ---------------------------------------------------------------------------

class Action:
    def __init__(self, name: str, kwargs: Dict[str, Any]):
        self.name = name
        self.kwargs = kwargs


class Task:
    def __init__(self, annotator: str, user_id: str, instruction: str, actions: List[Action], outputs: List[Any]):
        self.annotator = annotator
        self.user_id = user_id
        self.instruction = instruction
        self.actions = actions
        self.outputs = outputs


def load_tasks() -> List[Task]:
    code = (DATA_DIR / "tau_tasks_test.py").read_text(encoding="utf-8")
    clean = "\n".join(l for l in code.splitlines() if not l.startswith("from tau_bench"))
    loc: Dict[str, Any] = {"Task": Task, "Action": Action}
    exec(clean, loc)
    return loc["TASKS_TEST"]


# ---------------------------------------------------------------------------
# Environment retail: fungsi murni (env, **kwargs) -> str JSON
# ---------------------------------------------------------------------------

class RetailEnv:
    def __init__(self, users, products, orders):
        self.data = {"users": users, "products": products, "orders": orders}
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self.violations = 0


def _find_variant(env: RetailEnv, item_id: str):
    for pid, prod in env.data["products"].items():
        variants = prod.get("variants", {})
        if item_id in variants:
            v = variants[item_id]
            return {
                "item_id": item_id,
                "product_id": pid,
                "name": prod.get("name", ""),
                "price": v.get("price"),
                "options": v.get("options", {}),
            }
    return None


def t_find_user_by_email(env, email: str) -> str:
    for uid, prof in env.data["users"].items():
        if prof.get("email", "").lower() == email.strip().lower():
            return json.dumps({"user_id": uid})
    return json.dumps({"error": "Error: user not found"})


def t_find_user_by_name_zip(env, first_name: str, last_name: str, zip: str) -> str:
    for uid, prof in env.data["users"].items():
        name = prof.get("name", {})
        addr = prof.get("address", {})
        if (name.get("first_name", "").lower() == first_name.strip().lower()
                and name.get("last_name", "").lower() == last_name.strip().lower()
                and str(addr.get("zip", "")).strip() == str(zip).strip()):
            return json.dumps({"user_id": uid})
    return json.dumps({"error": "Error: user not found"})


def t_get_user_details(env, user_id: str) -> str:
    prof = env.data["users"].get(user_id)
    return json.dumps(prof) if prof else json.dumps({"error": "Error: user not found"})


def t_get_order_details(env, order_id: str) -> str:
    order = env.data["orders"].get(order_id)
    return json.dumps(order) if order else json.dumps({"error": "Error: order not found"})


def t_get_product_details(env, product_id: str) -> str:
    prod = env.data["products"].get(str(product_id))
    return json.dumps(prod) if prod else json.dumps({"error": "Error: product not found"})


def t_list_all_product_types(env) -> str:
    names = sorted({p.get("name", "") for p in env.data["products"].values()})
    return json.dumps({"product_types": names})


def t_cancel_pending_order(env, order_id: str, reason: str) -> str:
    order = env.data["orders"].get(order_id)
    if order is None:
        return json.dumps({"error": "Error: order not found"})
    if order.get("status") != "pending":
        env.violations += 1
        return json.dumps({"error": "Error: non-pending order cannot be cancelled"})
    order["status"] = "cancelled"
    order["cancel_reason"] = reason
    return json.dumps(order)


def t_modify_pending_order_address(env, order_id: str, address1: str, address2: str, city: str, state: str, country: str, zip: str) -> str:
    order = env.data["orders"].get(order_id)
    if order is None:
        return json.dumps({"error": "Error: order not found"})
    if order.get("status") != "pending":
        env.violations += 1
        return json.dumps({"error": "Error: non-pending order cannot be modified"})
    order["address"] = {"address1": address1, "address2": address2, "city": city,
                        "state": state, "country": country, "zip": zip}
    return json.dumps(order)


def t_modify_pending_order_items(env, order_id: str, item_ids: List[str], new_item_ids: List[str], payment_method_id: str) -> str:
    order = env.data["orders"].get(order_id)
    if order is None:
        return json.dumps({"error": "Error: order not found"})
    if order.get("status") != "pending":
        env.violations += 1
        return json.dumps({"error": "Error: non-pending order cannot be modified"})
    new_items = []
    for iid in new_item_ids:
        entry = _find_variant(env, str(iid))
        if entry is None:
            return json.dumps({"error": f"Error: item {iid} not found"})
        new_items.append(entry)
    remaining = [it for it in order.get("items", []) if str(it.get("item_id")) not in {str(x) for x in item_ids}]
    order["items"] = remaining + new_items
    order["payment_method_id"] = payment_method_id
    return json.dumps(order)


def t_modify_pending_order_payment_method(env, order_id: str, payment_method_id: str) -> str:
    order = env.data["orders"].get(order_id)
    if order is None:
        return json.dumps({"error": "Error: order not found"})
    if order.get("status") != "pending":
        env.violations += 1
        return json.dumps({"error": "Error: non-pending order cannot be modified"})
    order["payment_method_id"] = payment_method_id
    return json.dumps(order)


def t_modify_user_address(env, user_id: str, address1: str, address2: str, city: str, state: str, country: str, zip: str) -> str:
    prof = env.data["users"].get(user_id)
    if prof is None:
        return json.dumps({"error": "Error: user not found"})
    prof["address"] = {"address1": address1, "address2": address2, "city": city,
                       "state": state, "country": country, "zip": zip}
    return json.dumps(prof)


def t_return_delivered_order_items(env, order_id: str, item_ids: List[str], payment_method_id: str) -> str:
    order = env.data["orders"].get(order_id)
    if order is None:
        return json.dumps({"error": "Error: order not found"})
    if order.get("status") != "delivered":
        env.violations += 1
        return json.dumps({"error": "Error: non-delivered order cannot be returned"})
    order["status"] = "return requested"
    order["return_items"] = sorted(str(x) for x in item_ids)
    order["return_payment_method_id"] = payment_method_id
    return json.dumps(order)


def t_exchange_delivered_order_items(env, order_id: str, item_ids: List[str], new_item_ids: List[str], payment_method_id: str) -> str:
    order = env.data["orders"].get(order_id)
    if order is None:
        return json.dumps({"error": "Error: order not found"})
    if order.get("status") != "delivered":
        env.violations += 1
        return json.dumps({"error": "Error: non-delivered order cannot be exchanged"})
    new_items = []
    for iid in new_item_ids:
        entry = _find_variant(env, str(iid))
        if entry is None:
            return json.dumps({"error": f"Error: item {iid} not found"})
        new_items.append(entry)
    order["status"] = "exchange requested"
    order["exchange_items"] = sorted(str(x) for x in item_ids)
    order["exchange_new_items"] = new_items
    order["exchange_payment_method_id"] = payment_method_id
    return json.dumps(order)


def t_calculate(env, expression: str) -> str:
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


def t_transfer_to_human_agents(env, summary: str) -> str:
    return json.dumps({"status": "transferred", "summary": summary})


TOOL_FUNCS = {
    "find_user_id_by_email": t_find_user_by_email,
    "find_user_id_by_name_zip": t_find_user_by_name_zip,
    "get_user_details": t_get_user_details,
    "get_order_details": t_get_order_details,
    "get_product_details": t_get_product_details,
    "list_all_product_types": t_list_all_product_types,
    "cancel_pending_order": t_cancel_pending_order,
    "modify_pending_order_address": t_modify_pending_order_address,
    "modify_pending_order_items": t_modify_pending_order_items,
    "modify_pending_order_payment_method": t_modify_pending_order_payment_method,
    "modify_user_address": t_modify_user_address,
    "return_delivered_order_items": t_return_delivered_order_items,
    "exchange_delivered_order_items": t_exchange_delivered_order_items,
    "calculate": t_calculate,
    "transfer_to_human_agents": t_transfer_to_human_agents,
}

TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "find_user_id_by_email": {"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]},
    "find_user_id_by_name_zip": {"type": "object", "properties": {"first_name": {"type": "string"}, "last_name": {"type": "string"}, "zip": {"type": "string"}}, "required": ["first_name", "last_name", "zip"]},
    "get_user_details": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]},
    "get_order_details": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "get_product_details": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]},
    "list_all_product_types": {"type": "object", "properties": {}},
    "cancel_pending_order": {"type": "object", "properties": {"order_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["order_id", "reason"]},
    "modify_pending_order_address": {"type": "object", "properties": {"order_id": {"type": "string"}, "address1": {"type": "string"}, "address2": {"type": "string"}, "city": {"type": "string"}, "state": {"type": "string"}, "country": {"type": "string"}, "zip": {"type": "string"}}, "required": ["order_id", "address1", "address2", "city", "state", "country", "zip"]},
    "modify_pending_order_items": {"type": "object", "properties": {"order_id": {"type": "string"}, "item_ids": {"type": "array", "items": {"type": "string"}}, "new_item_ids": {"type": "array", "items": {"type": "string"}}, "payment_method_id": {"type": "string"}}, "required": ["order_id", "item_ids", "new_item_ids", "payment_method_id"]},
    "modify_pending_order_payment_method": {"type": "object", "properties": {"order_id": {"type": "string"}, "payment_method_id": {"type": "string"}}, "required": ["order_id", "payment_method_id"]},
    "modify_user_address": {"type": "object", "properties": {"user_id": {"type": "string"}, "address1": {"type": "string"}, "address2": {"type": "string"}, "city": {"type": "string"}, "state": {"type": "string"}, "country": {"type": "string"}, "zip": {"type": "string"}}, "required": ["user_id", "address1", "address2", "city", "state", "country", "zip"]},
    "return_delivered_order_items": {"type": "object", "properties": {"order_id": {"type": "string"}, "item_ids": {"type": "array", "items": {"type": "string"}}, "payment_method_id": {"type": "string"}}, "required": ["order_id", "item_ids", "payment_method_id"]},
    "exchange_delivered_order_items": {"type": "object", "properties": {"order_id": {"type": "string"}, "item_ids": {"type": "array", "items": {"type": "string"}}, "new_item_ids": {"type": "array", "items": {"type": "string"}}, "payment_method_id": {"type": "string"}}, "required": ["order_id", "item_ids", "new_item_ids", "payment_method_id"]},
    "calculate": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
    "transfer_to_human_agents": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
}

MUTATION_TOOLS = {
    "cancel_pending_order", "modify_pending_order_address", "modify_pending_order_items",
    "modify_pending_order_payment_method", "modify_user_address",
    "return_delivered_order_items", "exchange_delivered_order_items",
}

CURRENT: Dict[str, Optional[RetailEnv]] = {"env": None}


def register_retail_tools() -> List[str]:
    clear_tool_registry()
    names = []
    for tname, fn in TOOL_FUNCS.items():
        def make(name: str, f):
            def handler(**kwargs: Any) -> str:
                env = CURRENT["env"]
                assert env is not None
                env.calls.append((name, dict(kwargs)))
                return f(env, **kwargs)
            return handler
        reg = f"retail:{tname}"
        register_tool(ToolSpec(
            name=reg,
            description=f"TAU-bench retail tool: {tname}.",
            risk_tier=1 if tname in MUTATION_TOOLS else 0,
            parameters_schema=TOOL_SCHEMAS[tname],
            handler=make(tname, fn),
        ))
        names.append(reg)
    return names


# ---------------------------------------------------------------------------
# Reward: replay emas + perbandingan state
# ---------------------------------------------------------------------------

def replay_golden(task: Task, base) -> RetailEnv:
    env = RetailEnv(copy.deepcopy(base[0]), copy.deepcopy(base[1]), copy.deepcopy(base[2]))
    for a in task.actions:
        fn = TOOL_FUNCS.get(a.name)
        if fn is not None:
            fn(env, **a.kwargs)
    return env


def state_of(env: RetailEnv) -> Dict[str, Any]:
    return {"users": env.data["users"], "orders": env.data["orders"]}


def diff_keys(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    out = []
    for section in ("users", "orders"):
        ka, kb = a.get(section, {}), b.get(section, {})
        for k in sorted(set(ka) | set(kb)):
            if json.dumps(ka.get(k), sort_keys=True) != json.dumps(kb.get(k), sort_keys=True):
                out.append(f"{section}:{k}")
    return out


# ---------------------------------------------------------------------------
# Percakapan agen <-> simulator
# ---------------------------------------------------------------------------

AGENT_POLICY = (
    "You are a customer support agent for an online retail store. Follow this policy strictly:\n"
    "- First authenticate the customer: find their user_id by email, or by first name, last name and zip code, before any transaction.\n"
    "- Use get_order_details to check an order's status before acting on it. Never invent order ids, item ids, or prices; look them up with tools.\n"
    "- Pending orders may be cancelled, or have their address, items, or payment method modified. They cannot be returned or exchanged.\n"
    "- Delivered orders may be returned or exchanged (exchange only for a different variant of the same product type). They cannot be cancelled.\n"
    "- Before committing any change (cancel, return, exchange, modification), state the exact details to the customer and proceed only after they confirm.\n"
    "- Answer the customer's questions with exact figures from the tools when asked."
)

SIM_RULES = (
    "You are role-playing a customer talking to a retail support agent. Your private scenario:\n"
    "{instruction}\n"
    "Rules: speak naturally as that customer, one short message at a time. Reveal personal details "
    "(name, zip, email, order id, preferences) only when the agent asks or when needed; do not dump "
    "the whole scenario in your first message. Confirm or correct the agent's proposed actions based "
    "on your scenario. When everything you wanted is fully resolved, or the agent clearly cannot help, "
    "end the conversation by including the exact token ###STOP### in your final message."
)


async def run_task(idx: int, task: Task, base, tool_names: List[str]) -> Dict[str, Any]:
    env = RetailEnv(copy.deepcopy(base[0]), copy.deepcopy(base[1]), copy.deepcopy(base[2]))
    CURRENT["env"] = env

    agent_spec = LLMSpec(
        handle="@tau-agent",
        agent_name="TAU Retail Support Agent",
        soul_prompt="Agen customer support retail yang patuh kebijakan dan teliti.",
        system_prompt=AGENT_POLICY,
        tool_permissions=tool_names,
        model_settings={"provider": "custom", "model": MODEL, "temperature": 0.0},
    )
    sim_spec = LLMSpec(
        handle="@tau-user",
        agent_name="Simulated Customer",
        soul_prompt="Pelanggan toko online.",
        system_prompt=SIM_RULES.format(instruction=task.instruction),
        tool_permissions=[],
        model_settings={"provider": "custom", "model": MODEL, "temperature": 0.0},
    )

    agent_hist: List[Dict[str, str]] = []
    sim_hist: List[Dict[str, str]] = []
    transcript: List[Dict[str, str]] = []
    agent_tok = {"p": 0, "c": 0}
    sim_tok = {"p": 0, "c": 0}
    t0 = time.perf_counter()
    status = "COMPLETED"

    async def sim_say(agent_text: Optional[str]) -> str:
        nonlocal status
        if agent_text is None:
            incoming = "Begin the conversation with a short, natural opening message stating what you need."
        else:
            incoming = agent_text
            sim_hist.append({"role": "user", "content": agent_text})
        res = await execute_turn(
            sim_spec,
            contract_message(sender="@agent", target="@tau-user", content=incoming),
            SessionState(session_id=f"tau-{idx}-sim", history=tuple(sim_hist)),
            policy=TurnPolicy(max_tool_rounds=1),
        )
        sim_tok["p"] += getattr(res, "prompt_tokens", 0) or 0
        sim_tok["c"] += getattr(res, "completion_tokens", 0) or 0
        text = (res.content or "").strip()
        sim_hist.append({"role": "assistant", "content": text})
        return text

    try:
        user_text = await sim_say(None)
        transcript.append({"role": "user", "content": user_text})
        for _ in range(MAX_USER_MSGS):
            if "###STOP###" in user_text:
                break
            agent_hist.append({"role": "user", "content": user_text})
            res = await execute_turn(
                agent_spec,
                contract_message(sender="@user", target="@tau-agent", content=user_text),
                SessionState(session_id=f"tau-{idx}", history=tuple(agent_hist[:-1])),
                policy=TurnPolicy(max_tool_rounds=8),
            )
            agent_tok["p"] += getattr(res, "prompt_tokens", 0) or 0
            agent_tok["c"] += getattr(res, "completion_tokens", 0) or 0
            status = res.status
            agent_text = (res.content or "").strip()
            agent_hist.append({"role": "assistant", "content": agent_text})
            transcript.append({"role": "assistant", "content": agent_text})
            user_text = await sim_say(agent_text)
            transcript.append({"role": "user", "content": user_text})
            if "###STOP###" in user_text:
                break
    except Exception as exc:
        status = f"EXCEPTION: {type(exc).__name__}: {str(exc)[:200]}"

    golden = replay_golden(task, base)
    agent_state = state_of(env)
    golden_state = state_of(golden)
    diffs = diff_keys(agent_state, golden_state)
    db_equal = not diffs

    agent_speech = " ".join(m["content"] for m in transcript if m["role"] == "assistant").lower()
    outputs_ok = all(str(o).lower() in agent_speech for o in task.outputs)
    reward = 1.0 if (db_equal and outputs_ok) else 0.0

    return {
        "task_idx": idx,
        "user_id": task.user_id,
        "instruction": task.instruction,
        "reward": reward,
        "db_state_equal": db_equal,
        "db_diff_keys": diffs[:10],
        "outputs_required": task.outputs,
        "outputs_satisfied": outputs_ok,
        "policy_violations": env.violations,
        "tool_calls": [{"name": n, "arguments": a} for n, a in env.calls],
        "transcript": transcript,
        "status": status,
        "agent_prompt_tokens": agent_tok["p"],
        "agent_completion_tokens": agent_tok["c"],
        "sim_prompt_tokens": sim_tok["p"],
        "sim_completion_tokens": sim_tok["c"],
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }


async def main() -> None:
    users = json.loads((DATA_DIR / "tau_users.json").read_text(encoding="utf-8"))
    products = json.loads((DATA_DIR / "tau_products.json").read_text(encoding="utf-8"))
    orders = json.loads((DATA_DIR / "tau_orders.json").read_text(encoding="utf-8"))
    base = (users, products, orders)
    tasks = load_tasks()[:N_TASKS]
    tool_names = register_retail_tools()

    print(f"=== TAU-BENCH RETAIL: {len(tasks)} tugas, simulator aktif ===", flush=True)
    print(f"Model agen+simulator: {MODEL}", flush=True)
    results: List[Dict[str, Any]] = []
    t_start = time.perf_counter()
    for idx, task in enumerate(tasks):
        r = await run_task(idx, task, base, tool_names)
        results.append(r)
        _save(results, t_start)
        print(f"[{idx+1}/{len(tasks)}] task_{idx}: reward={r['reward']:.0f} "
              f"(db_equal={r['db_state_equal']}, outputs={r['outputs_satisfied']}, "
              f"viol={r['policy_violations']}, calls={len(r['tool_calls'])}, {r['elapsed_seconds']}s)", flush=True)
    _save(results, t_start)
    total = sum(r["reward"] for r in results)
    print(f"\n=== TAU SELESAI: reward total {total}/{len(results)} = {total/len(results)*100:.1f}% ===")


def _save(results, t_start) -> None:
    total = sum(r["reward"] for r in results)
    meta = {
        "legionadk_version": LegionADK.__version__,
        "legionadk_path": LegionADK.__file__,
        "model": MODEL,
        "simulator_model": MODEL,
        "provider": "custom",
        "total_tasks": len(results),
        "total_reward": total,
        "accuracy_pct": round(total / len(results) * 100.0, 1) if results else 0.0,
        "total_violations": sum(r["policy_violations"] for r in results),
        "agent_prompt_tokens": sum(r["agent_prompt_tokens"] for r in results),
        "agent_completion_tokens": sum(r["agent_completion_tokens"] for r in results),
        "sim_prompt_tokens": sum(r["sim_prompt_tokens"] for r in results),
        "sim_completion_tokens": sum(r["sim_completion_tokens"] for r in results),
        "elapsed_seconds": round(time.perf_counter() - t_start, 1),
        "reward_rule": "DB akhir agen == DB emas (replay aksi annotator) DAN outputs wajib terucap",
    }
    out = {"meta": meta, "results": results}
    (BASE_DIR / "results_tau.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
