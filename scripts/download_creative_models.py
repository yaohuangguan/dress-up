"""Pinned local scriptwriter and neural Mandarin narrator; no account/API key."""
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HF='https://huggingface.co/'
KOKORO=HF+'hexgrad/Kokoro-82M-v1.1-zh/resolve/01e7505bd6a7a2ac4975463114c3a7650a9f7218/'
FILES=[
    (HF+'Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf','runtime/writer/Qwen3-4B-Q4_K_M.gguf','7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'),
    ('https://github.com/ggml-org/llama.cpp/releases/download/b12024/llama-b12024-bin-win-cpu-x64.zip','runtime/writer/llama-b12024.zip','a8a1bc0167c594c377255e54aab617b288a38e09efb50f39ac5bd087e4398f72'),
    (KOKORO+'kokoro-v1_1-zh.pth','runtime/voice/kokoro-v1_1-zh.pth','b1d8410fa44dfb5c15471fd6c4225ea6b4e9ac7fa03c98e8bea47a9928476e2b'),
    (KOKORO+'voices/zf_094.pt','runtime/voice/zf_094.pt','c8ca9d1762d7f2f8c94717e3e4db803eccf695f96621ef7063ac8e92b81e30c1'),
    (KOKORO+'config.json','runtime/voice/config.json',None),
]

def main():
    records=[]
    for url,relative,expected in FILES:
        dest=ROOT/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            part=dest.with_suffix('.partial');start=part.stat().st_size if part.exists() else 0
            request=urllib.request.Request(url,headers={'Range':f'bytes={start}-'} if start else {})
            print('Downloading '+dest.name,flush=True)
            with urllib.request.urlopen(request,timeout=120) as response:
                if response.status!=206:start=0
                with part.open('ab' if start else 'wb') as stream:
                    while chunk:=response.read(8*1024*1024):stream.write(chunk)
            candidate=part
        else:candidate=dest
        with candidate.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if expected and digest!=expected:raise RuntimeError(dest.name+': SHA-256 mismatch')
        if candidate!=dest:part.replace(dest)
        records.append({'file':relative,'source':url,'sha256':digest})
        print(dest.name+': verified',flush=True)
    folder=ROOT/'runtime/writer/bin'
    with zipfile.ZipFile(ROOT/'runtime/writer/llama-b12024.zip') as archive:
        for entry in archive.infolist():
            if not (folder/entry.filename).resolve().is_relative_to(folder.resolve()):raise RuntimeError('Unsafe archive path')
        archive.extractall(folder)
    (ROOT/'data/creative-model-manifest.json').write_text(json.dumps(records,indent=2),encoding='utf8')

if __name__=='__main__':main()
