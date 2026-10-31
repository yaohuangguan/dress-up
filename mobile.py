"""A separate LAN-only, one-use mobile photo upload surface."""
import base64
import hashlib
import io
import ipaddress
import secrets
import socket
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

import psutil
import qrcode
from aiohttp import web

NETWORKS=[ipaddress.ip_network(value) for value in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']]

def local_addresses():
    found=[]
    stats=psutil.net_if_stats()
    for name,addresses in psutil.net_if_addrs().items():
        if name not in stats or not stats[name].isup:continue
        if any(word in name.casefold() for word in ['vethernet','wsl','loopback','tailscale','virtual','bluetooth']):continue
        for address in addresses:
            if address.family!=socket.AF_INET:continue
            ip=ipaddress.ip_address(address.address)
            if any(ip in network for network in NETWORKS):
                preferred=0 if any(word in name.casefold() for word in ['wlan','wi-fi','wireless','无线']) else 1
                found.append({'ip':str(ip),'name':name,'rank':preferred})
    return sorted(found,key=lambda x:(x['rank'],x['ip']))

def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()

class MobileUploads:
    def __init__(self,on_upload,web_dir,max_upload=20*1024*1024):
        self.on_upload=on_upload
        self.web_dir=web_dir
        self.max_upload=max_upload
        self.sessions={}
        self.runner=None
        self.allowed_hosts={'localhost','127.0.0.1'}

    def mint(self,address,addresses):
        if address not in {x['ip'] for x in addresses}:raise ValueError('请选择本机可用的局域网地址')
        now=time.time()
        self.sessions={key:value for key,value in self.sessions.items() if value['expires']>now}
        if len(self.sessions)>=10:raise ValueError('二维码较多，请等待旧二维码过期')
        # Creating another QR revokes previous unused codes from this desktop.
        for session in self.sessions.values():
            if session['status']=='waiting':session['status']='revoked'
        token=secrets.token_urlsafe(24)
        key=uuid.uuid4().hex
        expires=now+600
        self.sessions[key]={'hash':token_hash(token),'expires':expires,'status':'waiting','item':None}
        self.allowed_hosts.add(address)
        url=f'http://{address}:7801/#{token}'
        buffer=io.BytesIO()
        qrcode.make(url).save(buffer,format='PNG')
        return {'id':key,'url':url,'expires':expires,'qr':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),'addresses':addresses,'ip':address}

    async def new_session(self,request):
        body=await request.json()
        if not isinstance(body,dict):raise ValueError('无效请求')
        addresses=local_addresses()
        if not addresses:return web.json_response({'error':'未找到局域网地址，请将电脑连接 Wi-Fi 或网线'},status=503)
        address=body.get('ip',addresses[0]['ip'])
        if address not in {x['ip'] for x in addresses}:raise ValueError('无效局域网地址')
        await self.ensure_listener()
        return web.json_response(self.mint(address,addresses))

    async def session_status(self,request):
        session=self.sessions.get(request.match_info['id'])
        if not session:raise web.HTTPNotFound()
        status=session['status'] if session['expires']>time.time() else 'expired'
        return web.json_response({'status':status,'item':session['item'],'expires':session['expires']})

    async def ensure_listener(self):
        if self.runner:return
        runner=web.AppRunner(self.create_upload_app(),access_log=None)
        await runner.setup()
        try:await web.TCPSite(runner,'0.0.0.0',7801).start()
        except Exception:
            await runner.cleanup()
            raise ValueError('手机上传端口 7801 无法启动，请检查是否被占用')
        self.runner=runner

    async def close(self,*_):
        if self.runner:await self.runner.cleanup()
        self.sessions.clear()

    @web.middleware
    async def boundary(self,request,handler):
        try:
            hostname=request.host.rsplit(':',1)[0]
            if hostname not in self.allowed_hosts:raise web.HTTPForbidden()
            if request.method=='POST' and request.headers.get('Origin') not in {None,'http://'+request.host}:raise web.HTTPForbidden()
            response=await handler(request)
        except (ValueError,UnicodeError) as exc:response=web.json_response({'error':str(exc)},status=400)
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response

    async def page(self,request):
        name=request.match_info.get('name','mobile.html')
        if name not in {'mobile.html','mobile.css','mobile.js'}:raise web.HTTPNotFound()
        return web.FileResponse(self.web_dir/name)

    async def upload(self,request):
        token=request.headers.get('X-Upload-Token','')
        digest=token_hash(token)
        session=next((x for x in self.sessions.values() if secrets.compare_digest(x['hash'],digest)),None)
        if not session or session['expires']<=time.time() or session['status']!='waiting':
            return web.json_response({'error':'二维码已失效、已使用或已撤销，请在电脑上重新生成'},status=403)
        session['status']='uploading'
        try:
            reader=await request.multipart()
            field=await reader.next()
            if not field or field.name!='image':raise ValueError('请选择人物照片')
            data=bytearray()
            while chunk:=await field.read_chunk(65536):
                data.extend(chunk)
                if len(data)>self.max_upload:return web.json_response({'error':'照片不能超过 20MB'},status=413)
            if await reader.next() is not None:raise ValueError('一次仅可上传一张照片')
            if not data:raise ValueError('照片不能为空')
            name=Path(unquote(field.filename or '手机人物').replace('\\','/')).stem[:60]
            item=self.on_upload(data,name)
            session.update(status='uploaded',item=item)
            return web.json_response({'ok':True},status=201)
        finally:
            if session['status']=='uploading':session['status']='waiting'

    def create_upload_app(self):
        app=web.Application(middlewares=[self.boundary],client_max_size=self.max_upload+65536)
        app.add_routes([web.get('/',self.page),web.get('/{name}',self.page),web.post('/api/upload',self.upload)])
        return app

def register_mobile(app,on_upload,web_dir):
    mobile=MobileUploads(on_upload,web_dir)
    app['mobile']=mobile
    app.on_cleanup.append(mobile.close)
    app.router.add_post('/api/mobile-session',mobile.new_session)
    app.router.add_get('/api/mobile-session/{id}',mobile.session_status)
    return mobile
