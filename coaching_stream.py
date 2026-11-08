"""Relay a model's streamed reply to the browser while recording how it ended.

Pure of HTTP and web-framework concerns: it consumes text chunks and yields the
server-sent events the browser already expects. The provider connection stays with
the caller, so tests can feed plain chunks instead of mocking a network client.
"""
import inspect
import json

import coaching

REASON_CHARS = 300


def clip(text, limit=REASON_CHARS):
    """One plain line of at most `limit` characters; used for every stored failure reason."""
    line = ' '.join(str(text).split())
    return line if len(line) <= limit else line[:limit - 1].rstrip() + '…'


def _provider_message(error):
    message = error.get('message') or error.get('type') if isinstance(error, dict) else error
    return clip(message, 160) if isinstance(message, str) and message.strip() else None


def _record(on_finish, content, status, reason):
    """Call `on_finish(content, status)`, adding `reason` only for callbacks that declare a third parameter."""
    try:
        positional = [p for p in inspect.signature(on_finish).parameters.values()
                      if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    except (TypeError, ValueError):
        positional = []
    if reason and len(positional) >= 3:
        on_finish(content, status, reason)
    else:
        on_finish(content, status)


def relay(chunks, on_finish=None, close=None):
    """Yield server-sent events for `chunks`, calling `on_finish(content, status[, reason])` once.

    `status` is 'complete', 'failed' or 'interrupted'. A callback that accepts a third
    parameter also receives a short plain-text `reason` for a failed or interrupted
    reply. With no `on_finish` (plain chat) events are forwarded untouched and nothing is
    tracked. `close` always runs last. A reply that never finalizes is recorded as
    interrupted and never resent.
    """
    accumulated = ''
    finalized = False
    failed = False
    reason = None
    try:
        buffer = ""
        for chunk in chunks:
            buffer += chunk.replace('\r\n', '\n')
            while "\n\n" in buffer:
                event, buffer = buffer.split("\n\n", 1)
                for line in event.splitlines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        if on_finish:
                            if not accumulated.strip() and not failed:
                                reason = 'The model returned an empty reply.'
                            _record(on_finish, accumulated, 'complete' if accumulated.strip() and not failed else 'failed', reason)
                            finalized = True
                        yield "data: [DONE]\n\n"
                        return
                    if on_finish:
                        try:
                            event_data = json.loads(raw)
                            if event_data.get('error'):
                                failed = True
                                detail = _provider_message(event_data['error'])
                                reason = reason or ('The AI provider reported an error: ' + detail if detail
                                                    else 'The AI provider reported an error.')
                            for choice in event_data.get('choices', []):
                                accumulated += choice.get('delta', {}).get('content') or choice.get('text') or ''
                                finish_reason = choice.get('finish_reason')
                                if finish_reason == 'length':
                                    failed = True
                                    reason = reason or "The reply was cut off at the model's length limit."
                                elif finish_reason == 'content_filter':
                                    failed = True
                                    reason = reason or "The provider's content filter stopped the reply."
                            if len(accumulated) > coaching.MAX_REPLY_CHARS:
                                raise ValueError('Response exceeded the saved review limit.')
                        except json.JSONDecodeError:
                            failed = True
                            reason = reason or 'The provider sent data the app could not read.'
                    yield f"data: {raw}\n\n"
        if on_finish:
            _record(on_finish, accumulated, 'interrupted', 'The provider stopped sending before the reply was complete.')
            finalized = True
            yield 'data: {"error":{"message":"Response interrupted. Reload the saved conversation before continuing."}}\n\n'
        yield "data: [DONE]\n\n"
    except Exception as exc:
        reason = ('The reply was longer than the saved review limit and was stopped.' if isinstance(exc, ValueError)
                  else 'The reply stopped unexpectedly (connection or storage error).')
        yield 'data: {"error":{"message":"Response or persistence failed. Reload the saved conversation; no automatic resend."}}\n\n'
    finally:
        if on_finish and not finalized:
            try:
                _record(on_finish, accumulated[:coaching.MAX_REPLY_CHARS], 'interrupted', reason)
            except Exception:
                pass  # A pending record remains visible; never claim that it was saved.
        if close:
            close()
