"""Import CC0 AI portraits and deduplicated hairstyle descriptions for local use.

Only 400px previews are downloaded; no original 4.86GB image archive is needed.
Source images remain outside git and are not redistributed with this project.
"""
import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
REVISION='5a6202c65ca9a44bb283d9a45a562aef88d17527'
SOURCE='https://ai-portrait-gallery.pages.dev/'
PREVIEWS=f'https://raw.githubusercontent.com/HRuiCcc/RuiC-PoseAtlas/{REVISION}/portrait/thumbs/'
LENGTHS={'short':'短发','medium':'中发','semilong':'中长发','long':'长发'}
# Ordered by first appearance of the source's 50 named styles.
STYLES=[
('后颈层次空气短发','short layered hair with a longer nape and wispy see-through bangs'),
('湿发长刘海波波头','wet-look short bob with long bangs'),
('迷你狼尾','short mini wolf cut'),
('黑发螺旋卷波波头','black short bob with spiral perm curls'),
('奶茶色短波波头','light milk-tea blonde short bob'),
('挑染圆润短发','rounded short haircut with subtle highlights'),
('长刘海蘑菇短发','rounded mushroom short haircut with long bangs'),
('自然卷迷你波波头','mini bob with loose naturally curly texture'),
('眉上齐刘海波波头','mini bob with blunt bangs above the eyebrows'),
('脸周层次短波波头','short bob with face-framing layers'),
('深棕空气刘海波波头','rounded dark brown short bob with wispy bangs'),
('薰衣草灰内扣波波头','lavender ash bob with inward-curved ends'),
('无刘海齐切直波波头','blunt straight bob without bangs'),
('黑发前长后短波波头','black angled bob, longer at the front'),
('深色外翘波波头','dark bob with flipped-out ends'),
('耳后利落短发','short androgynous haircut tucked behind the ears, without bangs'),
('韩式侧刘海波波头','Korean tassel bob with side bangs'),
('双向刘海中发内扣','medium bob with two-way curtain bangs and softly inward-curved ends'),
('内层染收腰波波头','waisted bob with peekaboo inner hair color'),
('中发紧密卷','medium-length hair with tight defined perm curls'),
('齐刘海中直发','medium-length straight hair with blunt bangs'),
('奶茶灰中发','light milk-tea greige medium-length hair'),
('韩式层次碎剪','Korean hush cut with soft feathered layers'),
('榛果色蝴蝶剪','hazelnut brown butterfly haircut'),
('酒红空气层次发','burgundy layered hair with wispy bangs'),
('中发狼尾卷','medium-length wolf cut with a perm'),
('中发松散自然卷','medium-length hair with soft natural curling-iron waves'),
('米色层次内扣中发','soft beige medium-length layers with inward-curved ends'),
('薄荷米色长波波头','mint beige layered long bob'),
('齐切外翘中波波头','blunt medium bob with flipped-out ends'),
('栗色前长后短中发','chestnut beige angled medium-length bob'),
('无刘海顺直中发','silky straight medium-length bob without bangs'),
('渐变挑染厚层次中发','full medium-length layers with balayage highlights'),
('灰米色锁骨层次发','ash greige layered bob reaching the collarbones'),
('双向刘海韩式层次','Korean layered hair with two-way curtain bangs'),
('轻盈收腰中长发','waisted semi-long haircut with translucent natural hair color'),
('薰衣草灰丰厚层次','semi-long hair with abundant layers in lavender greige'),
('空气齐刘海碎层次','shaggy layers with wispy blunt bangs'),
('韩式螺旋卷中长发','Korean semi-long hairstyle with spiral curls'),
('樱桃红中长狼尾','cherry red semi-long wolf cut'),
('深色刘海中长直发','dark semi-long straight hair with bangs'),
('中长发轻柔自然卷','semi-long hair with loose natural waves'),
('奶茶米色脸周层次','milk-tea beige semi-long hair with face-framing layers'),
('黑色中长层次发','black semi-long hair with soft glossy layers'),
('金色高层次发尾染','highly layered blonde hair with dip-dyed ends'),
('灰米色层次碎剪','greige hush cut with feathered layers'),
('薄荷米色空气蝴蝶剪','mint beige butterfly haircut with wispy bangs'),
('长发水母狼尾','long wolf cut with jellyfish-style disconnected layers'),
('巧克力棕单卷层次','chocolate brown layered hair with curled ends and loose face-framing strands'),
('斜刘海轻盈卷发','long airy curls with side-swept bangs'),
]


def read_url(url,limit):
    with urllib.request.urlopen(url,timeout=30) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Source response exceeds size limit')
    return data


def prepare_cache():
    cache=ROOT/'work/libraries/portrait-atlas'
    if not cache.exists():
        cache.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['git','clone','--filter=blob:none','--no-checkout','--depth=1','https://github.com/HRuiCcc/RuiC-PoseAtlas.git',str(cache)],check=True)
        subprocess.run(['git','-C',str(cache),'sparse-checkout','init','--cone'],check=True)
        subprocess.run(['git','-C',str(cache),'sparse-checkout','set','portrait/thumbs'],check=True)
        subprocess.run(['git','-C',str(cache),'fetch','--depth=1','origin',REVISION],check=True)
        subprocess.run(['git','-C',str(cache),'checkout','--detach',REVISION],check=True)
    current=subprocess.check_output(['git','-C',str(cache),'rev-parse','HEAD'],text=True).strip()
    if current!=REVISION:raise ValueError('Existing preview cache differs from pinned revision; left unchanged')
    return cache/'portrait/thumbs'


def copy_preview(row,cache):
    key=row['id']
    if not re.fullmatch(r'f[0-9a-f]{10}',key):raise ValueError('Invalid source image identifier')
    source=cache/(key+'.webp')
    if source.stat().st_size>1_000_000:raise ValueError('Preview exceeds size limit')
    with Image.open(source) as image:
        if image.format!='WEBP' or image.width*image.height>1_000_000:raise ValueError('Unexpected preview format')
        image.verify()
    dest=ROOT/'data/library/portraits'/(key+'.webp')
    temporary=dest.with_suffix('.partial')
    temporary.write_bytes(source.read_bytes());temporary.replace(dest)


def save(file,data):
    temporary=file.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    temporary.replace(file)


def main():
    raw=read_url(f'https://raw.githubusercontent.com/HRuiCcc/RuiC-PoseAtlas/{REVISION}/data/faces.json',2_000_000)
    data=json.loads(raw)
    rows=data['images']
    styles=list(dict.fromkeys(row['style'] for row in rows if row['style']))
    if len(styles)!=len(STYLES) or len(rows)!=1499:raise ValueError('Pinned source schema/count changed')
    mapping=dict(zip(styles,STYLES))
    directory=ROOT/'data/library/portraits';directory.mkdir(parents=True,exist_ok=True)
    cache=prepare_cache()
    for count,row in enumerate(rows,1):
        copy_preview(row,cache)
        if count%500==0 or count==len(rows):print(f'Portrait previews: {count}/{len(rows)}',flush=True)
    portraits=[];hairstyles=[];seen=set()
    for row in rows:
        key=row['id'];length=LENGTHS[row['hair']]
        name,description=mapping.get(row['style'],(length+'人像',length+' hair'))
        path='data/library/portraits/'+key+'.webp'
        common={'path':path,'thumb':path,'source':'AI Model Face Database · あぎ · CC0-1.0','source_url':SOURCE,'original_url':SOURCE+'img/full/'+key+'.png','hair_length':length}
        portraits.append({**common,'id':'character-portrait-'+key,'code':key,'kind':'character','name':name,'category':'人像库 · '+length,'tags':length+' '+name+' '+row['style']+' '+('脸部特写' if row['sec']=='face' else '造型参考'),'prompt':''})
        if row['style'] and row['style'] not in seen:
            seen.add(row['style'])
            hairstyles.append({**common,'id':'hairstyle-'+key,'code':f'HAIR-{len(hairstyles)+1:02}','kind':'hairstyle','name':name,'category':'长发' if description.startswith('long ') else length,'tags':name+' '+description+' '+row['style'],'prompt':description,'reference_mode':'description'})
    save(ROOT/'data/portraits.json',portraits)
    save(ROOT/'data/hairstyles.json',hairstyles)
    save(ROOT/'data/portrait-library-manifest.json',{'source':SOURCE,'author':'あぎ (@agi_aibusi)','license':'CC0-1.0; original site requests no republication of image files','preview_mirror':PREVIEWS,'metadata_repo':'https://github.com/HRuiCcc/RuiC-PoseAtlas','revision':REVISION,'metadata_sha256':hashlib.sha256(raw).hexdigest(),'portraits':len(portraits),'hairstyles':len(hairstyles),'preview_bytes':sum(file.stat().st_size for file in directory.glob('*.webp')),'originals_downloaded':False})
    print(f'Imported {len(portraits)} portraits and {len(hairstyles)} distinct hairstyles.',flush=True)


if __name__=='__main__':main()
