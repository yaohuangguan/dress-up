import unittest
import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
import remote_gateway as module

class RemoteGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_studio=module.LOCAL_STUDIO;self.old_phone=module.LOCAL_PHONE
        self.calls=[]
        async def upstream(request):
            self.calls.append({'path':request.path,'host':request.host,'origin':request.headers.get('Origin'),'authorization':request.headers.get('Authorization'),'body':await request.read(),'local':request.headers.get('X-Local-Look')})
            if request.path=='/api/mobile-session':return web.json_response({'id':'one','url':'http://192.168.1.10:7801/#'+'A'*32,'qr':'old'})
            return web.json_response({'ok':True})
        studio=web.Application();studio.router.add_route('*','/{path:.*}',upstream)
        self.studio=TestServer(studio);await self.studio.start_server();module.LOCAL_STUDIO=str(self.studio.make_url('')).rstrip('/')
        async def phone(request):
            if request.path=='/':return web.Response(body=b'<link href="/mobile.css"><script src="/mobile.js"></script>',content_type='text/html')
            return web.Response(body=b"fetch('/api/upload', {method:'POST'})",content_type='application/javascript')
        app=web.Application();app.router.add_route('*','/{path:.*}',phone)
        self.phone=TestServer(app);await self.phone.start_server();module.LOCAL_PHONE=str(self.phone.make_url('')).rstrip('/')
        self.public='https://studio-test.trycloudflare.com'
        self.credentials={'username':'owner','password':'test-canary-not-a-real-password'}
        self.gateway=module.Gateway(self.credentials,self.public)
        self.client=TestClient(TestServer(self.gateway.app()),headers={'Host':'studio-test.trycloudflare.com'})
        await self.client.start_server()
        self.auth={'Authorization':aiohttp.BasicAuth(**{'login':self.credentials['username'],'password':self.credentials['password']}).encode()}

    async def asyncTearDown(self):
        await self.client.close();await self.studio.close();await self.phone.close()
        module.LOCAL_STUDIO=self.old_studio;module.LOCAL_PHONE=self.old_phone

    async def test_private_pages_and_apis_require_login(self):
        for path in ['/','/api/history','/api/status','/media/person','/results/private.png','/videos/private.mp4','/api/video/status','/api/video/jobs/private','/api/video/script/private','/phone/']:
            response=await self.client.get(path)
            self.assertEqual(response.status,401)
            self.assertIn('Basic realm=',response.headers['WWW-Authenticate'])
            self.assertNotIn(self.credentials['password'],await response.text())
        self.assertEqual(self.calls,[])

    async def test_invalid_credentials_do_not_reach_local_service(self):
        for value in ['Bearer wrong','Basic !!!',aiohttp.BasicAuth('owner','wrong').encode()]:
            response=await self.client.get('/api/history',headers={'Authorization':value})
            self.assertEqual(response.status,401)
        self.assertEqual(self.calls,[])

    async def test_login_rate_limit(self):
        for _ in range(10):self.assertEqual((await self.client.get('/')).status,401)
        self.assertEqual((await self.client.get('/',headers=self.auth)).status,429)
        self.assertEqual(self.calls,[])

    async def test_authenticated_proxy_does_not_forward_credentials(self):
        response=await self.client.get('/api/catalog?kind=character',headers=self.auth)
        self.assertEqual(response.status,200)
        self.assertEqual(await response.json(),{'ok':True})
        self.assertIsNone(self.calls[0]['authorization'])
        self.assertEqual(self.calls[0]['local'],'1')
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')

    async def test_video_is_not_transferred_by_public_tunnel(self):
        response=await self.client.get('/videos/private.mp4',headers=self.auth)
        self.assertEqual(response.status,403)
        self.assertEqual(self.calls,[])

    async def test_host_and_foreign_origin_denied(self):
        response=await self.client.get('/',headers={**self.auth,'Host':'attacker.example'})
        self.assertEqual(response.status,403)
        response=await self.client.post('/api/uploads',headers={**self.auth,'Origin':'https://attacker.example'},data=b'no')
        self.assertEqual(response.status,403)
        self.assertEqual(self.calls,[])

    async def test_same_origin_post_preserves_body_and_maps_local_origin(self):
        response=await self.client.post('/api/uploads',headers={**self.auth,'Origin':self.public},data=b'image-data')
        self.assertEqual(response.status,200)
        self.assertEqual(self.calls[0]['body'],b'image-data')
        self.assertEqual(self.calls[0]['origin'],module.LOCAL_STUDIO)

    async def test_remote_qr_uses_https_phone_page(self):
        response=await self.client.post('/api/mobile-session',headers={**self.auth,'Origin':self.public},json={})
        self.assertEqual(response.status,200)
        data=await response.json()
        self.assertEqual(data['url'],self.public+'/phone/#'+'A'*32)
        self.assertTrue(data['qr'].startswith('data:image/png;base64,iVBOR'))

    async def test_phone_page_paths_stay_inside_remote_entry(self):
        response=await self.client.get('/phone/',headers=self.auth)
        self.assertEqual(response.status,200)
        self.assertIn('/phone/mobile.css',await response.text())
        response=await self.client.get('/phone/mobile.js',headers=self.auth)
        self.assertIn("fetch('/phone/api/upload'",await response.text())
        response=await self.client.get('/phone/api/history',headers=self.auth)
        self.assertEqual(response.status,404)

if __name__=='__main__':unittest.main()
