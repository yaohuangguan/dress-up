"""Build the bundled, diverse adult character references with the local GPU."""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workflow import build_workflow

CHARACTERS=[
    ('lin','林 · 自然清透','女性 · 亚洲','East Asian adult woman, age 27, beautiful, long straight dark hair, natural makeup, warm approachable expression'),
    ('chen','辰 · 简约有型','男性 · 亚洲','East Asian adult man, age 29, handsome, short textured black hair, clean shaven, confident warm expression'),
    ('emma','Emma · 法式随性','女性 · 白人','white European adult woman, age 28, beautiful, shoulder-length softly wavy brown hair, light freckles, natural makeup'),
    ('alex','Alex · 都市日常','男性 · 白人','white European adult man, age 30, handsome, short brown hair, subtle stubble, relaxed expression'),
    ('maya','Maya · 自信明朗','女性 · 黑人','Black African adult woman, age 28, beautiful, dark brown skin, natural curly black hair, elegant confident expression'),
    ('noah','Noah · 沉稳利落','男性 · 黑人','Black African adult man, age 30, handsome, dark brown skin, short cropped black hair, clean shaven, relaxed confident expression'),
]

def request(path,data=None):
    body=json.dumps(data).encode() if data is not None else None
    req=urllib.request.Request('http://127.0.0.1:8188'+path,data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=6)
    args=parser.parse_args()
    folder=ROOT/'data/library/characters'
    folder.mkdir(parents=True,exist_ok=True)
    new=[]
    for index,(key,name,category,description) in enumerate(CHARACTERS[:args.limit]):
        dest=folder/(key+'.png')
        seed=93821+index
        prompt=f'Professional fashion model headshot portrait of one {description}. Front view, head and shoulders, looking into camera, wearing a plain white crew neck t-shirt, light warm gray studio background, soft daylight, photorealistic skin texture, natural proportions, premium editorial photography, centered face, no text, no logos.'
        started=time.monotonic()
        if not dest.exists():
            graph=build_workflow([],prompt,seed,512,640)
            graph['13']['inputs']['filename_prefix']='LocalLookStudio/characters/'+key
            try:queued=request('/prompt',{'prompt':graph})
            except urllib.error.HTTPError as exc:
                print(exc.read().decode(),flush=True)
                raise
            prompt_id=queued['prompt_id']
            print(key,'queued',prompt_id,flush=True)
            for _ in range(900):
                history=request('/history/'+prompt_id).get(prompt_id)
                if history:
                    if history['status'].get('status_str')=='error':raise RuntimeError(str(history['status']['messages'])[-6000:])
                    output=history['outputs']['13']['images'][0]
                    from urllib.parse import urlencode
                    with urllib.request.urlopen('http://127.0.0.1:8188/view?'+urlencode(output),timeout=30) as response:dest.write_bytes(response.read())
                    break
                time.sleep(2)
            else:raise TimeoutError('character generation timed out')
            print(key,'generated in',round(time.monotonic()-started,1),'seconds',flush=True)
        new.append({'id':'character-'+key,'code':key.upper(),'kind':'character','name':name,'category':category,'tags':'内置 AI 生成人物 '+category,'prompt':'','path':f'data/library/characters/{key}.png','thumb':f'data/library/characters/{key}.png','source':'本机 FLUX.2 Klein 4B AI 生成','generation':{'seed':seed,'prompt':prompt}})
        file=ROOT/'data/characters.json'
        previous=json.loads(file.read_text(encoding='utf8')) if file.exists() else []
        merged={item['id']:item for item in previous+new}
        file.write_text(json.dumps(list(merged.values()),ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':main()
