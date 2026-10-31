"""Normalize the downloaded public libraries for fully local browsing."""
import json
import argparse
import re
import shutil
import subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

def save(name, data):
    (ROOT/'data'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-root',type=Path,default=ROOT/'work/libraries')
    args=parser.parse_args()
    source_root=args.source_root
    (ROOT/'data').mkdir(exist_ok=True)
    (ROOT/'licenses').mkdir(exist_ok=True)
    pose = source_root/'shisei'
    costume = source_root/'nvzhuang'
    dest = ROOT/'data/library'
    dest.mkdir(exist_ok=True)
    shutil.copytree(pose/'images/line',dest/'poses',dirs_exist_ok=True)
    shutil.copytree(costume/'assets/img',dest/'outfits',dirs_exist_ok=True)
    shutil.copytree(costume/'assets/thumbs',dest/'outfit-thumbs',dirs_exist_ok=True)
    for src,name in [(pose/'LICENSE-images','shisei-CC0.txt'),(pose/'NOTICE','shisei-NOTICE.txt'),(costume/'LICENSE','costume-code-MIT.txt'),(costume/'docs/LICENSE-DECISION.md','costume-source-license.md')]:
        shutil.copyfile(src,ROOT/'licenses'/name)
    catalog = []
    poses = json.loads((pose/'data/catalog.json').read_text(encoding='utf8'))
    total_views=0
    for p in poses:
        views={angle:f'data/library/poses/w900/{file}' for angle,file in p['views'].items() if file and (dest/'poses/w900'/file).is_file()}
        if not views: continue
        thumb_views={angle:f'data/library/poses/w300/{Path(file).name}' for angle,file in views.items()}
        total_views+=len(views)
        catalog.append({'id':'pose-'+p['series']+'-'+p['id'],'code':p['id'],'kind':'pose','name':p['name_cn'],'category':p['class_cn'],'series':p['series'],'tags':p['name_en'],'prompt':p.get('desc_en',p['name_en']),'views':views,'thumb_views':thumb_views,'path':next(iter(views.values())),'thumb':next(iter(thumb_views.values())),'source':'Shisei · CC0'})
    text=(costume/'data.js').read_text(encoding='utf8')
    clothes=json.loads(re.search(r'const D=(\[.*?\]);',text,re.S).group(1))
    categories={'春':'春装','夏':'夏装','秋':'秋装','冬':'冬装','ランジェリー':'内衣','パーティ':'礼服','水着':'泳装','セクシー':'时尚搭配'}
    words={'dress':'连衣裙','skirt':'裙装','pants':'长裤','denim':'牛仔','knit':'针织','cardigan':'开衫','coat':'外套','shirt':'衬衫','jacket':'夹克','white':'白色','black':'黑色','pink':'粉色','blue':'蓝色','beige':'米色','green':'绿色','yellow':'黄色','red':'红色','floral':'碎花','ribbon':'蝴蝶结','boots':'靴子','sneakers':'运动鞋','lace':'蕾丝','satin':'缎面','shorts':'短裤','swimsuit':'泳衣','bikini':'比基尼','ivory':'象牙白','navy':'藏蓝'}
    for c in clothes:
        file=dest/'outfits'/(c['id']+'.webp')
        if not file.is_file(): continue
        tags=c['キーワード']
        translated=' · '.join(v for k,v in words.items() if k in tags.split())
        catalog.append({'id':'outfit-'+c['id'],'code':c['id'],'kind':'outfit','name':translated[:48] or c['id'],'category':categories[c['カテゴリ']],'tags':tags+' '+translated,'prompt':tags,'path':f'data/library/outfits/{file.name}','thumb':f'data/library/outfit-thumbs/{file.name}','source':'COSTUME-DB-01 · ギア / paipiange'})
    # The Shisei sample photos are AI generated and released under CC0.
    portraits=dest/'characters'
    portraits.mkdir(exist_ok=True)
    for i,p in enumerate([p for p in poses if p['series']=='std' and p.get('photos',{}).get('front')][:3]):
        candidates=list((pose/'images/photo').rglob(p['photos']['front']))
        if not candidates: continue
        source=max(candidates,key=lambda x:x.stat().st_size)
        with Image.open(source) as im:
            im=im.convert('RGB')
            # Keep the full reference rather than guess where its face is.
            im.thumbnail((768,1024))
            im.save(portraits/f'sample-{i+1}.webp',quality=92)
        catalog.append({'id':f'character-sample-{i+1}','code':f'DEMO-{i+1:02}','kind':'character','name':f'示例人物 {i+1:02}','category':'示例人物','tags':'AI 生成 CC0 示例','prompt':'','path':f'data/library/characters/sample-{i+1}.webp','thumb':f'data/library/characters/sample-{i+1}.webp','source':'Shisei AI sample photo · CC0'})
    save('catalog.json',catalog)
    sources={'pose':{'repo':'https://github.com/wquguru/shisei','revision':subprocess.check_output(['git','-C',str(pose),'rev-parse','HEAD'],text=True).strip(),'poses':sum(x['kind']=='pose' for x in catalog),'images':total_views,'license':'CC0-1.0 (images/data)'},'outfit':{'repo':'https://github.com/paipiange/nvzhuang','revision':subprocess.check_output(['git','-C',str(costume),'rev-parse','HEAD'],text=True).strip(),'outfits':sum(x['kind']=='outfit' for x in catalog),'original':'https://ai-costume-gallery.pages.dev/','license':'Repository code MIT; source image terms retained separately. Local reference use; do not assume redistribution rights.'}}
    save('library-manifest.json',sources)
    print(json.dumps(sources,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
