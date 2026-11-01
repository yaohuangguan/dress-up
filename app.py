from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

import aiohttp
from aiohttp import web
from PIL import Image, ImageOps, UnidentifiedImageError

from workflow import IMAGE_PROFILES, add_hairstyle_pass, build_workflow

ROOT = Path(__file__).resolve().parent
COMFY_URL = 'http://127.0.0.1:8188'
KINDS = {'character', 'outfit', 'pose', 'background', 'hairstyle'}
SIZES = IMAGE_PROFILES['fast']['sizes']
COMMON_MODELS = [('text_encoders','qwen_3_4b.safetensors',8_000_000_000),('vae','flux2-vae.safetensors',330_000_000)]
MAX_UPLOAD = 20*1024*1024
Image.MAX_IMAGE_PIXELS = 25_000_000
log = logging.getLogger('local-look')

def read_json(file, default):
    return json.loads(file.read_text(encoding='utf8')) if file.exists() else default

def save_json(file, data):
    file.parent.mkdir(parents=True,exist_ok=True)
    temporary=file.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    temporary.replace(file)

def safe_file(relative):
    path=(ROOT/relative).resolve()
    if not path.is_relative_to((ROOT/'data').resolve()) or not path.is_file():
        raise web.HTTPNotFound(text='图片不存在')
    return path

def public_item(item, angle='front'):
    result={k:v for k,v in item.items() if k not in {'path','thumb','views','thumb_views'}}
    result['angles']=list(item.get('views',{}))
    result['image']=f'/media/{item["id"]}?angle={angle}'
    result['thumbnail']=f'/media/{item["id"]}?angle={angle}&thumb=1'
    return result

def item_path(item,angle='front',thumb=False):
    views=item.get('thumb_views' if thumb else 'views',{})
    relative=views.get(angle) or item.get('thumb' if thumb else 'path')
    return safe_file(relative)

def validate_generation(body,items):
    if not isinstance(body,dict):raise ValueError('请求格式不正确')
    selected=[]
    for kind in ['character','outfit','pose']:
        key=body.get(kind)
        if not isinstance(key,str) or key not in items or items[key]['kind']!=kind:
            raise ValueError('请先选择人物、服装和姿势')
        selected.append(items[key])
    angle=body.get('angle','front')
    if angle not in {'front','diag','side','above','below'}:raise ValueError('无效视角')
    if selected[2].get('views') and angle not in selected[2]['views']:
        raise ValueError('这个姿势没有所选视角，请换一个视角')
    size=body.get('size','portrait')
    if size not in SIZES:raise ValueError('无效画幅')
    quality=body.get('quality','fast')
    if not isinstance(quality,str) or quality not in IMAGE_PROFILES:raise ValueError('无效画质档位')
    prompt=body.get('prompt','')
    if not isinstance(prompt,str) or len(prompt)>1500:raise ValueError('补充描述最多 1500 字')
    seed=body.get('seed')
    if seed is None:seed=secrets.randbelow(2**32)
    if type(seed) is not int or not 0<=seed<2**53:raise ValueError('种子必须是 0 到 2^53-1 的整数')
    background=body.get('background')
    if background is not None:
        if not isinstance(background,str) or background not in items or items[background]['kind']!='background':raise ValueError('无效背景素材')
        selected.append(items[background])
    description=body.get('background_description','')
    if not isinstance(description,str) or len(description)>600:raise ValueError('背景描述最多 600 字')
    hairstyle=body.get('hairstyle')
    if hairstyle is not None:
        if not isinstance(hairstyle,str) or hairstyle not in items or items[hairstyle]['kind']!='hairstyle':raise ValueError('无效发型素材')
        selected.append(items[hairstyle])
    hair_description=body.get('hairstyle_description','')
    if not isinstance(hair_description,str) or len(hair_description)>400:raise ValueError('发型描述最多 400 字')
    return selected,angle,size,prompt,seed,description,quality,hair_description

def image_references(selected):
    # Named styles carry explicit hair descriptions, so their preview faces do not
    # compete with the person's identity. Uploaded hair images remain references.
    return [item for item in selected if not (item['kind']=='hairstyle' and item.get('reference_mode')=='description')]


def compose_prompt(selected,extra,background_description='',hairstyle_description=''):
    assets={item['kind']:item for item in selected}
    references=image_references(selected)
    background='Use a clean professional studio background with soft lighting. '
    location=assets.get('background')
    if location:
        index=references.index(location)+1
        background=f'Use the location in image {index} as the background, preserve its environment and perspective, and place the person naturally into this scene with matching lighting and realistic contact shadows. Image {index} is a location reference only. '+location.get('prompt','')+'. '
    if background_description:
        if not location:background='Set the background location to: '+background_description+'. Match the lighting and contact shadows to this scene. '
        else:background+='Background instructions: '+background_description+'. '
    hair=assets.get('hairstyle')
    hair_prompt='Preserve the hairstyle and hair color of image 1. '
    if hair or hairstyle_description:
        hair_prompt='Change only the hairstyle while preserving the exact facial structure, eyes, nose, mouth, age and identity of image 1. '
        if hair:
            if hair.get('reference_mode')=='description':hair_prompt+='Selected hairstyle: '+hair.get('prompt','')+'. '
            else:hair_prompt+=f'Use image {references.index(hair)+1} for hair shape, length, parting and texture only; ignore that reference person\'s face, skin, clothing and background. '
        if hairstyle_description:hair_prompt+='Hair instructions: '+hairstyle_description+'. '
    return (
        'Create a single unretouched camera photograph of the adult person from image 1, framed full-body. '
        'Image 1 supplies the facial identity, age and gender. Preserve the original facial structure and eye shape. '
        + hair_prompt +
        'Image 1 is the sole reference for natural base skin tone across the face, neck, torso, arms, hands and legs, under consistent neutral white balance. '
        'Image 2 supplies only the garments: preserve colors, fabrics, construction, cut, shoes and accessories. Fit them to the person from image 1, ignoring the display mannequin and its skin color or proportions. '
        'Render hosiery as translucent fabric over the same skin tone, with clear realistic fabric boundaries. '
        'Image 3 supplies only pose action, joint arrangement, hand placement and camera direction. Reconstruct anatomically plausible adult proportions, connected hips, knees and ankles, and natural limb lengths. '
        'Show one adult person wearing the selected garments, head to shoes. '
        'Photographic rendering: visible fine skin pores and subtle natural texture, slight color variations, fine flyaway hairs, detailed fabric fibers, soft directional light, physically plausible shadows, restrained contrast and neutral color grading. '
        'Avoid beauty-filter smoothing, porcelain skin, artificial shine and CGI rendering. '
        + background
        + f'Outfit details: {selected[1].get("prompt","")}. Pose details: {selected[2].get("prompt","")}. '
        + extra
    )

@web.middleware
async def local_boundary(request,handler):
    host=request.headers.get('Host','')
    allowed={'127.0.0.1:7800','localhost:7800'}
    if host not in allowed:
        raise web.HTTPForbidden(text='只接受本机访问')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        if request.headers.get('Origin') not in {None,'http://127.0.0.1:7800','http://localhost:7800'} or request.headers.get('X-Local-Look')!='1':
            raise web.HTTPForbidden(text='请求来源无效')
    try:
        response=await handler(request)
    except (ValueError,KeyError,json.JSONDecodeError) as exc:
        response=web.json_response({'error':str(exc)},status=400)
    except web.HTTPException:
        raise
    except Exception:
        log.exception('request failed')
        response=web.json_response({'error':'操作失败，请查看项目 logs 日志'},status=500)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; manifest-src 'self'"
    if request.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

async def comfy_json(app,method,path,**kwargs):
    async with app['client'].request(method,COMFY_URL+path,timeout=aiohttp.ClientTimeout(total=20),**kwargs) as response:
        data=await response.json(content_type=None)
        if response.status>=400:raise ValueError('ComfyUI 请求失败：'+str(data)[:600])
        return data

async def status(request):
    app=request.app
    models=[]
    for folder,name,minimum in [('diffusion_models',p['model'],4_000_000_000) for p in IMAGE_PROFILES.values()]+COMMON_MODELS:
        file=ROOT/'runtime/ComfyUI/models'/folder/name
        part=file.with_suffix('.partial')
        models.append({'name':name,'ready':file.exists() and file.stat().st_size>=minimum,'bytes':file.stat().st_size if file.exists() else (part.stat().st_size if part.exists() else 0)})
    connected=False
    gpu=None
    error=None
    try:
        data=await comfy_json(app,'GET','/system_stats')
        gpu=next((x for x in data.get('devices',[]) if x.get('type')=='cuda'),None)
        connected=True
    except (aiohttp.ClientError,asyncio.TimeoutError,ValueError):
        error='ComfyUI 未连接，请使用启动脚本启动两个本地服务'
    installed={x['name']:x['ready'] for x in models}
    profiles={key:{'label':p['label'],'model':p['model'],'steps':p['steps'],'sizes':p['sizes'],'ready':connected and installed[p['model']] and all(installed[m[1]] for m in COMMON_MODELS)} for key,p in IMAGE_PROFILES.items()}
    counts={kind:sum(x['kind']==kind for x in app['items'].values()) for kind in KINDS}
    return web.json_response({'connected':connected,'ready':any(x['ready'] for x in profiles.values()),'profiles':profiles,'gpu':gpu,'models':models,'counts':counts,'pose_images':sum(len(x.get('views',{})) for x in app['items'].values()),'active_job':app['active'],'active_kind':'video' if app['active'] in app.get('video_jobs',{}) else 'image','error':error,'engine':'FLUX.2 Klein Base / Klein 4B · 本地 CUDA'})

async def catalog(request):
    params=request.query
    kind=params.get('kind','pose')
    if kind not in KINDS:raise ValueError('无效素材类型')
    query=params.get('q','').casefold()[:200]
    category=params.get('category','')
    angle=params.get('angle','front')
    page=max(1,min(10000,int(params.get('page','1'))))
    all_items=[x for x in request.app['items'].values() if x['kind']==kind]
    categories=sorted({x['category'] for x in all_items})
    found=[x for x in all_items if (not category or x['category']==category) and (not query or query in ' '.join(str(x.get(k,'')) for k in ['name','code','tags','category']).casefold()) and (not x.get('views') or angle in x['views'])]
    return web.json_response({'items':[public_item(x,angle) for x in found[(page-1)*36:page*36]],'total':len(found),'page':page,'pages':max(1,(len(found)+35)//36),'categories':categories})

async def item(request):
    found=request.app['items'].get(request.match_info['id'])
    if not found:raise web.HTTPNotFound()
    return web.json_response(public_item(found,request.query.get('angle','front')))

async def media(request):
    found=request.app['items'].get(request.match_info['id'])
    if not found:raise web.HTTPNotFound()
    return web.FileResponse(item_path(found,request.query.get('angle','front'),request.query.get('thumb')=='1'))

async def upload(request):
    reader=await request.multipart()
    kind=None
    data=None
    original='自定义素材'
    fields=0
    async for field in reader:
        fields+=1
        if fields>2:raise ValueError('上传字段过多')
        if field.name=='kind':
            value=await field.read_chunk(1024)
            kind=value.decode('utf8')
            if kind not in KINDS:raise ValueError('无效素材类型')
        elif field.name=='image':
            original=Path(unquote(field.filename or '自定义素材').replace('\\','/')).stem[:60]
            data=bytearray()
            while chunk:=await field.read_chunk(65536):
                data.extend(chunk)
                if len(data)>MAX_UPLOAD:raise web.HTTPRequestEntityTooLarge(max_size=MAX_UPLOAD,actual_size=len(data))
        else:raise ValueError('无效上传字段')
    if kind not in KINDS or not data:raise ValueError('请选择图片')
    found=store_upload(request.app,data,kind,original)
    return web.json_response(public_item(found),status=201)

def store_upload(app,data,kind,original):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {'PNG','JPEG','WEBP'}:raise ValueError('支持 PNG、JPG、WebP 图片')
            if image.width*image.height>25_000_000:raise ValueError('图片像素过大')
            image=ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((1600,1600))
            buffer=io.BytesIO()
            image.save(buffer,format='PNG')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ValueError('文件不是有效图片')
    key=kind+'-'+uuid.uuid4().hex
    relative='data/uploads/'+key+'.png'
    target=ROOT/relative
    target.parent.mkdir(exist_ok=True,parents=True)
    target.write_bytes(buffer.getvalue())
    found={'id':key,'code':'LOCAL','kind':kind,'name':original,'category':'我的素材','tags':'本地导入','prompt':'','path':relative,'thumb':relative,'source':'用户本地导入'}
    app['uploads'].append(found)
    save_json(ROOT/'data/uploads.json',app['uploads'])
    app['items'][key]=found
    return found

def persist_job(app,job):
    app['jobs'][job['id']]=job
    save_json(ROOT/'data/jobs'/(job['id']+'.json'),job)

async def run_job(app,job,selected):
    prompt_id=None
    try:
        job.update(status='preparing',message='正在准备所选参考图',progress=0)
        persist_job(app,job)
        names=[]
        for asset in image_references(selected):
            kind=asset['kind']
            source=item_path(asset,job['angle'])
            with Image.open(source) as image:
                image=ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((768,1024))
                buffer=io.BytesIO()
                image.save(buffer,format='PNG')
            form=aiohttp.FormData()
            form.add_field('image',buffer.getvalue(),filename=job['id']+'-'+kind+'.png',content_type='image/png')
            form.add_field('type','input')
            form.add_field('subfolder','LocalLookStudio')
            result=await comfy_json(app,'POST','/upload/image',data=form)
            names.append((result.get('subfolder','')+'/'+result['name']).lstrip('/'))
        quality=job.get('quality','fast')
        width,height=IMAGE_PROFILES[quality]['sizes'][job['size']]
        graph=build_workflow(names[:4],job['full_prompt'],job['seed'],width,height,quality=quality)
        if job.get('stages',1)==2:
            graph=add_hairstyle_pass(graph,names[-1],job['hairstyle_prompt'],job['seed'],width,height,quality)
        save_json(ROOT/'data/jobs'/(job['id']+'.workflow.json'),graph)
        client_id=uuid.uuid4().hex
        stage=1
        async with app['client'].ws_connect(COMFY_URL+'/ws?clientId='+client_id,timeout=aiohttp.ClientWSTimeout(ws_receive=1800)) as ws:
            queued=await comfy_json(app,'POST','/prompt',json={'prompt':graph,'client_id':client_id})
            if queued.get('node_errors'):raise ValueError('工作流校验失败：'+str(queued['node_errors'])[:600])
            prompt_id=queued['prompt_id']
            job.update(prompt_id=prompt_id,status='queued',message='已进入本地队列，首次加载模型需要几分钟')
            persist_job(app,job)
            async for msg in ws:
                if msg.type!=aiohttp.WSMsgType.TEXT:continue
                event=json.loads(msg.data)
                event_type=event.get('type')
                data=event.get('data',{})
                if data.get('prompt_id')!=prompt_id:continue
                if event_type=='execution_error':raise ValueError(data.get('exception_message','ComfyUI 生图失败')[:600])
                if event_type=='execution_interrupted':raise ValueError('任务已取消')
                if event_type=='progress':
                    job.update(status='running',progress=round(100*((stage-1)+data['value']/max(1,data['max']))/job.get('stages',1)),message=f'正在采样 {data["value"]} / {data["max"]}'+(f' · 第 {stage}/2 轮' if job.get('stages',1)==2 else ''))
                elif event_type=='executing':
                    node=data.get('node')
                    if node is None:break
                    stage=2 if str(node).startswith('hair-') else 1
                    node_type=graph.get(str(node),{}).get('class_type','')
                    message='正在本地生成'
                    if node_type=='CLIPTextEncode':message='正在 CPU 编码描述，首次加载较慢'
                    elif node_type=='VAEEncode':message='正在编码参考图'
                    elif node_type=='SamplerCustomAdvanced':message='正在 GPU 采样，8GB 显存按需卸载'
                    elif node_type=='VAEDecodeTiled':message='正在解码成图'
                    job.update(status='running',message=message)
                elif event_type=='execution_success':break
                persist_job(app,job)
        history=await comfy_json(app,'GET','/history/'+prompt_id)
        record=history.get(prompt_id,{})
        outputs=[image for output in record.get('outputs',{}).values() for image in output.get('images',[]) if image.get('type')=='output']
        if not outputs:raise ValueError('ComfyUI 未返回图片，请检查运行日志')
        output=outputs[0]
        async with app['client'].get(COMFY_URL+'/view',params={k:output[k] for k in ['filename','subfolder','type']},timeout=aiohttp.ClientTimeout(total=60)) as response:
            response.raise_for_status()
            image_data=await response.read()
        result_dir=ROOT/'data/results'
        result_dir.mkdir(exist_ok=True)
        (result_dir/(job['id']+'.png')).write_bytes(image_data)
        job.update(status='completed',message='生成完成',progress=100,image='/results/'+job['id']+'.png',elapsed=round(time.time()-job['created'],1))
    except asyncio.CancelledError:
        job.update(status='interrupted',message='服务已停止，任务可在 ComfyUI 历史中查看')
        raise
    except Exception as exc:
        log.exception('generation failed %s',job['id'])
        message=str(exc) or type(exc).__name__
        if 'out of memory' in message.lower():message='显存不足：请关闭其他占用显卡的软件，或切换快速预览并缩小画幅重试'
        job.update(status='failed',message=message[:600])
    finally:
        persist_job(app,job)
        app['active']=None

async def generate(request):
    app=request.app
    selected,angle,size,extra,seed,background_description,quality,hairstyle_description=validate_generation(await request.json(),app['items'])
    if app['active']:return web.json_response({'error':'已有任务运行中，请等待完成'},status=409)
    profile=IMAGE_PROFILES[quality]
    required=[('diffusion_models',profile['model'])]+[(folder,name) for folder,name,_ in COMMON_MODELS]
    if not all((ROOT/'runtime/ComfyUI/models'/folder/name).is_file() for folder,name in required):
        return web.json_response({'error':'模型尚未下载完成，请查看引擎状态'},status=503)
    try:await comfy_json(app,'GET','/system_stats')
    except (aiohttp.ClientError,asyncio.TimeoutError):return web.json_response({'error':'ComfyUI 未启动，请运行启动脚本'},status=503)
    # Claim the single GPU slot after the network await; concurrent requests must recheck.
    if app['active']:return web.json_response({'error':'已有任务运行中'},status=409)
    two_pass=len(image_references(selected))>4
    body_selection=[x for x in selected if x['kind']!='hairstyle'] if two_pass else selected
    hair_edit='Change only the hairstyle of the adult person in image 1 to match the hair in image 2. Preserve the exact facial identity, skin tone, expression, pose, garments, shoes, background, lighting, framing and photographic texture of image 1. Use image 2 for hair shape and texture only. '+hairstyle_description
    job={'id':uuid.uuid4().hex,'created':time.time(),'status':'queued','progress':0,'message':'准备生成','seed':seed,'angle':angle,'size':size,'quality':quality,'width':profile['sizes'][size][0],'height':profile['sizes'][size][1],'model':profile['model'],'steps':profile['steps'],'prompt':extra,'background_description':background_description,'hairstyle_description':hairstyle_description,'stages':2 if two_pass else 1,'hairstyle_prompt':hair_edit if two_pass else '', 'full_prompt':compose_prompt(body_selection,extra,background_description,'' if two_pass else hairstyle_description),'selection':{x['kind']:public_item(x,angle) for x in selected}}
    app['active']=job['id']
    persist_job(app,job)
    task=asyncio.create_task(run_job(app,job,selected))
    app['tasks'].add(task)
    task.add_done_callback(app['tasks'].discard)
    return web.json_response(job,status=202)

async def get_job(request):
    job=request.app['jobs'].get(request.match_info['id'])
    if not job:raise web.HTTPNotFound()
    return web.json_response(job)

async def history(request):
    return web.json_response(sorted(request.app['jobs'].values(),key=lambda x:x['created'],reverse=True)[:100])

async def result(request):
    key=request.match_info['id']
    job=request.app['jobs'].get(key)
    if not job or job['status']!='completed':raise web.HTTPNotFound()
    response=web.FileResponse(safe_file('data/results/'+key+'.png'))
    if request.query.get('download')=='1':response.headers['Content-Disposition']='attachment; filename="look-'+key[:8]+'.png"'
    return response

async def workflow(request):
    key=request.match_info['id']
    if key not in request.app['jobs']:raise web.HTTPNotFound()
    return web.FileResponse(safe_file('data/jobs/'+key+'.workflow.json'),headers={'Content-Disposition':'attachment; filename="look-workflow.json"'})

async def static(request):
    name=request.match_info.get('name','index.html')
    if name not in {'index.html','app.js','video.js','video.css','style.css','glass.css','manifest.webmanifest','sw.js','icon-192.png','icon-512.png'}:raise web.HTTPNotFound()
    response=web.FileResponse(ROOT/'web'/name)
    if name=='sw.js':response.headers['Cache-Control']='no-cache'
    return response

async def lifecycle(app):
    async with aiohttp.ClientSession() as client:
        app['client']=client
        yield
        for task in list(app['tasks']):task.cancel()
        await asyncio.gather(*app['tasks'],return_exceptions=True)

def create_app():
    app=web.Application(middlewares=[local_boundary],client_max_size=MAX_UPLOAD+65536)
    uploads=read_json(ROOT/'data/uploads.json',[])
    base=read_json(ROOT/'data/catalog.json',[])
    characters=read_json(ROOT/'data/characters.json',[])
    if characters:base=[x for x in base if x['kind']!='character']
    app['items']={x['id']:x for x in base+characters+read_json(ROOT/'data/portraits.json',[])+read_json(ROOT/'data/hairstyles.json',[])+read_json(ROOT/'data/backgrounds.json',[])+uploads}
    app['uploads']=uploads
    app['jobs']={}
    for file in (ROOT/'data/jobs').glob('*.json'):
        if file.name.endswith('.workflow.json'):continue
        job=read_json(file,{})
        if job.get('status') not in {'completed','failed','interrupted'}:
            job.update(status='interrupted',message='服务曾重启；可在 ComfyUI 历史查看原任务')
            save_json(file,job)
        if 'id' in job:app['jobs'][job['id']]=job
    app['active']=None
    app['tasks']=set()
    from video_engine import register as register_video
    register_video(app,ROOT,comfy_json,save_json,item_path,lambda:COMFY_URL)
    from story_writer import register as register_writer
    register_writer(app)
    app.cleanup_ctx.append(lifecycle)
    app.add_routes([web.get('/api/status',status),web.get('/api/catalog',catalog),web.get('/api/items/{id}',item),web.post('/api/uploads',upload),web.post('/api/generate',generate),web.get('/api/jobs/{id}',get_job),web.get('/api/history',history),web.get('/api/workflow/{id}',workflow),web.get('/media/{id}',media),web.get('/results/{id}.png',result),web.get('/',static),web.get('/{name}',static)])
    from mobile import register_mobile
    register_mobile(app,lambda data,name:public_item(store_upload(app,data,'character',name)),ROOT/'web')
    return app

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    print('衣见 · Local Look Studio: http://127.0.0.1:7800',flush=True)
    web.run_app(create_app(),host='127.0.0.1',port=7800,print=None)
