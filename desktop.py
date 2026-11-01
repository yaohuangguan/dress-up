"""Open the local studio as a desktop window, without a terminal window."""
import ctypes
import json
import os
import subprocess
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    try:
        (ROOT/'logs').mkdir(exist_ok=True)
        with (ROOT/'logs/desktop-launch.log').open('a',encoding='utf8') as output:
            result=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'launch.py'),'--no-browser'],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,timeout=150,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode:raise RuntimeError('启动失败。请查看项目 logs/desktop-launch.log。')
        remote_state=ROOT/'data/remote/state.json'
        if remote_state.exists() and json.loads(remote_state.read_text(encoding='utf8')).get('enabled'):
            output=(ROOT/'logs/desktop-remote.log').open('a',encoding='utf8')
            subprocess.Popen([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'remote_access.py'),'--quiet'],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            output.close()
        edge=next((path for path in [Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft/Edge/Application/msedge.exe'] if path.is_file()),None)
        if edge:
            subprocess.Popen([str(edge),'--app=http://127.0.0.1:7800/','--new-window'],creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        else:webbrowser.open('http://127.0.0.1:7800/')
    except Exception as error:
        if os.name=='nt':ctypes.windll.user32.MessageBoxW(0,str(error),'衣见 · 启动提示',0x10)
        else:raise

if __name__=='__main__':main()
