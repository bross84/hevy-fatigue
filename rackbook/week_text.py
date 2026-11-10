"""Pure reader for a training week written as text. No database, no HTTP, no side effects.

    Week 3 Day 1
    #squat, low bar w/ belt 1x3@8 TS, 3x5@7 BO
    #bench press 5x4@6 DDP
    #lateral raise myo 15-20@9

`Week N Day N` starts a training day (training order, not weekdays). `#name` is a movement and is
matched against the athlete's movement list exactly (case and spacing ignored); it is never guessed.
`3x5` is sets x reps (x, X or ×), `@7` the prescribed RPE and `@6,7,8` one RPE per set. A comma
followed by new sets x reps starts another group of sets. Callouts: TS top set, BO back-off,
`+` AMRAP last set, DS / DS2 drop sets, `myo 15-20@9`, DDP and TM90. ME and RE are accepted and
ignored: plans carry no effort labels (ADR 0002). Anything else, `*` included, is reported with
its line number and never dropped silently.
"""
from __future__ import annotations

import re
from typing import Any

MAX_TEXT_CHARS = 20_000
MAX_DAYS = 14
MAX_MOVEMENTS = 30
MAX_SETS = 50
MAX_SUGGESTIONS = 8

_HEADER = re.compile(r'^week\s+(\d{1,4})\s+day\s+(\d{1,2})\s*:?$', re.IGNORECASE)
_LOOKS_LIKE_HEADER = re.compile(r'^week\b', re.IGNORECASE)
# Where a group of sets begins: optional ignored label, then "3x5" or "myo".
_GROUP_START = r'(?:(?:ME|RE)\s+)?(?:\d+\s*[x×]\s*\d|myo\b)'
_STARTS_GROUP = re.compile(_GROUP_START, re.IGNORECASE)
_GROUP_SPLIT = re.compile(r',\s*(?=' + _GROUP_START + r')', re.IGNORECASE)
_GROUP = re.compile(
    r'''^(?:(?:ME|RE)\s+)?
    (?:(?P<sets>\d+)\s*[x×]\s*(?P<reps>\d+)(?P<range>\s*-\s*\d+)?(?P<amrap>\+)?
      |myo\s+(?P<lo>\d+)(?:\s*-\s*(?P<hi>\d+))?)
    \s*(?:@\s*(?P<rpe>\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*))?
    (?P<rest>.*)$''', re.IGNORECASE | re.VERBOSE)
_DROPS = re.compile(r'^DS(\d+)?$', re.IGNORECASE)
_TM = re.compile(r'^TM(\d+)?$', re.IGNORECASE)
CALLOUT_HELP = 'Callouts are TS, BO, DS, DS2, DDP, TM90 and + after the reps for AMRAP.'


def normalise(name: str) -> str:
    return ' '.join(name.split()).casefold()


def _blank_set(reps: int) -> dict[str, Any]:
    return dict(reps=reps, reps_max=None, rpe=None, ts=False, amrap=False, backoff=False,
                ddp=False, myo=False, drops=None, drops_open=False)


def _rpe_values(raw: str | None, line: int, errors: list) -> list[float] | None:
    if raw is None:
        return []
    values = []
    for part in raw.split(','):
        value = float(part)
        if not 4 <= value <= 10 or value * 2 != int(value * 2):
            errors.append(dict(line=line, message=f'RPE {part.strip()} must be between 4 and 10 in half steps.'))
            return None
        values.append(value)
    return values


def _group(raw: str, line: int, errors: list) -> tuple[list[dict], int | None] | None:
    """One group such as `1x3@8 TS` → (sets, TM percentage or None). Appends an error and returns None
    when anything in the group is not understood."""
    match = _GROUP.match(raw.strip())
    if not match:
        errors.append(dict(line=line, message=f'Could not read the sets "{raw.strip()}". Write them like 3x5@7.'))
        return None
    if match['range']:
        errors.append(dict(line=line, message=f'Rep ranges like "{raw.strip()}" are not supported yet (only with myo).'))
        return None
    rpes = _rpe_values(match['rpe'], line, errors)
    if rpes is None:
        return None
    flags, tm = set(), None
    for token in match['rest'].split():
        upper = token.upper()
        drops, tm_match = _DROPS.match(token), _TM.match(token)
        if '*' in token:
            where = '' if token == '*' else f' (in "{token}")'
            errors.append(dict(line=line, message=f'The * has no meaning here{where}. Remove it, or use a callout. {CALLOUT_HELP}'))
            return None
        if upper in ('ME', 'RE'):
            continue  # Effort labels are accepted and ignored.
        if upper in ('TS', 'BO', 'DDP'):
            flags.add(upper)
        elif drops:
            count = int(drops[1]) if drops[1] else None
            if count is not None and not 1 <= count <= 10:
                errors.append(dict(line=line, message=f'{token}: drop sets go from DS1 to DS10.'))
                return None
            flags.add(('DS', count))
        elif tm_match:
            if not tm_match[1]:
                errors.append(dict(line=line, message='TM needs a percentage, for example TM90.'))
                return None
            tm = int(tm_match[1])
            if not 50 <= tm <= 100:
                errors.append(dict(line=line, message=f'{token}: the TM percentage must be between 50 and 100.'))
                return None
        else:
            errors.append(dict(line=line, message=f'Unknown callout "{token}". {CALLOUT_HELP}'))
            return None
    drop_flags = [f for f in flags if isinstance(f, tuple)]
    if len(drop_flags) > 1:
        errors.append(dict(line=line, message='Write drop sets once per group.'))
        return None

    if match['lo'] is not None:
        lo, hi = int(match['lo']), int(match['hi']) if match['hi'] else None
        if not 1 <= lo <= 100 or (hi is not None and not lo < hi <= 100):
            errors.append(dict(line=line, message=f'Myo-reps target "{raw.strip()}" must be reps like 15-20, up to 100.'))
            return None
        if flags:
            errors.append(dict(line=line, message='Myo-reps take only a rep target and an RPE, for example myo 15-20@9 (TM90 is allowed).'))
            return None
        if len(rpes) > 1:
            errors.append(dict(line=line, message='Myo-reps take one RPE, for example myo 15-20@9.'))
            return None
        one = dict(_blank_set(lo), reps_max=hi, rpe=rpes[0] if rpes else None, myo=True)
        return [one], tm

    count, reps = int(match['sets']), int(match['reps'])
    if not 1 <= count <= MAX_SETS or not 1 <= reps <= 100:
        errors.append(dict(line=line, message=f'"{raw.strip()}": use 1 to {MAX_SETS} sets of 1 to 100 reps.'))
        return None
    if len(rpes) > 1 and len(rpes) != count:
        errors.append(dict(line=line, message=f'"{raw.strip()}" has {count} sets but {len(rpes)} RPE values. Give one RPE, or one per set.'))
        return None
    if 'TS' in flags and count != 1:
        errors.append(dict(line=line, message='TS marks one set. Write it as its own group, for example 1x3@8 TS, 3x5@7 BO.'))
        return None
    if 'TS' in flags and 'BO' in flags:
        errors.append(dict(line=line, message='A set cannot be both TS and BO.'))
        return None
    sets = []
    for index in range(count):
        one = _blank_set(reps)
        one['rpe'] = (rpes[index] if len(rpes) > 1 else rpes[0]) if rpes else None
        one['ts'] = 'TS' in flags
        one['backoff'] = 'BO' in flags
        one['ddp'] = 'DDP' in flags
        sets.append(one)
    if match['amrap']:
        sets[-1]['amrap'] = True
    if drop_flags:
        drop_count = drop_flags[0][1]
        sets[-1]['drops'] = drop_count
        sets[-1]['drops_open'] = drop_count is None
    return sets, tm


def _split_name(rest: str) -> list[tuple[str, str]]:
    """Every place the movement name could end: right before a word that starts a group of sets."""
    found = []
    for match in re.finditer(r'\s+', rest):
        spec = rest[match.end():]
        if _STARTS_GROUP.match(spec):
            found.append((rest[:match.start()].strip(), spec.strip()))
    return found


def _suggestions(name: str, titles: dict[str, str]) -> list[dict[str, str]]:
    terms = [t for t in re.split(r'[\s,()/]+', normalise(name)) if t]
    hits = [dict(id=key, title=title) for key, title in titles.items()
            if terms and all(t in title.casefold() for t in terms)]
    if not hits and terms:  # Loosen to any word so the athlete still has a list to choose from.
        hits = [dict(id=key, title=title) for key, title in titles.items() if any(t in title.casefold() for t in terms)]
    return sorted(hits, key=lambda h: (len(h['title']), h['title'].casefold()))[:MAX_SUGGESTIONS]


def _movement(rest: str, line: int, titles: dict[str, str], by_name: dict[str, list[str]],
              choices: dict[str, str], errors: list) -> dict[str, Any] | None:
    candidates = _split_name(rest)
    candidates = [(name, spec) for name, spec in candidates if name]
    if not candidates:
        errors.append(dict(line=line, message='No sets found after the movement name. Write them like #squat 3x5@7.'))
        return None
    # The longest name that is exactly a known movement wins; otherwise the name ends before the first sets.
    known = [(name, spec) for name, spec in candidates if normalise(name) in by_name]
    name, spec = max(known, key=lambda c: len(c[0])) if known else candidates[0]
    key = normalise(name)

    sets, tm = [], None
    group_errors: list = []
    for raw in _GROUP_SPLIT.split(spec):
        parsed = _group(raw, line, group_errors)
        if parsed is None:
            continue
        group_sets, group_tm = parsed
        if group_tm is not None:
            if tm is not None and tm != group_tm:
                group_errors.append(dict(line=line, message=f'Two different TM percentages (TM{tm} and TM{group_tm}). Use one per movement.'))
            tm = group_tm
        sets.extend(group_sets)
    if not group_errors:
        if len(sets) > MAX_SETS:
            group_errors.append(dict(line=line, message=f'A movement can have up to {MAX_SETS} sets.'))
        if sum(s['ts'] for s in sets) > 1:
            group_errors.append(dict(line=line, message='Only one TS per movement.'))
    errors.extend(group_errors)

    ids = by_name.get(key, [])
    chosen = choices.get(key)
    if chosen in titles:
        status, template_id, options = 'chosen', chosen, []
    elif len(ids) == 1:
        status, template_id, options = 'matched', ids[0], []
    elif ids:
        status, template_id = 'ambiguous', None
        options = [dict(id=i, title=titles[i]) for i in ids]
    else:
        status, template_id, options = 'unresolved', None, _suggestions(name, titles)
    return dict(line=line, name=name, key=key, status=status, exercise_template_id=template_id,
                title=titles[template_id] if template_id else None, choices=options,
                tm_pct=tm, sets=sets, valid=not group_errors)


def parse_week_text(text: str, titles: dict[str, str], choices: dict[str, str] | None = None) -> dict[str, Any]:
    """Read the text into weeks → days → movements → sets.

    `titles` is {movement id: title} from the athlete's own list. `choices` is {normalised name:
    movement id} the athlete picked for names that did not match exactly. Returns
    {"weeks": [...], "errors": [{"line", "message"}], "unresolved": [names], "ready": bool}.
    """
    choices = choices or {}
    errors: list[dict] = []
    if len(text) > MAX_TEXT_CHARS:
        return dict(weeks=[], errors=[dict(line=0, message=f'The text is longer than {MAX_TEXT_CHARS} characters.')],
                    unresolved=[], ready=False)
    by_name: dict[str, list[str]] = {}
    for key, title in titles.items():
        by_name.setdefault(normalise(title), []).append(key)

    days: dict[tuple[int, int], dict] = {}
    current: tuple[int, int] | None = None
    for index, raw in enumerate(text.splitlines()):
        line, stripped = index + 1, raw.strip()
        if not stripped:
            continue
        header = _HEADER.match(stripped)
        if header:
            week, day = int(header[1]), int(header[2])
            if week < 1 or not 1 <= day <= MAX_DAYS:
                errors.append(dict(line=line, message=f'Use week numbers from 1 and day numbers from 1 to {MAX_DAYS}.'))
                current = None
                continue
            if (week, day) in days:
                errors.append(dict(line=line, message=f'Week {week} Day {day} already started on line {days[(week, day)]["line"]}.'))
                current = None
                continue
            current = (week, day)
            days[current] = dict(day=day, line=line, exercises=[])
            continue
        if _LOOKS_LIKE_HEADER.match(stripped):
            errors.append(dict(line=line, message='Write a day heading as "Week 1 Day 1".'))
            current = None
            continue
        if not stripped.startswith('#'):
            errors.append(dict(line=line, message='Expected "Week N Day N" or a movement starting with #.'))
            continue
        if current is None:
            errors.append(dict(line=line, message='Start with a "Week N Day N" line before the movements.'))
            continue
        movement = _movement(stripped[1:].strip(), line, titles, by_name, choices, errors)
        if movement is None:
            continue
        if len(days[current]['exercises']) >= MAX_MOVEMENTS:
            errors.append(dict(line=line, message=f'A day can have up to {MAX_MOVEMENTS} movements.'))
            continue
        days[current]['exercises'].append(movement)

    weeks: dict[int, list[dict]] = {}
    for (week, _), day in sorted(days.items()):
        weeks.setdefault(week, []).append(day)
    for week, day_list in weeks.items():
        empty = [d for d in day_list if not d['exercises']]
        for day in empty:
            errors.append(dict(line=day['line'], message=f'Week {week} Day {day["day"]} has no movements.'))
    if not days and not errors:
        errors.append(dict(line=0, message='Nothing to read yet. Start with "Week 1 Day 1".'))

    errors.sort(key=lambda e: e['line'])
    unresolved = sorted({m['name'] for d in days.values() for m in d['exercises'] if m['exercise_template_id'] is None},
                        key=str.casefold)
    return dict(weeks=[dict(week=w, days=d) for w, d in sorted(weeks.items())], errors=errors,
                unresolved=unresolved, ready=bool(days) and not errors and not unresolved)


def plan_sessions(week: dict[str, Any], new_id) -> list[dict[str, Any]]:
    """Builder sessions for one read week. Weights stay blank so the Log page plans the loads."""
    return [dict(id=new_id(), name=f'Day {index}', exercises=[
        dict(exercise_template_id=m['exercise_template_id'], title=m['title'], notes='', tm_pct=m['tm_pct'],
             sets=[dict(s, weight_kg=None, type='normal') for s in m['sets']])
        for m in day['exercises']]) for index, day in enumerate(week['days'], 1)]
