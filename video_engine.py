"""Local video jobs: native ComfyUI clips, storyboard keyframes and MP4 export."""
import asyncio
import io
import json
import logging
import secrets
import time
import uuid
from pathlib import Path

import aiohttp
from aiohttp import web
from PIL import Image, ImageOps

from video_workflow import MODEL, ENCODER, build_video_workflow
from workflow import build_workflow

log=logging.getLogger('local-look.video')
TERMINAL={'completed','failed','interrupted'}

def model_status(root):
    models=[]
    for folder,name,size in [('checkpoints',MODEL,4461695684),('text_encoders',ENCODER,4893934904)]:
        file=root/'runtime/ComfyUI/models'/folder/name
        part=file.with_suffix('.partial')
        models.append({'name':name,'ready':file.exists() and file.stat().st_size==size,'bytes':file.stat().st_size if file.exists() else part.stat().st_size if part.exists() else 0})
    return models

def save(app,job):
    app['video_jobs'][job['id']]=job
    app['video_save'](app['video_root']/'data/video_jobs'/(job['id']+'.json'),job)

async def upload_image(app,file,name):
    with Image.open(file) as image:
        image=ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((768,1024))
        buffer=io.BytesIO();image.save(buffer,format='PNG')
    form=aiohttp.FormData()
    form.add_field('image',buffer.getvalue(),filename=name+'.png',content_type='image/png')
    form.add_field('type','input');form.add_field('subfolder','LocalLookStudio')
    result=await app['video_comfy'](app,'POST','/upload/image',data=form)
    return (result.get('subfolder','')+'/'+result['name']).lstrip('/')

async def execute(app,job,graph,label,folder):
    app['video_save'](folder/(label+'.workflow.json'),graph)
    client=uuid.uuid4().hex
    url=app['video_url']()
    async with app['client'].ws_connect(url+'/ws?clientId='+client,timeout=aiohttp.ClientWSTimeout(ws_receive=3600)) as ws:
        queued=await app['video_comfy'](app,'POST','/prompt',json={'prompt':graph,'client_id':client})
        if queued.get('node_errors'):raise ValueError('视频工作流校验失败：'+str(queued['node_errors'])[:400])
        prompt_id=queued['prompt_id']
        job.update(prompt_id=prompt_id,message=label+' · 正在加载模型');save(app,job)
        async for msg in ws:
            if msg.type!=aiohttp.WSMsgType.TEXT:continue
            event=json.loads(msg.data);data=event.get('data',{})
            if data.get('prompt_id')!=prompt_id:continue
            kind=event.get('type')
            if kind=='execution_error':raise ValueError(data.get('exception_message','视频生成失败')[:500])
            if kind=='execution_interrupted':raise ValueError('任务已在 ComfyUI 中停止')
            if kind=='progress':
                job.update(message=label+f' · 采样 {data["value"]}/{data["max"]}',step_progress=round(100*data['value']/max(data['max'],1)))
            elif kind=='executing':
                node=data.get('node')
                if node is None:break
                job.update(message=label+' · '+{'CLIPTextEncode':'编码描述','SamplerCustomAdvanced':'本地 GPU 采样','VAEDecodeTiled':'解码画面','SaveVideo':'导出 MP4'}.get(graph.get(str(node),{}).get('class_type'),'准备画面'))
            elif kind=='execution_success':break
            save(app,job)
    history=await app['video_comfy'](app,'GET','/history/'+prompt_id)
    outputs=[x for o in history.get(prompt_id,{}).get('outputs',{}).values() for x in o.get('images',[]) if x.get('type')=='output']
    if not outputs:raise ValueError('引擎没有返回生成文件')
    output=outputs[0]
    extension=Path(output['filename']).suffix.lower()
    if extension not in {'.png','.mp4'}:raise ValueError('引擎返回了不支持的文件格式')
    target=folder/(label+extension)
    async with app['client'].get(url+'/view',params={k:output[k] for k in ['filename','subfolder','type']},timeout=aiohttp.ClientTimeout(total=180)) as response:
        response.raise_for_status()
        with target.open('wb') as stream:
            async for chunk in response.content.iter_chunked(1024*1024):stream.write(chunk)
    return target

async def run(app,job,source):
    root=app['video_root'];folder=root/'data/videos'/job['id'];folder.mkdir(parents=True,exist_ok=True)
    try:
        job.update(status='running');save(app,job)
        image=await upload_image(app,source,job['id']+'-source')
        if job['mode']=='clip':
            graph=build_video_workflow(image,job['motion'],job['seed'],frames=job['frames'])
            output=await execute(app,job,graph,'clip',folder)
            if output.suffix!='.mp4':raise ValueError('视频引擎未返回 MP4')
            await asyncio.to_thread(output.replace,folder/'film.mp4')
        else:
            clips=[];total=len(job['scenes'])
            for index,scene in enumerate(job['scenes']):
                job.update(scene=index+1,progress=round(90*index/total),message=f'分镜 {index+1}/{total} · 制作关键帧');save(app,job)
                prompt='Create a cinematic movie still using the same adult person from the reference image. Preserve this person\'s face, hairstyle, skin tone and outfit consistently. One coherent film scene, realistic photography. '+scene['visual']
                keyframe=await execute(app,job,build_workflow([image],prompt,job['seed']+index,640,896),f'{index+1:02}-keyframe',folder)
                if keyframe.suffix!='.png':raise ValueError('关键帧引擎未返回图片')
                frame=await upload_image(app,keyframe,job['id']+f'-scene-{index}')
                motion=scene['visual']+' '+scene['motion']+' Maintain the same adult person and clothing. Continuous natural motion, cinematic live action.'
                clip=await execute(app,job,build_video_workflow(frame,motion,job['seed']+index,frames=193),f'{index+1:02}-video',folder)
                if clip.suffix!='.mp4':raise ValueError('视频引擎未返回 MP4')
                clips.append(str(clip))
            job.update(progress=94,message='分镜生成完成 · 本地中文配音与剪辑');save(app,job)
            payload=folder/'edit.json'
            app['video_save'](payload,{'title':job['title'],'clips':clips,'scenes':job['scenes']})
            import subprocess,sys
            process=await asyncio.create_subprocess_exec(sys.executable,str(root/'scripts/compose_video.py'),str(payload),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0)
            try:
                output,_=await process.communicate()
            finally:
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
            (folder/'edit.log').write_bytes(output)
            if process.returncode:raise ValueError('本地剪辑失败，已保留分镜文件；请查看 edit.log')
        import av
        with av.open(str(folder/'film.mp4')) as container:
            stream=container.streams.video[0]
            duration=float(stream.duration*stream.time_base) if stream.duration else float(container.duration/av.time_base)
            dimensions=[stream.width,stream.height]
        job.update(status='completed',message='短片已生成并保存在本机',video='/videos/'+job['id']+'.mp4',progress=100,duration=round(duration,2),dimensions=dimensions,elapsed=round(time.time()-job['created'],1))
    except asyncio.CancelledError:
        job.update(status='interrupted',message='服务已停止，已完成的分镜保留在本机');raise
    except Exception as exc:
        log.exception('video failed %s',job['id'])
        job.update(status='failed',message=str(exc)[:600] or type(exc).__name__)
    finally:
        save(app,job);app['active']=None

async def info(request):
    app=request.app;models=model_status(app['video_root'])
    voice=all((app['video_root']/'runtime/voice'/name).is_file() for name in ['config.json','kokoro-v1_1-zh.pth','zf_094.pt'])
    return web.json_response({'ready':all(x['ready'] for x in models),'voice_ready':voice,'models':models,'engine':'LTX-Video 2B 0.9.8 distilled FP8','templates':app['video_templates'],'active':app['active'] if app['active'] in app['video_jobs'] else None})

async def generate(request):
    app=request.app;body=await request.json()
    if not isinstance(body,dict):raise ValueError('请求格式不正确')
    mode=body.get('mode','clip')
    if mode not in {'clip','story'}:raise ValueError('无效视频模式')
    seed=body.get('seed')
    if seed is None:seed=secrets.randbelow(2**32)
    if type(seed)is not int or not 0<=seed<2**53-100:raise ValueError('无效随机种子')
    source_id=body.get('source_job');asset_id=body.get('source_asset')
    if isinstance(source_id,str) and source_id in app['jobs']:
        source_job=app['jobs'][source_id]
        if source_job.get('status')!='completed':raise ValueError('请选择已完成的图片')
        source=app['video_root']/'data/results'/(source_id+'.png')
        poster='/results/'+source_id+'.png'
        source_ref={'source_job':source_id}
    elif isinstance(asset_id,str) and asset_id in app['items']:
        asset=app['items'][asset_id]
        source=app['video_item_path'](asset)
        poster='/media/'+asset_id
        source_ref={'source_asset':asset_id}
    else:raise ValueError('请选择本机图片，不接受外部链接或文件路径')
    if not source.is_file():raise ValueError('参考图片不存在')
    motion=body.get('motion','')
    if not isinstance(motion,str) or not 1<=len(motion.strip())<=2500:raise ValueError('动作描述需要 1–2500 字')
    frames=body.get('frames',97)
    if type(frames)is not int or frames not in {73,97,121}:raise ValueError('无效片段长度')
    scenes=[];title='动态片段'
    if mode=='story':
        template=next((x for x in app['video_templates'] if x['id']==body.get('template')),None)
        if not template:raise ValueError('请选择故事模板')
        scenes=body.get('scenes',template['scenes']);title=template['title']
        title=body.get('title',title)
        if not isinstance(title,str) or not 1<=len(title)<=60:raise ValueError('标题需要 1–60 字')
        if not isinstance(scenes,list) or len(scenes)!=8:raise ValueError('一分钟故事需要 8 个分镜')
        for scene in scenes:
            if not isinstance(scene,dict):raise ValueError('无效分镜')
            for field,limit in [('title',60),('narration',45),('visual',2000),('motion',1200)]:
                if not isinstance(scene.get(field),str) or not 1<=len(scene[field])<=limit:raise ValueError('分镜字段缺失或过长；每段旁白最多 45 字，建议 20–35 字')
    if app['active']:return web.json_response({'error':'已有图片或视频任务运行中，请等待完成'},status=409)
    if not all(x['ready'] for x in model_status(app['video_root'])):return web.json_response({'error':'视频模型尚未安装完成'},status=503)
    if mode=='story' and not all((app['video_root']/'runtime/voice'/name).is_file() for name in ['config.json','kokoro-v1_1-zh.pth','zf_094.pt']):return web.json_response({'error':'中文神经配音模型尚未安装完成'},status=503)
    try:await app['video_comfy'](app,'GET','/system_stats')
    except (aiohttp.ClientError,asyncio.TimeoutError,ValueError):return web.json_response({'error':'ComfyUI 未就绪'},status=503)
    if app['active']:return web.json_response({'error':'已有任务运行中'},status=409)
    job={'id':uuid.uuid4().hex,'kind':'video','mode':mode,'title':title,'created':time.time(),'status':'queued','progress':0,'seed':seed,'motion':motion,'frames':frames,'scenes':scenes,'poster':poster,'message':'准备视频任务',**source_ref}
    app['active']=job['id'];save(app,job)
    task=asyncio.create_task(run(app,job,source));app['tasks'].add(task);task.add_done_callback(app['tasks'].discard)
    return web.json_response(job,status=202)

async def get_job(request):
    job=request.app['video_jobs'].get(request.match_info['id'])
    if not job:raise web.HTTPNotFound()
    return web.json_response(job)

async def history(request):
    return web.json_response(sorted(request.app['video_jobs'].values(),key=lambda x:x['created'],reverse=True)[:100])

async def result(request):
    key=request.match_info['id'];job=request.app['video_jobs'].get(key)
    if not job or job.get('status')!='completed':raise web.HTTPNotFound()
    target=request.app['video_root']/'data/videos'/key/'film.mp4'
    if not target.is_file():raise web.HTTPNotFound()
    headers={'Content-Type':'video/mp4','Cache-Control':'private, no-store'}
    if request.query.get('download')=='1':headers['Content-Disposition']='attachment; filename="film-'+key[:8]+'.mp4"'
    return web.FileResponse(target,headers=headers)

def register(app,root,comfy,save_json,item_path,url):
    app['video_root']=root;app['video_comfy']=comfy;app['video_save']=save_json;app['video_item_path']=item_path;app['video_url']=url
    app['video_templates']=json.loads((Path(__file__).parent/'data/story-templates.json').read_text(encoding='utf8'))
    jobs={}
    for file in (root/'data/video_jobs').glob('*.json'):
        job=json.loads(file.read_text(encoding='utf8'))
        if job.get('status') not in TERMINAL:
            job.update(status='interrupted',message='服务曾重启，已完成的分镜仍保留在本机');save_json(file,job)
        jobs[job['id']]=job
    app['video_jobs']=jobs
    app.add_routes([web.get('/api/video/status',info),web.post('/api/video/generate',generate),web.get('/api/video/history',history),web.get('/api/video/jobs/{id}',get_job),web.get('/videos/{id}.mp4',result)])
