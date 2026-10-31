import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from aiohttp.test_utils import TestClient,TestServer
from PIL import Image

import app as studio
from mobile import MobileUploads

class MobileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_root=studio.ROOT
        studio.ROOT=Path(self.temp.name)
        self.state={'uploads':[],'items':{}}
        self.manager=MobileUploads(lambda data,name:studio.public_item(studio.store_upload(self.state,data,'character',name)),studio.ROOT)
        self.addresses=[{'name':'Wi-Fi','ip':'192.168.1.73','rank':0}]
        self.session=self.manager.mint('192.168.1.73',self.addresses)
        self.token=urlsplit(self.session['url']).fragment
        self.client=TestClient(TestServer(self.manager.create_upload_app()),headers={'Host':'192.168.1.73:7801'})
        await self.client.start_server()
        buffer=io.BytesIO();Image.new('RGB',(48,64),'navy').save(buffer,format='PNG');self.image=buffer.getvalue()

    async def asyncTearDown(self):
        await self.client.close()
        studio.ROOT=self.old_root
        self.temp.cleanup()

    def form(self):
        form=aiohttp.FormData();form.add_field('image',self.image,filename='phone.png',content_type='image/png');return form

    async def test_qr_fragment_token_and_single_use_upload(self):
        self.assertEqual(len(self.token),32)
        self.assertEqual(urlsplit(self.session['url']).query,'')
        self.assertNotIn(self.token,json.dumps(self.manager.sessions))
        response=await self.client.post('/api/upload',data=self.form(),headers={'X-Upload-Token':self.token})
        self.assertEqual(response.status,201,await response.text())
        session=self.manager.sessions[self.session['id']]
        self.assertEqual(session['status'],'uploaded')
        self.assertEqual(len(self.state['uploads']),1)
        self.assertEqual(self.state['uploads'][0]['kind'],'character')
        response=await self.client.post('/api/upload',data=self.form(),headers={'X-Upload-Token':self.token})
        self.assertEqual(response.status,403)
        self.assertEqual(len(self.state['uploads']),1)

    async def test_expired_or_invalid_token_cannot_write(self):
        for token in ['', 'wrong-token',self.token]:
            if token==self.token:self.manager.sessions[self.session['id']]['expires']=time.time()-1
            response=await self.client.post('/api/upload',data=self.form(),headers={'X-Upload-Token':token})
            self.assertEqual(response.status,403)
        self.assertEqual(self.state['uploads'],[])
        self.assertFalse((studio.ROOT/'data').exists())

    async def test_new_qr_revokes_previous_code(self):
        self.manager.mint('192.168.1.73',self.addresses)
        response=await self.client.post('/api/upload',data=self.form(),headers={'X-Upload-Token':self.token})
        self.assertEqual(response.status,403)
        self.assertEqual(self.state['uploads'],[])

    async def test_lan_surface_has_no_library_or_generation_access(self):
        for route in ['/api/status','/api/catalog','/api/history','/media/person','/api/generate']:
            response=await self.client.get(route)
            self.assertEqual(response.status,404,route)

    async def test_foreign_host_and_origin_denied(self):
        response=await self.client.get('/',headers={'Host':'foreign.example:7801'})
        self.assertEqual(response.status,403)
        response=await self.client.post('/api/upload',data=self.form(),headers={'X-Upload-Token':self.token,'Origin':'https://foreign.example'})
        self.assertEqual(response.status,403)
        self.assertEqual(self.state['uploads'],[])

    async def test_oversized_upload_is_denied_and_can_retry(self):
        self.manager.max_upload=32
        response=await self.client.post('/api/upload',data=self.form(),headers={'X-Upload-Token':self.token})
        self.assertEqual(response.status,413)
        self.assertEqual(self.manager.sessions[self.session['id']]['status'],'waiting')
        self.assertEqual(self.state['uploads'],[])

if __name__=='__main__':unittest.main()
