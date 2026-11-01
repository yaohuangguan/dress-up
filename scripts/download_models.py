"""Download official model files, resume interrupted transfers, verify SHA-256."""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    ('black-forest-labs/FLUX.2-klein-base-4b-fp8', 'flux-2-klein-base-4b-fp8.safetensors', 'diffusion_models'),
    ('black-forest-labs/FLUX.2-klein-4b-fp8', 'flux-2-klein-4b-fp8.safetensors', 'diffusion_models'),
    ('Comfy-Org/Flux-2-Klein-4B', 'split_files/text_encoders/qwen_3_4b.safetensors', 'text_encoders'),
    ('Comfy-Org/Flux-2-Klein-4B', 'split_files/vae/flux2-vae.safetensors', 'vae'),
]

def read_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)

def download(repo, source, folder):
    meta = read_json(f'https://huggingface.co/api/models/{repo}?blobs=true')
    entry = next(x for x in meta['siblings'] if x['rfilename'] == source)
    size = entry.get('size') or entry['lfs']['size']
    expected = entry.get('lfs', {}).get('sha256')
    revision = meta['sha']
    dest = ROOT / 'runtime/ComfyUI/models' / folder / Path(source).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == size:
        print(f'{dest.name}: already installed', flush=True)
        return {'file':str(dest.relative_to(ROOT)), 'size':size, 'sha256':expected, 'revision':revision, 'repo':repo}
    part = dest.with_suffix('.partial')
    for attempt in range(4):
        try:
            start = part.stat().st_size if part.exists() else 0
            headers = {'Range': f'bytes={start}-'} if start else {}
            request = urllib.request.Request(f'https://huggingface.co/{repo}/resolve/{revision}/{source}?download=true&attempt={attempt}', headers=headers)
            with urllib.request.urlopen(request, timeout=90) as response:
                if start and response.status != 206:
                    start = 0
                mode = 'ab' if start else 'wb'
                done = start
                last = time.monotonic()
                print(f'{dest.name}: downloading {size/1e9:.2f} GB, resume {start/1e9:.2f} GB', flush=True)
                with part.open(mode) as out:
                    while chunk := response.read(8*1024*1024):
                        out.write(chunk)
                        done += len(chunk)
                        if time.monotonic()-last > 15:
                            print(f'{dest.name}: {100*done/size:.1f}% ({done/1e9:.2f} GB)', flush=True)
                            last = time.monotonic()
            if part.stat().st_size != size:
                raise ValueError('incomplete transfer')
            digest = hashlib.file_digest(part.open('rb'),'sha256').hexdigest()
            if expected and digest != expected:
                raise ValueError('SHA-256 mismatch; remove the .partial file and retry')
            part.replace(dest)
            print(f'{dest.name}: SHA-256 verified', flush=True)
            return {'file':str(dest.relative_to(ROOT)), 'size':size, 'sha256':digest, 'revision':revision, 'repo':repo}
        except Exception as exc:
            print(f'{dest.name}: attempt {attempt+1}: {exc}', flush=True)
            if attempt == 3:
                raise
            time.sleep(2)

if __name__ == '__main__':
    records = [download(*model) for model in MODELS]
    (ROOT/'data').mkdir(exist_ok=True)
    (ROOT/'data/model-manifest.json').write_text(json.dumps(records,indent=2),encoding='utf8')
