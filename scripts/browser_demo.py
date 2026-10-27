"""Real Chromium/UI and HTTP rehearsal using isolated stores and the mock carrier.

Requires the optional `browser` extra and `python -m playwright install chromium`.
No model calls are fabricated: this harness explicitly runs deterministic mode.
"""
import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_healthy(base, process):
    with httpx.Client(trust_env=False) as client:
        for _ in range(300):
            if process.poll() is not None:
                raise RuntimeError('Demo service exited; inspect browser-server.log')
            try:
                if client.get(base+'/health', timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.1)
    raise RuntimeError('Service did not become healthy within 30 seconds')


def rehearse(output):
    from playwright.sync_api import sync_playwright
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path('atlas/static/index.html'),Path('scripts/browser_demo.py')]}, 'mode':'demo', 'live_llm_executed':False, 'checks':{}, 'javascript_errors':[]}
    key = secrets.token_urlsafe(24)
    api_port, carrier_port = free_port(), free_port()
    base = f'http://127.0.0.1:{api_port}'
    processes = []
    with tempfile.TemporaryDirectory(prefix='atlas-browser-') as tmp:
        env = {**os.environ, 'ATLAS_MODE':'demo', 'EMBEDDING_MODEL':'',
               'DATABASE_URL':'sqlite:///'+tmp+'/demo.db', 'CHROMA_PATH':tmp+'/chroma',
               'DATA_DIR':str(Path('data').resolve()), 'ADMIN_API_KEY':key, 'DEMO_ACCESS':'true',
               'CARRIER_BASE_URL':f'http://127.0.0.1:{carrier_port}', 'CARRIER_API_KEY':'',
               'AS_OF_DATE':'2026-10-26', 'NO_PROXY':'127.0.0.1,localhost', 'ALL_PROXY':'',
               'HTTP_PROXY':'', 'HTTPS_PROXY':''}
        with output.with_suffix('.server.log').open('w') as logfile:
            try:
                for module, port in [('atlas.mock_carrier:app',carrier_port), ('atlas.api:app',api_port)]:
                    process = subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host','127.0.0.1',
                        '--port',str(port)], env=env, cwd=tmp, stdout=logfile, stderr=logfile)
                    processes.append(process)
                    wait_healthy(f'http://127.0.0.1:{port}', process)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page(viewport={'width':1440, 'height':1100})
                    page.on('pageerror', lambda error:report['javascript_errors'].append(str(error)))
                    page.goto(base)
                    page.get_by_text('Connected', exact=True).wait_for()
                    page.get_by_role('button',name='Demo A · Refund & approval ↗').click()
                    page.get_by_role('button',name='Confirm refund proposal',exact=True).wait_for()
                    page.wait_for_function("document.querySelector('#trace').textContent.trim().startsWith('{') && JSON.parse(document.querySelector('#trace').textContent).action?.amount_cents === 24900")
                    report['demo_a_trace'] = json.loads(page.locator('#trace').text_content())
                    assert report['demo_a_trace']['action']['amount_cents'] == 24900
                    assert report['demo_a_trace']['action']['requires_human']
                    page.get_by_role('button',name='Confirm refund proposal',exact=True).click()
                    page.get_by_role('button',name='Confirmed · awaiting human review',exact=True).wait_for()
                    page.locator('#opsTab').click()
                    page.locator('#adminKey').fill(key)
                    page.locator('#loadReviews').click()
                    page.get_by_role('button',name='Approve simulation',exact=True).wait_for()
                    page.get_by_placeholder('Decision reason (required)').fill('Verified synthetic receipt and inspection')
                    page.get_by_role('button',name='Approve simulation',exact=True).click()
                    page.get_by_text('No requests awaiting review.',exact=True).wait_for()
                    page.locator('#drain').click()
                    page.get_by_text('1 simulated payment(s) completed. No real money moved.',exact=True).wait_for()
                    # Audit is fetched after draining; wait for the async UI refresh too.
                    page.wait_for_function("document.querySelector('#audit').textContent.includes('completed_simulation')")
                    audit = json.loads(page.locator('#audit').text_content())
                    report['demo_a_audit'] = audit
                    report['checks']['refund_approval_and_audit'] = any(
                        e['event']=='completed_simulation' for e in audit)
                    page.locator('#drain').click()
                    page.get_by_text('0 simulated payment(s) completed. No real money moved.',exact=True).wait_for()
                    report['checks']['duplicate_processing'] = True
                    page.locator('#customerTab').click()
                    page.get_by_role('button',name='Completed · simulated payment',exact=True).wait_for()
                    report['checks']['customer_payment_status_updated'] = True
                    page.get_by_role('button',name='Demo B · Tracking & styling ↗').click()
                    page.wait_for_function("JSON.parse(document.querySelector('#trace').textContent).outfit.length > 0")
                    trace = json.loads(page.locator('#trace').text_content())
                    report['demo_b_trace'] = trace
                    report['checks']['both_tracking_and_outfit'] = (
                        'Shipment status:' in page.locator('#chat').inner_text()
                        and 'Suggested outfit:' in page.locator('#chat').inner_text())
                    report['checks']['worker_overlap'] = bool(trace['execution_summary']['parallel_pairs'])
                    report['checks']['live_mock_carrier'] = any(
                        f['evidence'].get('source')=='live mock carrier API' for f in trace['evidence'])
                    report['checks']['budget_size_stock'] = (
                        sum(p['price_cents'] for p in trace['outfit']) <= 15000
                        and all(p['size']=='M' and p['stock']>0 for p in trace['outfit']))
                    page.screenshot(path=str(output.with_suffix('.desktop.png')), full_page=True)
                    page.set_viewport_size({'width':390,'height':844})
                    report['checks']['mobile_no_horizontal_overflow'] = page.evaluate(
                        'document.documentElement.scrollWidth <= window.innerWidth')
                    page.screenshot(path=str(output.with_suffix('.mobile.png')), full_page=True)
                    browser.close()
            except Exception as exc:
                import traceback
                report['failure'] = type(exc).__name__+': '+str(exc)
                report['failure_traceback'] = traceback.format_exc()
            finally:
                for process in reversed(processes):
                    process.terminate()
                    process.wait(timeout=15)
    report['passed'] = (not report.get('failure') and not report['javascript_errors']
                        and bool(report['checks']) and all(report['checks'].values()))
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if not k.endswith(('_trace','_audit'))}, indent=2))
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',default='reports/browser-demo.json')
    args = parser.parse_args()
    raise SystemExit(0 if rehearse(args.output) else 1)
