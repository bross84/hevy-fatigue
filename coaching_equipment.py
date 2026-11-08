"""The athlete's available equipment: stored on the host and given to the AI coach as context.

Host-only (SQLAlchemy app_settings). It never touches the logging database. The coach reads it
through coaching.build_report, so each saved conversation freezes the list with its other evidence.
"""
from datetime import datetime, timezone
import json

from database import AppSetting

SETTING_KEY = 'coach_equipment'
MAX_NOTES = 1000
# (id, label), in display order. Ids are the stored contract; labels are what the coach reads.
CATALOG = (
    ('barbell', 'Barbell and plates'),
    ('rack', 'Squat or power rack'),
    ('bench', 'Bench (flat or adjustable)'),
    ('trap_bar', 'Trap / hex bar'),
    ('ez_bar', 'EZ-curl bar'),
    ('dumbbells', 'Dumbbells'),
    ('kettlebells', 'Kettlebells'),
    ('cable', 'Cable machine'),
    ('lat_pulldown', 'Lat pulldown'),
    ('leg_press', 'Leg press'),
    ('leg_machines', 'Leg curl / extension machines'),
    ('smith', 'Smith machine'),
    ('machines', 'Other selectorized or plate-loaded machines'),
    ('pullup_bar', 'Pull-up bar'),
    ('dip_station', 'Dip station'),
    ('rings', 'Rings or suspension trainer'),
    ('bands', 'Resistance bands'),
    ('box', 'Plyo box or step'),
    ('sled', 'Sled'),
    ('cardio', 'Cardio machine'),
)
LABELS = dict(CATALOG)


class EquipmentError(ValueError):
    """A save the athlete can correct; the message is safe to show."""


def catalog():
    return [dict(id=i, label=label) for i, label in CATALOG]


def normalize(items, notes):
    """(ids in catalog order without duplicates, trimmed notes). Unknown ids are an error, never dropped."""
    requested = list(items or [])
    unknown = sorted({str(i) for i in requested if i not in LABELS})
    if unknown:
        raise EquipmentError('Unknown equipment: ' + ', '.join(unknown))
    notes = (notes or '').strip()
    if len(notes) > MAX_NOTES:
        raise EquipmentError(f'Equipment notes are limited to {MAX_NOTES} characters.')
    chosen = set(requested)
    return [i for i, _ in CATALOG if i in chosen], notes


def load(db):
    """Stored state as the API shows it. Not set is unknown, never 'no equipment'."""
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    try:
        data = json.loads(row.value) if row and row.value else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return dict(configured=False, items=[], notes='', saved_at=None)
    try:
        items, notes = normalize(data.get('items'), data.get('notes'))
    except EquipmentError:
        # A catalog id removed in a later release: keep what is still valid rather than hide everything.
        items = [i for i, _ in CATALOG if i in set(data.get('items') or [])]
        notes = str(data.get('notes') or '').strip()[:MAX_NOTES]
    return dict(configured=bool(items or notes), items=items, notes=notes, saved_at=data.get('saved_at'))


def save(db, items, notes):
    """Store the list; an empty list with no notes clears it back to not set."""
    items, notes = normalize(items, notes)
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if not items and not notes:
        if row:
            db.delete(row)
        db.commit()
        return load(db)
    value = json.dumps(dict(items=items, notes=notes, saved_at=datetime.now(timezone.utc).isoformat()),
                       ensure_ascii=False, separators=(',', ':'))
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=SETTING_KEY, value=value))
    db.commit()
    return load(db)


def for_report(db):
    """The block build_report embeds: labels for the coach, or an explicit not-set marker."""
    state = load(db)
    if not state['configured']:
        return dict(status='not_set')
    return dict(status='set', items=[LABELS[i] for i in state['items']], notes=state['notes'],
                saved_at=state['saved_at'])


LIMITATION = ('available_equipment is the athlete\'s own saved list. status not_set means unknown, not that '
              'they have none. known_movements are past movements and do not prove the equipment exists today.')
