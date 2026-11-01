"""Start the authenticated temporary remote entry and save its login locally."""
import argparse
import base64
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psutil

from launch import ROOT,LOGS,available
from scripts.download_cloudflared import install

PRIVATE=ROOT/'data/remote'
STATE=PRIVATE/'state.json'

def read(file,default):return json.loads(file.read_text(encoding='utf8')) if file.exists() else default
def write(file,data):
    file.parent.mkdir(parents=True,exist_ok=True)
    temporary=file.with_suffix('.tmp');temporary.write_text(json.dumps(data,indent=2),encoding='utf8');temporary.replace(file)

def managed(pid,name):
    if not isinstance(pid,int) or pid<=0:return None
    try:
        process=psutil.Process(pid)
        args=process.cmdline()
        if name=='gateway':return process if str(ROOT/'remote_gateway.py').casefold() in ' '.join(args).casefold() else None
        return process if Path(process.exe()).resolve()==(ROOT/'runtime/bin/cloudflared.exe').resolve() and 'http://127.0.0.1:7802' in args else None
    except (psutil.Error,OSError,TypeError):return None

def probe(url,credentials=None):
    request=urllib.request.Request(url)
    if credentials:
        value=base64.b64encode((credentials['username']+':'+credentials['password']).encode()).decode()
        request.add_header('Authorization','Basic '+value)
    try:
        with urllib.request.urlopen(request,timeout=10) as response:return response.status
    except urllib.error.HTTPError as exc:return exc.code
    except (OSError,TimeoutError):return 0

def stop(state):
    for name in ['tunnel','gateway']:
        process=managed(state.get(name),name)
        if process:
            for child in process.children(recursive=True):
                try:
                    if str(ROOT).casefold() in ' '.join(child.cmdline()).casefold():child.terminate()
                except psutil.Error:pass
            process.terminate()
            try:process.wait(5)
            except psutil.TimeoutExpired:process.kill()
    write(STATE,{'enabled':False})

def start(quiet=False):
    PRIVATE.mkdir(parents=True,exist_ok=True);LOGS.mkdir(exist_ok=True)
    state=read(STATE,{})
    file=PRIVATE/'credentials.json'
    credentials=read(file,{})
    if not credentials:
        credentials={'username':'owner','password':secrets.token_urlsafe(18)}
        write(file,credentials)
    with (LOGS/'remote-launch.log').open('a',encoding='utf8') as output:
        subprocess.run([sys.executable,str(ROOT/'launch.py'),'--no-browser'],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True,timeout=150,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if not managed(state.get('gateway'),'gateway'):
        if not available(7802):raise RuntimeError('Port 7802 belongs to another process; left unchanged.')
        output=(LOGS/'remote-gateway.log').open('a',encoding='utf8')
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
        process=subprocess.Popen([sys.executable,'-u',str(ROOT/'remote_gateway.py')],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        output.close();state['gateway']=process.pid;write(STATE,state)
    for _ in range(30):
        if probe('http://127.0.0.1:7802/')==401 and probe('http://127.0.0.1:7802/api/catalog?kind=character',credentials)==200:break
        time.sleep(.5)
    else:raise RuntimeError('Authenticated local gateway did not become ready; no tunnel started.')
    if not managed(state.get('tunnel'),'tunnel'):
        client=install();logfile=LOGS/'cloudflared.log'
        output=logfile.open('w',encoding='utf8')
        process=subprocess.Popen([str(client),'tunnel','--no-autoupdate','--url','http://127.0.0.1:7802','--protocol','http2'],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        output.close();state.update(tunnel=process.pid,enabled=True,url='');write(STATE,state)
        for _ in range(120):
            if process.poll() is not None:raise RuntimeError('Cloudflare tunnel exited. See logs/cloudflared.log.')
            content=logfile.read_text(encoding='utf8',errors='replace')
            match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',content)
            if match:
                state['url']=match.group(0);write(STATE,state)
                if 'Registered tunnel connection' in content:break
            time.sleep(.5)
        else:raise RuntimeError('Tunnel registration is not ready; inspect logs/cloudflared.log before retrying.')
    for _ in range(30):
        authenticated=probe(state['url']+'/api/catalog?kind=character',credentials)
        if authenticated==200 and probe(state['url'])==401:break
        time.sleep(1)
    else:raise RuntimeError(f'Tunnel created but external HTTPS verification has not passed (authenticated HTTP {authenticated}).')
    state['enabled']=True;write(STATE,state)
    instructions=(
        '衣见 · 私人远程访问\n\n地址：'+state['url']+'\n账号：'+credentials['username']+'\n密码：'+credentials['password']+
        '\n\n此文件含私人登录信息，请勿分享或上传仓库。\n计算仍在本机完成，电脑需要开机并联网。\n临时链接在隧道重建后可能变化，重新启动远程入口后以本文件为准。\n'
    )
    (ROOT/'远程访问.txt').write_text(instructions,encoding='utf8')
    if not quiet:print('REMOTE_URL='+state['url'],flush=True);print('Login details saved locally to 远程访问.txt (not logged or committed).',flush=True)
    return state['url']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stop',action='store_true');parser.add_argument('--quiet',action='store_true');args=parser.parse_args()
    if args.stop:stop(read(STATE,{}))
    else:start(args.quiet)
