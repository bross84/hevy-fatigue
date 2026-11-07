"""Streamed-reply relay: how a reply ends is decided here, with plain chunks and no network."""
import json
from unittest import TestCase
from unittest.mock import patch

import coaching
import coaching_stream


def delta(text):
    return 'data: ' + json.dumps({'choices': [{'delta': {'content': text}}]}) + '\n\n'


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, content, status):
        self.calls.append((content, status))


class RelayTests(TestCase):
    def run_relay(self, chunks, **kwargs):
        recorder = Recorder()
        closed = []
        events = ''.join(coaching_stream.relay(iter(chunks), recorder, close=lambda: closed.append(True), **kwargs))
        return events, recorder.calls, closed

    def test_complete_reply_is_recorded_once_and_forwarded(self):
        events, calls, closed = self.run_relay([delta('Keep '), delta('going.') + 'data: [DONE]\n\n'])
        self.assertEqual(calls, [('Keep going.', 'complete')])
        self.assertTrue(events.endswith('data: [DONE]\n\n'))
        self.assertIn('Keep ', events)
        self.assertEqual(closed, [True])

    def test_events_split_across_chunks_are_reassembled(self):
        whole = delta('Split reply') + 'data: [DONE]\n\n'
        events, calls, _ = self.run_relay([whole[:15], whole[15:40], whole[40:]])
        self.assertEqual(calls, [('Split reply', 'complete')])

    def test_stream_ending_without_done_is_interrupted_with_the_partial_text(self):
        events, calls, closed = self.run_relay([delta('Partial')])
        self.assertEqual(calls, [('Partial', 'interrupted')])
        self.assertIn('Response interrupted', events)
        self.assertEqual(closed, [True])

    def test_provider_error_event_is_failed(self):
        _, calls, _ = self.run_relay(['data: {"error":{"message":"boom"}}\n\ndata: [DONE]\n\n'])
        self.assertEqual(calls[0][1], 'failed')

    def test_truncated_or_filtered_reply_is_failed(self):
        chunk = 'data: ' + json.dumps({'choices': [{'delta': {'content': 'cut'}, 'finish_reason': 'length'}]}) + '\n\ndata: [DONE]\n\n'
        _, calls, _ = self.run_relay([chunk])
        self.assertEqual(calls, [('cut', 'failed')])

    def test_empty_reply_is_failed_not_complete(self):
        _, calls, _ = self.run_relay(['data: [DONE]\n\n'])
        self.assertEqual(calls, [('', 'failed')])

    def test_unreadable_event_marks_failure(self):
        _, calls, _ = self.run_relay(['data: not-json\n\n' + delta('ok') + 'data: [DONE]\n\n'])
        self.assertEqual(calls, [('ok', 'failed')])

    def test_reply_over_the_limit_is_stopped_and_recorded_as_interrupted(self):
        with patch.object(coaching, 'MAX_REPLY_CHARS', 10):
            events, calls, closed = self.run_relay([delta('x' * 25), delta('never read') + 'data: [DONE]\n\n'])
        self.assertEqual(calls, [('x' * 10, 'interrupted')])
        self.assertIn('no automatic resend', events)
        self.assertEqual(closed, [True])

    def test_connection_dropping_mid_reply_is_interrupted(self):
        def chunks():
            yield delta('Before the drop')
            raise ConnectionError('lost')
        recorder = Recorder()
        events = ''.join(coaching_stream.relay(chunks(), recorder))
        self.assertEqual(recorder.calls, [('Before the drop', 'interrupted')])
        self.assertIn('no automatic resend', events)

    def test_failing_recorder_does_not_claim_the_reply_was_saved(self):
        def broken(content, status):
            raise RuntimeError('database unavailable')
        events = ''.join(coaching_stream.relay(iter([delta('Reply') + 'data: [DONE]\n\n']), broken))
        self.assertIn('no automatic resend', events)
        self.assertNotIn('[DONE]', events)

    def test_plain_chat_forwards_untouched_and_tracks_nothing(self):
        raw = 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
        closed = []
        events = ''.join(coaching_stream.relay(iter([raw]), close=lambda: closed.append(True)))
        self.assertEqual(events, raw)
        self.assertEqual(closed, [True])
