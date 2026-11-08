"""Coach side of plan proposals: the format it is told to use and the movements it may name."""
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import coaching
from database import Base, WorkoutLog, WorkoutSession
from rackbook import database as logger
from rackbook import plan_proposals

DAY = date(2026, 11, 5)


class BriefTests(TestCase):
    def test_example_matches_the_parser_shape_and_fence(self):
        example = json.loads(coaching.PROPOSAL_EXAMPLE)
        self.assertEqual(plan_proposals.FENCE, example['version'])
        parsed = plan_proposals.Proposal.model_validate(example)
        self.assertEqual(1, len(parsed.sessions))
        self.assertIn('```' + plan_proposals.FENCE, coaching.BRIEF)
        self.assertIn(coaching.PROPOSAL_EXAMPLE, coaching.BRIEF)

    def test_the_brief_example_is_found_by_the_parser_fence(self):
        blocks = plan_proposals.BLOCK.findall(coaching.BRIEF)
        self.assertEqual([coaching.PROPOSAL_EXAMPLE], [b.strip() for b in blocks])

    def test_brief_limits_what_a_proposal_may_do(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('Only when the athlete asks for a concrete training week or plan',
                       'Use only exercise_template_id values listed in known_movements',
                       'Never include weights', 'inactive draft', 'never say a change has been made',
                       'Omit the block when you are only discussing'):
            self.assertIn(phrase, brief)
        self.assertIn('you cannot apply them', brief)


class KnownMovementTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'logging.db'
        self.env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(self.path))
        self.env.start()
        logger.init_db()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def imported(self, identity, days_ago, exercise_id, title):
        day = DAY - timedelta(days=days_ago)
        self.db.add(WorkoutSession(hevy_workout_id=identity, workout_date=day, workout_title='Strength',
                                   start_time=datetime(day.year, day.month, day.day, 17)))
        self.db.add(WorkoutLog(workout_id=identity, date=day, exercise_id=exercise_id, exercise_title=title,
                               set_number=1, weight_lbs=220, reps=5, rpe=8))
        self.db.commit()

    def test_known_movements_cover_history_and_saved_plans_but_not_unidentified_exercises(self):
        self.imported('a', 10, 'sq', 'Squat')
        self.imported('b', 3, 'sq', 'Squat')
        self.imported('c', 5, 'bp', 'Bench Press')
        self.imported('d', 2, None, 'Mystery lift')
        document = dict(name='Plan', weeks=[dict(name='Week 1', sessions=[dict(id='d1', name='Day', exercises=[
            dict(exercise_template_id='row', title='Row', sets=[dict(reps=5)]),
            dict(exercise_template_id='bp', title='Bench Press', sets=[dict(reps=5)])])])])
        with logger.get_db() as conn:
            conn.execute('INSERT INTO mesocycles (id, document, active) VALUES (?, ?, 1)', ('p', json.dumps(document)))
        report = coaching.build_report(self.db, today=DAY)
        known = {m['exercise_template_id']: m for m in report['known_movements']}
        self.assertEqual({'sq', 'bp', 'row'}, set(known))
        self.assertEqual(dict(title='Squat', last_date=str(DAY - timedelta(days=3)), exposure_count=2, in_saved_plan=False,
                              exercise_template_id='sq'), known['sq'])
        self.assertTrue(known['bp']['in_saved_plan'])
        self.assertEqual((None, 0, 'Row'), (known['row']['last_date'], known['row']['exposure_count'], known['row']['title']))
        self.assertEqual(['sq', 'bp', 'row'], [m['exercise_template_id'] for m in report['known_movements']])  # most recent first
        self.assertTrue(any('known_movements' in note for note in report['limitations']))
        json.dumps(report, allow_nan=False)

    def test_known_movements_are_capped(self):
        for index in range(3):
            self.imported(str(index), index + 1, f'id{index}', f'Lift {index}')
        with patch.object(coaching, 'KNOWN_MOVEMENTS', 2):
            report = coaching.build_report(self.db, today=DAY)
        self.assertEqual(['id0', 'id1'], [m['exercise_template_id'] for m in report['known_movements']])

    def test_every_listed_movement_is_accepted_by_the_preview_validator(self):
        self.imported('a', 3, 'sq', 'Squat')
        known = coaching.build_report(self.db, today=DAY)['known_movements']
        with logger.get_db() as conn:
            conn.execute('INSERT INTO hevy_exercise_cache (id, title) VALUES (?, ?)', ('sq', 'Squat'))
        body = dict(version=plan_proposals.FENCE, title='T', rationale='R', sessions=[dict(name='A', exercises=[
            dict(exercise_template_id=known[0]['exercise_template_id'], sets=[dict(reps=5, rpe=7)])])])
        result = plan_proposals.preview('```plan-proposal-v1\n' + json.dumps(body) + '\n```')
        self.assertTrue(result['valid'], result)
