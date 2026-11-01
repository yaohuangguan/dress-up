"""Authenticated HTTPS tunnel entry. ComfyUI remains private on loopback."""
import base64
import hmac
import io
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
import qrcode
from aiohttp import web

ROOT=Path(__file__).resolve().parent
LOCAL_STUDIO='http://127.0.0.1:7800'
LOCAL_PHONE='http://127.0.0.1:7801'
PRIVATE=ROOT/'data/remote'
HOP_HEADERS={'connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade','content-length','content-encoding','host','authorization','cookie'}

def private_json(name,default):
    file=PRIVATE/name
    return json.loads(file.read_text(encoding='utf8')) if file.exists() else default

class Gateway:
    def __init__(self,credentials,public_url=None):
        self.credentials=credentials
        self.public_url=public_url
        self.client=None
        self.failures={}

    def url(self):
        return self.public_url or private_json('state.json',{}).get('url','')

    @web.middleware
    async def guard(self,request,handler):
        public=self.url()
        remote_host=urlsplit(public).netloc if public else ''
        allowed={'127.0.0.1:7802','localhost:7802'}
        if remote_host:allowed.add(remote_host)
        if request.host not in allowed:raise web.HTTPForbidden(text='Invalid host')
        if request.method not in {'GET','HEAD'} and request.headers.get('Origin') not in {None,public,'http://127.0.0.1:7802','http://localhost:7802'}:raise web.HTTPForbidden(text='Invalid origin')
        # Cloudflare overwrites this header; direct loopback callers receive their own bucket.
        address=request.headers.get('CF-Connecting-IP') or request.remote or 'local'
        cutoff=time.monotonic()-300
        failures=[stamp for stamp in self.failures.get(address,[]) if stamp>cutoff]
        if len(failures)>=10:return web.Response(status=429,text='Too many login attempts. Try again in five minutes.',headers={'Retry-After':'300','Cache-Control':'no-store'})
        valid=False
        try:
            auth=aiohttp.BasicAuth.decode(request.headers.get('Authorization',''))
            valid=hmac.compare_digest(auth.login.encode(),self.credentials['username'].encode()) and hmac.compare_digest(auth.password.encode(),self.credentials['password'].encode())
        except (ValueError,UnicodeError):pass
        if not valid:
            self.failures[address]=failures+[time.monotonic()]
            if len(self.failures)>4096:self.failures={key:values for key,values in self.failures.items() if values and values[-1]>cutoff}
            return web.Response(status=401,text='Sign in to your private Local Look Studio.',headers={'WWW-Authenticate':'Basic realm="Local Look Studio", charset="UTF-8"','Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        response=await handler(request)
        response.headers['Cache-Control']='private, no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    async def proxy(self,request):
        if request.path.startswith('/videos/'):
            return web.Response(status=403,text='Video playback is available in the local studio. Public video delivery is not enabled.',headers={'Cache-Control':'no-store'})
        phone=request.path=='/phone' or request.path.startswith('/phone/')
        path=request.path[len('/phone'):] if phone else request.path
        path=path or '/'
        base=LOCAL_PHONE if phone else LOCAL_STUDIO
        # Do not turn the gateway into an arbitrary proxy.
        if phone and (request.method,path) not in {('GET','/'),('GET','/mobile.js'),('GET','/mobile.css'),('POST','/api/upload')}:
            raise web.HTTPNotFound()
        if request.content_length and request.content_length>21*1024*1024:raise web.HTTPRequestEntityTooLarge(max_size=21*1024*1024,actual_size=request.content_length)
        body=await request.read() if request.can_read_body else None
        headers={key:value for key,value in request.headers.items() if key.lower() not in HOP_HEADERS and not key.lower().startswith('cf-') and not key.lower().startswith('x-forwarded-')}
        headers['Host']=urlsplit(base).netloc
        if 'Origin' in headers:headers['Origin']=base
        if not phone:headers['X-Local-Look']='1'
        url=base+path+('?' + request.query_string if request.query_string else '')
        try:
            async with self.client.request(request.method,url,headers=headers,data=body,allow_redirects=False,timeout=aiohttp.ClientTimeout(total=40)) as upstream:
                payload=await upstream.read()
                result_headers={key:value for key,value in upstream.headers.items() if key.lower() not in HOP_HEADERS}
                result_headers.pop('ETag',None)
                if request.path=='/api/mobile-session' and request.method=='POST' and upstream.status==200:
                    data=json.loads(payload)
                    token=urlsplit(data['url']).fragment
                    data['url']=self.url()+'/phone/#'+token
                    image=io.BytesIO();qrcode.make(data['url']).save(image,format='PNG')
                    data['qr']='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
                    payload=json.dumps(data).encode()
                elif phone and path=='/':
                    payload=payload.replace(b'href="/mobile.css"',b'href="/phone/mobile.css"').replace(b'src="/mobile.js"',b'src="/phone/mobile.js"')
                elif phone and path=='/mobile.js':payload=payload.replace(b"fetch('/api/upload'",b"fetch('/phone/api/upload'")
                return web.Response(body=payload,status=upstream.status,headers=result_headers)
        except (aiohttp.ClientError,TimeoutError):
            return web.Response(status=502,text='The local studio is unavailable. Start it on your computer.')

    async def lifecycle(self,app):
        async with aiohttp.ClientSession() as client:
            self.client=client
            yield

    def app(self):
        app=web.Application(middlewares=[self.guard],client_max_size=21*1024*1024)
        app.cleanup_ctx.append(self.lifecycle)
        app.router.add_route('*','/{path:.*}',self.proxy)
        return app

if __name__=='__main__':
    credentials=private_json('credentials.json',{})
    if not credentials.get('username') or not credentials.get('password'):raise SystemExit('Run remote_access.py first.')
    logging.basicConfig(level=logging.WARNING)
    web.run_app(Gateway(credentials).app(),host='127.0.0.1',port=7802,access_log=None,print=None)
