"""Descriptive personal reference ranges; never changes monitoring scores/states."""
from datetime import date, timedelta
from collections import deque
import math
from statistics import median

WINDOW_DAYS = 84
MIN_OBSERVATIONS = 14
MIN_SPAN_DAYS = 28


def percentile(values, fraction):
    position = (len(values) - 1) * fraction
    lower = int(position)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)


def historical_ranges(history):
    """Each point uses only prior valid observations, independent of chart slicing."""
    result = []
    prior = deque()
    for row in history:
        day = date.fromisoformat(row['date'])
        start = day - timedelta(days=WINDOW_DAYS)
        while prior and prior[0]['date'] < str(start):
            prior.popleft()
        values = sorted(r['smoothed_score'] for r in prior)
        span = (date.fromisoformat(prior[-1]['date']) - date.fromisoformat(prior[0]['date'])).days + 1 if prior else 0
        sufficient = len(values) >= MIN_OBSERVATIONS and span >= MIN_SPAN_DAYS
        reference = dict(window_days=WINDOW_DAYS, start=str(start), end=str(day-timedelta(days=1)),
                         observations=len(values), observed_span_days=span,
                         missing_or_ineligible_days=WINDOW_DAYS-len(values), sufficient=sufficient,
                         minimum_observations=MIN_OBSERVATIONS, minimum_span_days=MIN_SPAN_DAYS,
                         lower=round(percentile(values,.1),2) if sufficient else None,
                         upper=round(percentile(values,.9),2) if sufficient else None,
                         median=round(median(values),2) if sufficient else None,
                         method='Prior 84 days; 10th–90th percentile of eligible smoothed scores. Descriptive, not a recovery or performance threshold.')
        score = row.get('smoothed_score') if row.get('data_sufficient') else None
        position = ('below_usual' if score < reference['lower'] else 'above_usual' if score > reference['upper'] else 'usual') if sufficient and score is not None else 'unavailable'
        result.append({**row, 'historical_range':reference, 'historical_position':position})
        if row.get('data_sufficient') and row.get('smoothed_score') is not None and math.isfinite(row['smoothed_score']):
            prior.append(row)
    return result
