"""Real logger with mocked Hevy and disposable DBs; no production access."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/reference-recency'
URL = 'http://127.0.0.1:18139'


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT/'preview.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'uvicorn',
            'tools.preview_app:app', '--host', '127.0.0.1', '--port', '18139'], cwd=ROOT,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError('Preview exited')
                try:
                    urllib.request.urlopen(URL+'/training/health', timeout=1).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Preview unavailable')
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge', headless=True)
                for width in (390, 1280):
                    context = browser.new_context(viewport={'width': width, 'height': 900}, service_workers='block')
                    context.route('https://**/*', lambda r: r.abort())
                    page = context.new_page()
                    page.goto(URL+'/training/log')
                    page.get_by_role('button', name='Start an empty workout', exact=True).click()
                    page.evaluate("""() => {
                      const old=new Date(Date.now()-100*86400000).toISOString();
                      draft.exercises=[{id:'bench',template_id:'sq',title:'Low pin bench',
                        ref:{...defaultRef(),weightUnit:'lb',state:{found:true,e1rm_lb:240,workout_start_time:old},
                          ts:{found:true,e1rm_lb:275,set_at:old}},
                        sets:[{type:'normal',kg:'113.4',reps:'2',rpe:'8',done:false,manual:false}]}];
                      applyAuto(draft.exercises[0]);renderWorkout();saveDraft();
                    }""")
                    assert page.evaluate('draft.exercises[0].sets[0].kg') == ''
                    button = page.get_by_role('button', name='Use pinned TS for this workout', exact=True)
                    expect(button).to_be_visible()
                    page.screenshot(path=str(OUT/f'stale-{width}.png'), full_page=True)
                    button.click()
                    expect(button).to_have_count(0)
                    assert abs(page.evaluate('Number(draft.exercises[0].sets[0].kg)*LB_PER_KG')-250) < .01
                    saved_ts = page.evaluate('draft.exercises[0].ref.ts')
                    context.route('**/training/training-max/sq', lambda r: r.fulfill(json=saved_ts))
                    context.route('**/training/hevy/exercise-state/sq', lambda r: r.fulfill(json={'found': False, 'previous': []}))
                    page.reload()
                    expect(page.locator('.reference-notice')).to_contain_text('Pinned TS')
                    expect(button).to_have_count(0)
                    assert abs(page.evaluate('Number(draft.exercises[0].sets[0].kg)*LB_PER_KG')-250) < .01
                    page.evaluate("draft.exercises[0].ref.ts.e1rm_lb=280;applyAuto(draft.exercises[0]);renderWorkout()")
                    expect(button).to_be_visible()
                    assert page.evaluate('draft.exercises[0].sets[0].kg') == ''
                    page.evaluate("draft.exercises[0].ref.ts={found:false};applyAuto(draft.exercises[0]);renderWorkout()")
                    expect(page.locator('.reference-notice')).to_contain_text('Enter a starting weight')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    context.close()
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=15)
    print('Phone/desktop stale TS, explicit confirmation, changed TS and manual-start notice passed.')


if __name__ == '__main__':
    run()
