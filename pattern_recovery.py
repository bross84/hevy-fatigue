"""Descriptive pattern signals; provisional smoothing, not measured recovery times."""
from datetime import date, timedelta
from recommendations import MIN_CHECKINS, RESET_GAP_DAYS, RECOVERY_ALPHA

VERSION = 'pattern-recovery-v1'
FIELDS = dict(knee='sore_quad_dom', hip='sore_posterior',push='sore_upper_push',pull='sore_upper_pull')


def load_signal(atl, ctl):
    # Unlike clipped TSB, residual acute load remains visible below baseline.
    return min(1.,max(0.,atl)/(2*ctl)) if ctl > 0 else None


def level(signal):
    return min(5,int(max(0.,min(1.,signal))*5)+1) if signal is not None else None


def build_pattern_history(history, checkins):
    indexed = {str(r['date']): r for r in checkins}
    memory={p:None for p in FIELDS}; last={p:None for p in FIELDS}
    consecutive={p:0 for p in FIELDS}; established={p:False for p in FIELDS}
    exposures={p:[] for p in FIELDS}; result=[]; previous=None
    for row in history:
        day=date.fromisoformat(row['date'])
        if previous:
            for p in FIELDS:
                if previous['pattern_loads'].get(p,{}).get('stress',0)>0:
                    exposures[p].append(date.fromisoformat(previous['date']))
        patterns={}
        for p,field in FIELDS.items():
            pl=row['pattern_loads'].get(p,{})
            # Remove target-day stress before interpreting its morning check-in.
            stress=float(pl.get('stress',0))
            atl=max(0.,float(pl.get('atl',0))-.25*stress)
            ctl=max(0.,float(pl.get('ctl',0))-(2/43)*stress)
            load=load_signal(atl,ctl)
            rating=indexed.get(row['date'],{}).get(field)
            if rating is not None and (not isinstance(rating,(int,float)) or not 0 <= rating <= 4):
                rating=None
            sore=rating/4 if rating is not None else None
            baseline=[d for d in exposures[p] if day-timedelta(days=180)<=d<day]
            baseline_ready=len(baseline)>=3 and min(baseline,default=day)<=day-timedelta(days=28)
            if sore is not None and load is not None:
                raw=max(load,sore)
                gap=(day-last[p]).days if last[p] else None
                if gap is None or gap>RESET_GAP_DAYS:
                    memory[p]=raw;consecutive[p]=1;established[p]=False
                else:
                    consecutive[p]=consecutive[p]+1 if gap==1 else 1
                    memory[p]=max(raw,RECOVERY_ALPHA*raw+(1-RECOVERY_ALPHA)*memory[p])
                last[p]=day
                established[p]=established[p] or consecutive[p]>=MIN_CHECKINS
                ready=baseline_ready and established[p]
                trend=memory[p] if ready else None
            else:
                consecutive[p]=0
                trend=None;ready=False
            patterns[p]=dict(model_version=VERSION,
                load_signal=round(load,4) if load is not None else None,
                load_data_sufficient=baseline_ready, load_dots=level(load) if baseline_ready else None,
                soreness_rating=rating,soreness_signal=sore,soreness_dots=int(rating)+1 if rating is not None else None,
                combined_signal=round(trend,4) if trend is not None else None,
                dots_filled=level(trend),dots_total=5,data_sufficient=ready,
                days_since_loaded=(day-exposures[p][-1]).days if exposures[p] else None)
        result.append(dict(date=row['date'],patterns=patterns))
        previous=row
    return result
