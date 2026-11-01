"""Install a pinned, checksum-verified Cloudflare client inside this project."""
import hashlib
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.10.7'
SHA256='2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343'
URL=f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-windows-amd64.exe'

def install():
    dest=ROOT/'runtime/bin/cloudflared.exe'
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()==SHA256:return dest
    dest.parent.mkdir(parents=True,exist_ok=True)
    temporary=dest.with_suffix('.download')
    with urllib.request.urlopen(URL,timeout=60) as response,temporary.open('wb') as output:
        while chunk:=response.read(1024*1024):output.write(chunk)
    if hashlib.sha256(temporary.read_bytes()).hexdigest()!=SHA256:raise RuntimeError('cloudflared SHA-256 verification failed')
    temporary.replace(dest)
    print('cloudflared installed and SHA-256 verified:',VERSION,flush=True)
    return dest

if __name__=='__main__':install()
