"""Generate the bundled location references on the local ComfyUI GPU."""
import json
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workflow import build_workflow

SCENES=[
 ('studio','极简影棚','室内','a minimalist professional fashion photography studio, warm white seamless curved backdrop, light gray floor, soft diffuse studio lighting, empty central foreground'),
 ('cafe','街角咖啡馆','室内','an elegant Parisian sidewalk cafe, warm wooden cafe facade, large windows, small bistro tables on the side, open central pavement for a fashion portrait, soft morning light'),
 ('city','都市街头','户外','a contemporary city street with modern limestone buildings and shop windows, quiet empty sidewalk, open foreground for a full body fashion photo, soft overcast daylight'),
 ('beach','落日海岸','户外','a beautiful quiet sandy beach, calm ocean, golden sunset light, distant coastline, open empty foreground sand for a full body fashion portrait, subtle warm pink sky'),
 ('park','林荫公园','户外','a serene public park with a wide stone path, leafy trees framing both sides, soft late afternoon sunlight, open empty central foreground for a full body portrait'),
 ('loft','暖调室内','室内','a refined contemporary loft apartment, large sunlit window, neutral plaster walls, warm oak floor, minimal sofa at the side, wide empty foreground, soft diffused natural light'),
]

def request(path,data=None):
    body=json.dumps(data).encode() if data is not None else None
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8188'+path,data=body,headers={'Content-Type':'application/json'}),timeout=30) as response:return json.load(response)

def main():
    folder=ROOT/'data/library/backgrounds';folder.mkdir(exist_ok=True,parents=True)
    records=[]
    for index,(key,name,category,description) in enumerate(SCENES):
        dest=folder/(key+'.png')
        if not dest.exists():
            prompt=f'High quality realistic architectural location photograph of {description}. No people, no human figures, no text, no watermarks. Natural perspective, coherent lighting, editorial fashion location scouting photograph.'
            graph=build_workflow([],prompt,928100+index,768,512)
            graph['13']['inputs']['filename_prefix']='LocalLookStudio/backgrounds/'+key
            queued=request('/prompt',{'prompt':graph});pid=queued['prompt_id']
            print(name,'queued',flush=True)
            for _ in range(900):
                history=request('/history/'+pid).get(pid)
                if history:
                    if history['status'].get('status_str')=='error':raise RuntimeError(str(history['status']['messages'])[-4000:])
                    output=history['outputs']['13']['images'][0]
                    with urllib.request.urlopen('http://127.0.0.1:8188/view?'+urlencode(output),timeout=30) as response:dest.write_bytes(response.read())
                    print(name,'generated',flush=True);break
                time.sleep(2)
            else:raise TimeoutError(name)
        records.append({'id':'background-'+key,'code':key.upper(),'kind':'background','name':name,'category':category,'tags':name+' '+description,'prompt':description,'path':f'data/library/backgrounds/{key}.png','thumb':f'data/library/backgrounds/{key}.png','source':'本机 FLUX.2 Klein 4B AI 生成'})
        (ROOT/'data/backgrounds.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':main()
