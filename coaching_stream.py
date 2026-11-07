"""Relay a model's streamed reply to the browser while recording how it ended.

Pure of HTTP and web-framework concerns: it consumes text chunks and yields the
server-sent events the browser already expects. The provider connection stays with
the caller, so tests can feed plain chunks instead of mocking a network client.
"""
import json

import coaching


def relay(chunks, on_finish=None, close=None):
    """Yield server-sent events for `chunks`, calling `on_finish(content, status)` once.

    `status` is 'complete', 'failed' or 'interrupted'. With no `on_finish` (plain chat)
    events are forwarded untouched and nothing is tracked. `close` always runs last.
    A reply that never finalizes is recorded as interrupted and never resent.
    """
    accumulated = ''
    finalized = False
    failed = False
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
                            on_finish(accumulated, 'complete' if accumulated.strip() and not failed else 'failed')
                            finalized = True
                        yield "data: [DONE]\n\n"
                        return
                    if on_finish:
                        try:
                            event_data = json.loads(raw)
                            if event_data.get('error'): failed = True
                            for choice in event_data.get('choices', []):
                                accumulated += choice.get('delta', {}).get('content') or choice.get('text') or ''
                                if choice.get('finish_reason') in ('length', 'content_filter'): failed = True
                            if len(accumulated) > coaching.MAX_REPLY_CHARS:
                                raise ValueError('Response exceeded the saved review limit.')
                        except json.JSONDecodeError:
                            failed = True
                    yield f"data: {raw}\n\n"
        if on_finish:
            on_finish(accumulated, 'interrupted')
            finalized = True
            yield 'data: {"error":{"message":"Response interrupted. Reload the saved conversation before continuing."}}\n\n'
        yield "data: [DONE]\n\n"
    except Exception:
        yield 'data: {"error":{"message":"Response or persistence failed. Reload the saved conversation; no automatic resend."}}\n\n'
    finally:
        if on_finish and not finalized:
            try:
                on_finish(accumulated[:coaching.MAX_REPLY_CHARS], 'interrupted')
            except Exception:
                pass  # A pending record remains visible; never claim that it was saved.
        if close:
            close()
