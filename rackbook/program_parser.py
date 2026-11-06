"""
program_parser.py — Pure parser for Rackbook program notation text.
No DB access, no HTTP calls, no side effects.
"""
from __future__ import annotations

import re
from typing import Any

# Three-level header: {block}.{microcycle}.{day} [optional rest-of-line]
_DAY_PREFIX = re.compile(r'^(\d+)\.(\d+)\.(\d+)(?:\s+(.*))?$', re.DOTALL)

_SOURCE_TM   = re.compile(r'^TM(\d+(?:\.\d+)?)$', re.IGNORECASE)
_SOURCE_E1RM = re.compile(r'^e1RM$', re.IGNORECASE)
_SOURCE_DDP  = re.compile(r'^DDP(?:\+(\d+(?:\.\d+)?))?$', re.IGNORECASE)

# Set group patterns (matched after source tag is stripped)
_BBB    = re.compile(r'^(\d+)x(\d+)\s+@\.(\d+)\s+e1RM$', re.IGNORECASE)   # 5x10 @.65 e1RM
_JOKER  = re.compile(r'^(\d+)x1[Jj]\s+\+([\d,]+)$')                         # 3x1J +10,15,20
_NX_RPE = re.compile(r'^(\d+)x(\d+)@([\d.]+)(\+?)$')                        # 3x5@7 or 3x5@7+
_NX_FREE = re.compile(r'^(\d+)x(\d+)$')                                      # 5x10
_RPE_LIST = re.compile(r'^(\d+)@([\d.,+]+)$')                                # 5@5,6,7+ or 5@5,6,7
_WAVE_SET = re.compile(r'^(\d+)@([\d.]+)(\+?)$')                             # single wave entry: 5@7 or 1@8+


def _extract_source_tag(tokens: list[str]) -> tuple[list[str], dict[str, Any] | None]:
    if not tokens:
        return tokens, None
    last = tokens[-1]
    tm_m = _SOURCE_TM.match(last)
    if tm_m:
        return tokens[:-1], {"source": "tm", "wm_pct": float(tm_m.group(1)) / 100}
    if _SOURCE_E1RM.match(last):
        return tokens[:-1], {"source": "e1rm"}
    ddp_m = _SOURCE_DDP.match(last)
    if ddp_m:
        inc = float(ddp_m.group(1)) if ddp_m.group(1) else 2.5
        return tokens[:-1], {"source": "ddp", "increment_kg": inc}
    return tokens, None


def _parse_group(raw: str, line_num: int, errors: list[dict]) -> tuple[list[dict], dict[str, Any] | None]:
    """Parse one set group string. Returns (sets, source_params_or_None)."""
    raw = raw.strip()
    if not raw:
        return [], None

    # BBB: uniquely identified by @.XX e1RM suffix — check before extracting source tag
    bbb_m = _BBB.match(raw)
    if bbb_m:
        n = int(bbb_m.group(1))
        reps = int(bbb_m.group(2))
        pct = int(bbb_m.group(3)) / 100
        sets = [
            {"reps": reps, "target_rpe": None, "is_amrap": False, "is_joker": False,
             "bbb_pct": pct, "bbb_source": "e1rm"}
            for _ in range(n)
        ]
        return sets, {"source": "e1rm"}

    # Strip trailing source tag before matching set patterns
    tokens = raw.split()
    tokens, source_params = _extract_source_tag(tokens)
    expr = " ".join(tokens).strip()

    # Joker: 3x1J +10,15,20
    joker_m = _JOKER.match(expr)
    if joker_m:
        pct_parts = joker_m.group(2).split(",")
        sets = [
            {"reps": 1, "target_rpe": None, "is_amrap": False, "is_joker": True,
             "joker_jump_pct": float(p) / 100}
            for p in pct_parts
        ]
        return sets, source_params

    # NxReps@RPE with optional + for last-set AMRAP
    nxrpe_m = _NX_RPE.match(expr)
    if nxrpe_m:
        n = int(nxrpe_m.group(1))
        reps = int(nxrpe_m.group(2))
        rpe = float(nxrpe_m.group(3))
        last_is_amrap = nxrpe_m.group(4) == "+"
        sets = [
            {"reps": reps, "target_rpe": rpe,
             "is_amrap": (i == n - 1 and last_is_amrap), "is_joker": False}
            for i in range(n)
        ]
        return sets, source_params

    # NxReps (free — no RPE)
    nxfree_m = _NX_FREE.match(expr)
    if nxfree_m:
        n = int(nxfree_m.group(1))
        reps = int(nxfree_m.group(2))
        sets = [
            {"reps": reps, "target_rpe": None, "is_amrap": False, "is_joker": False}
            for _ in range(n)
        ]
        return sets, source_params

    # Wave sets: 5@5,3@6,1@7+ — each token is reps@rpe, last + means AMRAP
    wave_tokens = [t.strip() for t in expr.split(",")]
    if len(wave_tokens) > 1 and all(_WAVE_SET.match(t) for t in wave_tokens):
        sets = []
        for idx, token in enumerate(wave_tokens):
            m = _WAVE_SET.match(token)
            reps = int(m.group(1))
            rpe = float(m.group(2))
            is_amrap = m.group(3) == "+" and idx == len(wave_tokens) - 1
            sets.append({"reps": reps, "target_rpe": rpe, "is_amrap": is_amrap, "is_joker": False})
        return sets, source_params

    # RPE list: reps@rpe1,rpe2,...  — trailing + on last RPE means AMRAP
    rpe_list_m = _RPE_LIST.match(expr)
    if rpe_list_m:
        reps = int(rpe_list_m.group(1))
        raw_rpes = rpe_list_m.group(2).split(",")
        last_is_amrap = raw_rpes[-1].endswith("+")
        rpe_values = [float(r.rstrip("+")) for r in raw_rpes]
        sets = [
            {"reps": reps, "target_rpe": rpe,
             "is_amrap": (i == len(rpe_values) - 1 and last_is_amrap), "is_joker": False}
            for i, rpe in enumerate(rpe_values)
        ]
        return sets, source_params

    errors.append({"line": line_num, "message": f"Unrecognised set group: {raw!r}"})
    return [], source_params


def _parse_slot_line(
    exercise_name: str,
    sets_str: str,
    slot_order: int,
    line_num: int,
    errors: list[dict],
) -> dict[str, Any] | None:
    groups = [g.strip() for g in sets_str.split(" / ") if g.strip()]
    if not groups:
        errors.append({"line": line_num, "message": "No set groups found."})
        return None

    all_sets: list[dict] = []
    source_params: dict[str, Any] | None = None

    for g in groups:
        grp_sets, grp_source = _parse_group(g, line_num, errors)
        all_sets.extend(grp_sets)
        if grp_source is not None and source_params is None:
            source_params = grp_source

    if source_params is None:
        source_params = {"source": "free"}

    working_rpes = [
        s["target_rpe"]
        for s in all_sets
        if not s.get("is_joker") and s.get("target_rpe") is not None
    ]
    slot_target_rpe = max(working_rpes) if working_rpes else None

    return {
        "exercise_name": exercise_name.strip(),
        "slot_order": slot_order,
        "source_params": source_params,
        "target_rpe": slot_target_rpe,
        "sets": all_sets,
    }


def parse_program(text: str) -> dict[str, Any]:
    """
    Parse program notation text.
    Returns {"blocks": [...], "errors": [{"line": N, "message": "..."}]}.
    """
    lines = text.splitlines()
    errors: list[dict] = []
    # (block_num, cycle_num, day_num) → list of slots
    days: dict[tuple[int, int, int], list[dict]] = {}
    current_context: tuple[int, int, int] | None = None

    for raw_idx, raw_line in enumerate(lines):
        line_num = raw_idx + 1
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        prefix_m = _DAY_PREFIX.match(line)
        if prefix_m:
            current_context = (
                int(prefix_m.group(1)),
                int(prefix_m.group(2)),
                int(prefix_m.group(3)),
            )
            line = (prefix_m.group(4) or "").strip()
            if not line:
                continue  # header-only line with no exercise on same line

        if current_context is None:
            errors.append({
                "line": line_num,
                "message": "No day context — line must start with {block}.{cycle}.{day}",
            })
            continue

        if " - " not in line:
            errors.append({"line": line_num, "message": f"Missing ' - ' separator: {line!r}"})
            continue

        exercise_name, sets_str = line.rsplit(" - ", 1)
        exercise_name = exercise_name.strip()
        sets_str = sets_str.strip()

        if not exercise_name:
            errors.append({"line": line_num, "message": "Empty exercise name."})
            continue
        if not sets_str:
            errors.append({"line": line_num, "message": "Empty set specification."})
            continue

        key = current_context
        if key not in days:
            days[key] = []
        slot = _parse_slot_line(exercise_name, sets_str, len(days[key]), line_num, errors)
        if slot is not None:
            days[key].append(slot)

    # Assemble three-level output
    by_block: dict[int, dict[int, list[dict]]] = {}
    for (block_num, cycle_num, day_num), slots in sorted(days.items()):
        by_cycle = by_block.setdefault(block_num, {})
        by_cycle.setdefault(cycle_num, []).append({"day_number": day_num, "slots": slots})

    blocks = [
        {
            "block_number": bn,
            "label": f"Block {bn}",
            "microcycles": [
                {
                    "cycle_number": cn,
                    "label": f"Micro {cn}",
                    "days": sorted(day_list, key=lambda d: d["day_number"]),
                }
                for cn, day_list in sorted(by_cycle.items())
            ],
        }
        for bn, by_cycle in sorted(by_block.items())
    ]

    return {"blocks": blocks, "errors": errors}
