"""Start/stop only this project's background processes on Windows."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

import psutil

ROOT=Path(__file__).resolve().parent
LOGS=ROOT/'logs'
STATE=LOGS/'processes.json'

def owned(pid):
    try:
        process=psutil.Process(pid)
        return process if Path(process.exe()).resolve()==Path(sys.executable).resolve() and str(ROOT).casefold() in ' '.join(process.cmdline()).casefold() else None
    except (psutil.Error,OSError):return None

def available(port):
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1',port))!=0

def healthy(url):
    try:
        with urllib.request.urlopen(url,timeout=2) as response:return response.status==200
    except Exception:return False

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stop',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    LOGS.mkdir(exist_ok=True)
    state=json.loads(STATE.read_text()) if STATE.exists() else {}
    if args.stop:
        for name,pid in state.items():
            process=owned(pid)
            if process:
                children=[]
                for child in process.children(recursive=True):
                    try:
                        if str(ROOT).casefold() in ' '.join(child.cmdline()).casefold():children.append(child)
                    except psutil.Error:pass
                for child in reversed(children):
                    with __import__('contextlib').suppress(psutil.Error):child.terminate()
                process.terminate()
                try:process.wait(8)
                except psutil.TimeoutExpired:process.kill()
                print(f'{name} stopped')
        STATE.write_text('{}')
        return
    services={
        'comfy':(8188,[str(ROOT/'runtime/ComfyUI/main.py'),'--listen','127.0.0.1','--port','8188','--lowvram','--disable-dynamic-vram','--fp16-unet','--fp32-vae','--reserve-vram','1','--disable-all-custom-nodes','--disable-api-nodes','--disable-auto-launch']),
        'studio':(7800,[str(ROOT/'app.py')]),
    }
    for name,(port,arguments) in services.items():
        if state.get(name) and owned(state[name]):
            print(f'{name}: already running (PID {state[name]})')
            continue
        if not available(port):raise SystemExit(f'Port {port} is occupied by another application. Stop that application or inspect it first.')
        output=(LOGS/(name+'.log')).open('a',encoding='utf8')
        environment=os.environ.copy()
        environment['PYTHONIOENCODING']='utf-8'
        process=subprocess.Popen([sys.executable,'-u',*arguments],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,env=environment,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        output.close()
        state[name]=process.pid
        STATE.write_text(json.dumps(state))
        print(f'{name}: starting (PID {process.pid})')
    for _ in range(30):
        if healthy('http://127.0.0.1:7800/api/status'):break
        time.sleep(1)
    else:raise SystemExit('Studio did not become ready. See logs/studio.log.')
    print('Local Look Studio: http://127.0.0.1:7800')
    print('ComfyUI: http://127.0.0.1:8188 (first startup may take a minute)')
    if not args.no_browser:webbrowser.open('http://127.0.0.1:7800')

if __name__=='__main__':main()
