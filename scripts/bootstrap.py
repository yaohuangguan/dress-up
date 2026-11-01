"""Recreate this verified Windows installation without global package changes."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
COMFY_REV='7c4390a6f70cd8eb41014d6af52969397a752fc4'
SOURCES=[
    ('https://github.com/Comfy-Org/ComfyUI.git',ROOT/'runtime/ComfyUI',COMFY_REV),
    ('https://github.com/wquguru/shisei.git',ROOT/'work/libraries/shisei','3f60df337c1569d04df2a2309615a1cf96d56501'),
    ('https://github.com/paipiange/nvzhuang.git',ROOT/'work/libraries/nvzhuang','f13741ebc09c73a63b92f626a115a1bb74ed779f'),
]

def run(*arguments):
    print('Running:',str(arguments[0]),' '.join(map(str,arguments[1:])),flush=True)
    subprocess.run(list(map(str,arguments)),cwd=ROOT,check=True)

def main():
    parser=argparse.ArgumentParser(description='Install the local image studio; video weights are opt-in.')
    parser.add_argument('--with-video',action='store_true',help='Also install local video, writer and voice models (~12.3 GB extra)')
    args=parser.parse_args()
    temporary=ROOT/'work/tmp'
    temporary.mkdir(parents=True,exist_ok=True)
    for key in ['TEMP','TMP','TMPDIR']:os.environ[key]=str(temporary)
    os.environ['PIP_CACHE_DIR']=str(ROOT/'work/cache/pip')
    if sys.version_info[:2]!=(3,11):raise SystemExit('Use Python 3.11 (64-bit) for the verified Windows setup.')
    python=ROOT/'.venv/Scripts/python.exe'
    if not python.exists():run(sys.executable,'-m','venv',ROOT/'.venv')
    run(python,'-m','pip','install','--no-cache-dir','-r','requirements-lock.txt','--extra-index-url','https://download.pytorch.org/whl/cu128')
    for url,directory,revision in SOURCES:
        if not directory.exists():
            directory.parent.mkdir(parents=True,exist_ok=True)
            run('git','clone','--filter=blob:none','--no-checkout',url,directory)
            run('git','-C',directory,'checkout','--detach',revision)
        else:
            current=subprocess.check_output(['git','-C',str(directory),'rev-parse','HEAD'],text=True).strip()
            if current!=revision:raise SystemExit(f'{directory}: existing checkout differs from verified version; left unchanged.')
    run(python,'scripts/import_libraries.py')
    run(python,'scripts/import_portraits.py')
    run(python,'scripts/download_models.py')
    if args.with_video:
        run(python,'scripts/download_video_models.py')
        run(python,'scripts/download_creative_models.py')
    run(python,'scripts/make_icons.py')
    run('powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'scripts/Install-Shortcuts.ps1')
    print('Installed. Double-click Start-Studio.cmd to open the studio.',flush=True)

if __name__=='__main__':main()
