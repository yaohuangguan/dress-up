"""Install the pinned, checksum-verified LTX-Video preview engine."""
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

from download_models import ROOT

MODELS = [
    ('Lightricks/LTX-Video', '8984fa25007f376c1a299016d0957a37a2f797bb', 'ltxv-2b-0.9.8-distilled-fp8.safetensors', 'checkpoints', 4461695684, 'd6d8fa8ed3a98346787c2503ac80fb5d7cebcf80e356b79a2ba361fbadf97e15'),
    ('comfyanonymous/flux_text_encoders', '6af2a98e3f615bdfa612fbd85da93d1ed5f69ef5', 't5xxl_fp8_e4m3fn.safetensors', 'text_encoders', 4893934904, '7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09'),
]

def main():
    records=[]
    for repo,revision,name,folder,size,digest in MODELS:
        dest=ROOT/'runtime/ComfyUI/models'/folder/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        part=dest.with_suffix('.partial')
        if not dest.exists():
            start=part.stat().st_size if part.exists() else 0
            if shutil.disk_usage(ROOT).free<size-start+5_000_000_000:
                raise SystemExit('Insufficient disk space: leave at least 5 GB free.')
            request=urllib.request.Request(f'https://huggingface.co/{repo}/resolve/{revision}/{name}',headers={'Range':f'bytes={start}-'} if start else {})
            with urllib.request.urlopen(request,timeout=120) as response:
                if response.status!=206:start=0
                print(f'{name}: downloading, resume {start/1e9:.2f} GB',flush=True)
                with part.open('ab' if start else 'wb') as out:shutil.copyfileobj(response,out,8*1024*1024)
            candidate=part
        else:candidate=dest
        with candidate.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if candidate.stat().st_size!=size or actual!=digest:raise SystemExit(f'{name}: checksum mismatch; file left for inspection')
        if candidate!=dest:part.replace(dest)
        records.append({'file':str(dest.relative_to(ROOT)),'size':size,'sha256':digest,'repo':repo,'revision':revision})
        print(f'{name}: SHA-256 verified',flush=True)
    (ROOT/'data/video-model-manifest.json').write_text(json.dumps(records,indent=2),encoding='utf8')

if __name__=='__main__':main()
