"""Offline, descriptive recommendation replay from read-only API exports.

No imports of either app, database connections, network requests or live writes.
Candidates are experimental stability rules, not validated performance predictors.
"""
import argparse
import csv
import hashlib
from datetime import date, timedelta
import json
from pathlib import Path

LABELS = ('Large Increase', 'Increase', 'Continue', 'Decrease', 'Large Decrease')
BOUNDARIES = (6.0, 8.0, 13.0, 14.0)
VERSION = 'offline-recovery-v1'
RATINGS = ('tiredness', 'perceived_recovery', 'sore_quad_dom',
           'sore_posterior', 'sore_upper_push', 'sore_upper_pull')


def band(score):
    return next((i for i, boundary in enumerate(BOUNDARIES) if score <= boundary), 4)


def subjective(entry):
    if any(entry.get(key) is None for key in RATINGS):
        return None
    if any(not 0 <= entry[key] <= 4 for key in RATINGS):
        raise ValueError('Ratings must use their original 0-4 scale')
    fatigue = round(.45 * entry['tiredness'] / 4
                    + .30 * entry['perceived_recovery'] / 4
                    + .25 * sum(entry[key] for key in RATINGS[2:]) / 16, 3)
    return round(fatigue * 20, 2)


class RecoveryCandidate:
    """Worsening immediate; improvements retain 65% of prior fatigue.

    Guarded mode requires two adjacent observed days beyond a .5-point buffer,
    then improves by at most one band. Missing days never count as confirmation.
    A gap over seven days starts a new segment; its initial label is unconfirmed.
    Parameters are fixed before inspection of results, not fitted to outcomes.
    """
    def __init__(self, guarded=False):
        self.guarded = guarded
        self.memory = self.state = self.previous_day = None
        self.confirmations = 0

    def update(self, day, raw):
        if raw is None:
            self.confirmations = 0
            return None, None, False
        gap = (day - self.previous_day).days if self.previous_day else None
        reset = gap is None or gap > 7
        if reset:
            self.memory, self.state = raw, band(raw)
            self.confirmations = 0
        else:
            self.memory = max(raw, .35 * raw + .65 * self.memory)
            target = band(self.memory)
            if not self.guarded or target >= self.state:
                self.state = target
                self.confirmations = 0
            else:
                qualifies = self.memory <= BOUNDARIES[self.state - 1] - .5
                self.confirmations = (self.confirmations + 1 if gap == 1 else 1) if qualifies else 0
                if self.confirmations >= 2:
                    self.state -= 1
                    self.confirmations = 0
        self.previous_day = day
        return round(self.memory, 4), self.state, reset


def prior_objective(day, workouts):
    # Match dashboard's trailing windows at a pre-workout, date-only cutoff.
    # Target-day workouts and future workouts cannot be used as evidence.
    recent = sum(w['volume'] or 0 for w in workouts
                 if day - timedelta(days=7) <= date.fromisoformat(w['date']) < day)
    baseline = sum(w['volume'] or 0 for w in workouts
                   if day - timedelta(days=180) <= date.fromisoformat(w['date']) < day) / 26
    return round(min(20, recent / baseline * 10) if baseline > 0 else 0, 2)


def replay(checkins, workouts, exported):
    indexed = {r['date']: r for r in checkins}
    if len(indexed) != len(checkins):
        raise ValueError('Duplicate check-in dates require reconciliation')
    if not indexed:
        return []
    exported = {r['date']: r for r in exported}
    smooth, guarded = RecoveryCandidate(), RecoveryCandidate(guarded=True)
    day, end = date.fromisoformat(min(indexed)), date.fromisoformat(max(indexed))
    rows = []
    while day <= end:
        key = day.isoformat()
        entry = indexed.get(key)
        sub = subjective(entry) if entry else None
        obj = prior_objective(day, workouts)
        raw = round(.8 * sub + .2 * obj, 2) if sub is not None else None
        smooth_score, smooth_band, reset = smooth.update(day, raw)
        guarded_score, guarded_band, _ = guarded.update(day, raw)
        rows.append(dict(date=key, subjective=sub, objective_prior_only=obj,
                         current_score=raw, current_band=band(raw) if raw is not None else None,
                         smooth_score=smooth_score, smooth_band=smooth_band,
                         guarded_score=guarded_score, guarded_band=guarded_band,
                         segment_start=reset, joint_concern=any((entry or {}).get(k, 0) or 0 for k in ('joint_upper','joint_lower')),
                         exported_history_score=exported.get(key, {}).get('combined_score')))
        day += timedelta(days=1)
    return rows


def metrics(rows, field):
    observed = [r for r in rows if r[field] is not None]
    pairs = [(a,b) for a,b in zip(rows, rows[1:])
             if a[field] is not None and b[field] is not None]
    flips = 0
    for a,b,c in zip(rows, rows[1:], rows[2:]):
        if all(r[field] is not None for r in (a,b,c)):
            flips += (b[field]-a[field]) * (c[field]-b[field]) < 0
    return dict(observed_days=len(observed), consecutive_pairs=len(pairs),
                changes=sum(a[field] != b[field] for a,b in pairs),
                multiband_jumps=sum(abs(a[field]-b[field]) >= 2 for a,b in pairs),
                reversals_next_day=flips,
                distribution={label:sum(r[field] == i for r in observed) for i,label in enumerate(LABELS)},
                more_conservative_days=sum(r[field] > r['current_band'] for r in observed),
                less_conservative_days=sum(r[field] < r['current_band'] for r in observed))


def report(folder):
    def read(name):
        return json.loads((folder/name).read_text(encoding='utf-8'))
    checkins, workouts = read('hevy-readiness.json'), read('hevy-workouts.json')
    rows = replay(checkins, workouts, read('hevy-combined-history.json'))
    trial = read('rackbook-trial-dashboard.json')
    summary = {key:metrics(rows,key) for key in ('current_band','smooth_band','guarded_band')}
    completed = [r for r in trial['entries'] if r['status'] == 'completed']
    summary['replay'] = dict(model_version=VERSION, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        segment_starts=sum(r['segment_start'] for r in rows), missing_days=sum(r['current_band'] is None for r in rows))
    summary['rackbook'] = dict(total=len(trial['entries']), completed=len(completed),
        classified=sum(r.get('observed') != 'unclassified' and r.get('observed') is not None for r in completed),
        eligible_predictions=sum(c['eligible_predictions'] for c in trial['cohorts']))
    (folder/'replay-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    with (folder/'daily-replay.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    differences=[r for r in rows if r['current_band'] is not None and r['current_band'] != r['guarded_band']]
    lines=['# Offline recommendation replay', '', f'Model: `{VERSION}`. {rows[0]["date"]} through {rows[-1]["date"]}.', '',
        '## Stability on the same observed days', '',
        '| Model | Check-ins | Adjacent-day changes | Jumps of 2+ bands | Next-day reversals |',
        '|---|---:|---:|---:|---:|']
    for key,label in [('current_band','Current formula, prior-day workouts'),('smooth_band','Slower recovery'),('guarded_band','Slower recovery + confirmation')]:
        m=summary[key]
        lines.append(f'| {label} | {m["observed_days"]} | {m["changes"]}/{m["consecutive_pairs"]} | {m["multiband_jumps"]} | {m["reversals_next_day"]} |')
    lines += ['', '## Most recent disagreements', '', '| Date | Raw fatigue | Current | Guarded candidate |', '|---|---:|---|---|']
    for r in differences[-15:]:
        lines.append(f'| {r["date"]} | {r["current_score"]} | {LABELS[r["current_band"]]} | {LABELS[r["guarded_band"]]} |')
    lines += ['', '## Rules and interpretation', '',
        '- Same 80/20 subjective/tonnage signal and recommendation thresholds in all three arms. Only recovery memory and transition rules change.',
        '- Recovery memory: max(today raw score, 35% today + 65% previous memory). Worsening propagates immediately; improvements decay gradually.',
        '- Guarded upgrades: two consecutive check-ins at least 0.5 below the next threshold; one tier per confirmed upgrade. Initial/gap-reset days are unconfirmed segment starts.',
        '- Missing check-ins stay missing, never fresh or recovery confirmation. Gaps over seven days reset state. This is an experimental choice, not a measured recovery time.',
        '- All comparisons exclude target-day and future workouts. This reconstructs a pre-workout dashboard calculation; it is not a log of recommendations actually displayed.',
        '- API workout tonnage is rounded to whole pounds; linked session identity cannot be fully reconciled from these summaries. Small threshold differences are possible.',
        '- The readiness log endpoint converts absent ratings to zero; this export cannot distinguish an original null from an explicit zero.',
        '- Historical ratings can have later edits; original intraday availability and deployed code revisions are unknown. Current mappings/settings are not historical proof.',
        '- Existing history chart scores include target-day workouts and use a different window; retained separately in CSV rather than used as a pre-workout baseline.',
        '- The exports are sequential HTTP reads, not one atomic SQLite snapshot. Inputs were saved with source hashes; no credentials were fetched.',
        '- This isolates transition behavior; it deliberately retains the legacy tonnage signal, weights, caps and thresholds. It does not fix their physiological or modality limitations.',
        '- Stability is not predictive accuracy. More conservative days and delayed recovery may be unnecessary warnings. This replay does not validate the candidate.',
        '- Joint concerns remain separate; candidate labels must not override them. Missing individual ratings invalidate the offline score, although the live legacy model may default them to zero.',
        '', '## Rackbook assimilation', '',
        f'{len(trial["entries"])} records; {len(completed)} completed; {summary["rackbook"]["classified"]} classified outcomes; {summary["rackbook"]["eligible_predictions"]} eligible predictions.',
        'Frozen daily bridge values were available in all five completed records. Reasons include fewer than three comparable exposures, insufficient spacing/workload history, and unresolved related-movement mappings. These are evidence gaps, not measured prediction failures.',
        'The current trial is shared-trial-v0. Do not relabel its frozen predictions or blend daily recommendations into its movement-performance accuracy denominator.',
        'A future shadow arm should record this candidate under its own version, with input cutoff/time, source hashes, state, gaps and proposed action. Link by exact workout and exercise IDs; preserve Rackbook exact weights, RPE and TS flags.',
        'Continue collecting matched strength/hypertrophy outcomes separately. Neither smoother recommendations nor sparse unclassified outcomes justify retiring either app.',
        '', 'Full per-day values: `daily-replay.csv`; counts: `replay-summary.json`; acquisition metadata: `provenance.json`.']
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True,help='Folder of private read-only API exports')
    args=parser.parse_args()
    print(json.dumps(report(args.input),indent=2))
