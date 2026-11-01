"""On-demand CPU Qwen scriptwriter; releases model memory after each request."""
import asyncio
import json
import os
import secrets
import socket
import time
import uuid
from pathlib import Path

import aiohttp
from aiohttp import web

def files(root):
    return root/'runtime/writer/bin/llama-server.exe',root/'runtime/writer/Qwen3-4B-Q4_K_M.gguf'

async def status(request):
    root=request.app['video_root']
    return web.json_response({'ready':all(x.is_file() for x in files(root)),'model':'Qwen3 4B Q4_K_M','busy':bool(request.app.get('writer_busy'))})

def validate_script(data):
    if not isinstance(data,dict) or not isinstance(data.get('title'),str) or not 1<=len(data['title'])<=60:raise ValueError('编剧返回的标题格式错误')
    if not isinstance(data.get('logline'),str) or len(data['logline'])>300:raise ValueError('编剧返回的梗概格式错误')
    scenes=data.get('scenes')
    if not isinstance(scenes,list) or len(scenes)!=8:raise ValueError('编剧必须返回 8 个分镜')
    for scene in scenes:
        if not isinstance(scene,dict):raise ValueError('分镜格式错误')
        for field,limit in [('title',60),('narration',45),('visual',2000),('motion',1200)]:
            if not isinstance(scene.get(field),str) or not 1<=len(scene[field])<=limit:raise ValueError('编剧返回的分镜字段缺失或过长')
        if not scene['visual'].isascii() or not scene['motion'].isascii():raise ValueError('场景与运镜需要英文，请重新生成分镜')
    return {key:data[key] for key in ['title','logline','scenes']}

async def write(request):
    app=request.app;body=await request.json()
    if not isinstance(body,dict) or not isinstance(body.get('idea'),str) or not 1<=len(body['idea'].strip())<=600:raise ValueError('故事主题需要 1–600 字')
    if app['active'] or app.get('writer_busy'):return web.json_response({'error':'请等待当前任务完成后再写分镜'},status=409)
    exe,model=files(app['video_root'])
    if not exe.is_file() or not model.is_file():return web.json_response({'error':'本地编剧模型未安装'},status=503)
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',7803))==0:return web.json_response({'error':'编剧端口被占用，请检查 7803'},status=503)
    app['writer_busy']=True;app['active']='scriptwriter'
    job={'id':uuid.uuid4().hex,'status':'running','created':time.time(),'message':'本地编剧正在写分镜'}
    app['script_jobs'][job['id']]=job
    task=asyncio.create_task(run(app,body,job));app['tasks'].add(task);task.add_done_callback(app['tasks'].discard)
    return web.json_response(job,status=202)

async def get_job(request):
    job=request.app['script_jobs'].get(request.match_info['id'])
    if not job:raise web.HTTPNotFound()
    return web.json_response(job)

async def run(app,body,job):
    exe,model=files(app['video_root'])
    process=None;logfile=None
    try:
        root=app['video_root'];(root/'logs').mkdir(exist_ok=True)
        logfile=(root/'logs/writer.log').open('ab')
        token=secrets.token_urlsafe(32)
        environment={**os.environ,'LLAMA_API_KEY':token}
        process=await asyncio.create_subprocess_exec(str(exe),'-m',str(model),'--host','127.0.0.1','--port','7803','-c','8192','-t','8','-ngl','0','-np','1','--jinja','--no-webui','--no-slots','--cors-origins','localhost',env=environment,stdout=logfile,stderr=asyncio.subprocess.STDOUT,creationflags=__import__('subprocess').CREATE_NO_WINDOW if os.name=='nt' else 0)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=900),headers={'Authorization':'Bearer '+token}) as client:
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if process.returncode is not None:raise ValueError('编剧进程启动失败，请查看 writer.log')
                try:
                    async with client.get('http://127.0.0.1:7803/health',timeout=aiohttp.ClientTimeout(total=2)) as response:
                        if response.status==200:break
                except (aiohttp.ClientError,asyncio.TimeoutError):pass
                await asyncio.sleep(.5)
            else:raise ValueError('本地编剧模型加载超时')
            fields={'title':{'type':'string'},'narration':{'type':'string','maxLength':45},'visual':{'type':'string','pattern':'^[ -~]+$'},'motion':{'type':'string','pattern':'^[ -~]+$'}}
            schema={'type':'object','properties':{'title':{'type':'string'},'logline':{'type':'string'},'scenes':{'type':'array','minItems':8,'maxItems':8,'items':{'type':'object','properties':fields,'required':['title','narration','visual','motion'],'additionalProperties':False}}},'required':['title','logline','scenes'],'additionalProperties':False}
            system='You are a suspense film director. Write a coherent 64-second short film with exactly 8 shots of 8 seconds each. Each shot reveals a new concrete clue that causes the next action; finish with a clear twist, not a vague statement about realizing the truth. One adult woman, consistent face and clothing. Write title, logline, shot title and narration in Chinese. Narration: 20-35 Chinese characters per shot, spoken in under 8 seconds. IMPORTANT: visual and motion must be in ENGLISH only. Visual describes a specific cinematic keyframe with camera framing, location and lighting. Motion describes subtle character action and camera movement. Never ask the image model to render readable text, fast actions or complex interactions. Return JSON with title, logline and 8 scenes, each containing title, narration, visual, motion. No reasoning, no markdown.'
            payload={'messages':[{'role':'system','content':system},{'role':'user','content':body['idea']+' /no_think'}],'temperature':.7,'max_tokens':3600,'stream':False,'response_format':{'type':'json_schema','json_schema':{'name':'story','strict':True,'schema':schema}},'chat_template_kwargs':{'enable_thinking':False}}
            async with client.post('http://127.0.0.1:7803/v1/chat/completions',json=payload) as response:
                if response.status!=200:raise ValueError('本地编剧请求失败，请查看 writer.log')
                result=await response.json()
            job.update(status='completed',result=validate_script(json.loads(result['choices'][0]['message']['content'])),message='分镜已生成')
    except asyncio.CancelledError:
        job.update(status='failed',message='编剧任务已停止');raise
    except Exception as exc:
        job.update(status='failed',message=str(exc)[:300] or '编剧失败，请查看 writer.log')
    finally:
        if process and process.returncode is None:
            process.terminate()
            try:await asyncio.wait_for(process.wait(),10)
            except asyncio.TimeoutError:process.kill();await process.wait()
        if logfile:logfile.close()
        app['writer_busy']=False;app['active']=None

def register(app):
    app['writer_busy']=False
    app['script_jobs']={}
    app.add_routes([web.get('/api/video/writer',status),web.post('/api/video/script',write),web.get('/api/video/script/{id}',get_job)])
