"""Joint coaching calls (#154): a frozen AI Coach conversation about a joint rating above usual.

The call is advice only. The athlete's decision is recorded by their own tap on the decision card
(POST /api/joint/decisions); nothing here changes a plan, a workout or a check-in.
"""
import coaching
import database
import joint_baseline

FIRST_MESSAGE = (
    'This is a joint coaching call: my {regions} joint rating has been above my usual. Using joint_context, '
    'help me work out what is likely causing it — which lifts, what changed recently, where I am in my block — and '
    'whether to accept it, carry on for now, or make a change (a variation, range of motion, swap or lighter load). '
    'Use the movement evidence as context, not proof. Keep it short and plain, give one recommendation with its '
    'reason, and remind me that the decision is mine to record on the card. Do not apply changes.')


def label(context):
    names = ' and '.join(joint_baseline.REGIONS[r]['label'].lower() for r in context['regions'])
    return f"Joint coaching call · {names} joint"


def prepare(db, monitoring, today):
    context = joint_baseline.call_context(db, database, today)
    if context is None:
        raise ValueError('No joint coaching call is due.')
    if db.get(database.CoachingConversation, context['call_id']):
        return coaching.conversation(db, context['call_id'])
    evidence = coaching.build_report(db, today=today, monitoring_context=monitoring)
    evidence['joint_context'] = dict(label=label(context), **context)
    evidence['limitations'] = evidence.get('limitations', []) + [
        'Joint ratings are upper/lower regions only, not a specific joint. The movement report compares check-ins after '
        'days with a lift against other check-ins; it shows association, not cause, and early reads rest on few check-ins.']
    return coaching.save_conversation(db, context['call_id'], evidence)


def first_message(view):
    context = (view.get('evidence') or {}).get('joint_context') or {}
    names = ' and '.join(joint_baseline.REGIONS[r]['label'].lower() for r in context.get('regions', [])) or 'joint'
    return FIRST_MESSAGE.format(regions=names)
