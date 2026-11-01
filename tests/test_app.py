import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

import app as studio
from workflow import build_workflow


class StudioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_root=studio.ROOT
        self.old_comfy=studio.COMFY_URL
        studio.ROOT=Path(self.temp.name)
        root=studio.ROOT
        (root/'data').mkdir()
        buffer=io.BytesIO()
        Image.new('RGB',(40,60),'#aabbcc').save(buffer,format='PNG')
        self.png=buffer.getvalue()
        (root/'data/reference.png').write_bytes(self.png)
        self.items=[{'id':kind+'-one','kind':kind,'code':'ONE','name':kind,'category':'测试','tags':'white 白色','prompt':'','path':'data/reference.png','thumb':'data/reference.png'} for kind in ['character','outfit','pose']]
        (root/'data/catalog.json').write_text(json.dumps(self.items),encoding='utf8')
        for folder,name in [('diffusion_models','flux-2-klein-4b-fp8.safetensors'),('diffusion_models','flux-2-klein-base-4b-fp8.safetensors'),('text_encoders','qwen_3_4b.safetensors'),('vae','flux2-vae.safetensors')]:
            file=root/'runtime/ComfyUI/models'/folder/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(b'test fake provider only')
        self.uploads=[]
        self.prompts=[]
        self.ws=None
        self.ready=asyncio.Event()
        fake=web.Application()
        fake.add_routes([web.get('/system_stats',self.system),web.post('/upload/image',self.provider_upload),web.get('/ws',self.websocket),web.post('/prompt',self.prompt),web.get('/history/test-prompt',self.provider_history),web.get('/view',self.provider_view)])
        self.provider=TestServer(fake)
        await self.provider.start_server()
        studio.COMFY_URL=str(self.provider.make_url('')).rstrip('/')
        self.application=studio.create_app()
        self.client=TestClient(TestServer(self.application),headers={'Host':'127.0.0.1:7800','X-Local-Look':'1'})
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.provider.close()
        studio.ROOT=self.old_root
        studio.COMFY_URL=self.old_comfy
        self.temp.cleanup()

    async def system(self,request):return web.json_response({'devices':[{'type':'cuda','name':'fake GPU'}]})

    async def provider_upload(self,request):
        data=await request.post()
        self.assertEqual(set(data),{'image','type','subfolder'})
        self.assertEqual(data['type'],'input')
        image=data['image']
        raw=image.file.read()
        self.assertTrue(raw.startswith(b'\x89PNG'))
        self.uploads.append(image.filename)
        return web.json_response({'name':image.filename,'subfolder':'LocalLookStudio','type':'input'})

    async def websocket(self,request):
        self.ws=web.WebSocketResponse()
        await self.ws.prepare(request)
        async for _ in self.ws:pass
        return self.ws

    async def prompt(self,request):
        body=await request.json()
        self.assertEqual(set(body),{'prompt','client_id'})
        self.prompts.append(body['prompt'])
        for kind,data in [('executing',{'node':'11'}),('progress',{'value':4,'max':4}),('execution_success',{})]:
            await self.ws.send_json({'type':kind,'data':{'prompt_id':'test-prompt',**data}})
        return web.json_response({'prompt_id':'test-prompt','number':0,'node_errors':{}})

    async def provider_history(self,request):return web.json_response({'test-prompt':{'outputs':{'13':{'images':[{'filename':'look.png','subfolder':'LocalLookStudio','type':'output'}]}}}})

    async def provider_view(self,request):
        self.assertEqual(dict(request.query),{'filename':'look.png','subfolder':'LocalLookStudio','type':'output'})
        return web.Response(body=self.png,content_type='image/png')

    def generation(self):return {'character':'character-one','outfit':'outfit-one','pose':'pose-one','seed':42}

    async def test_catalog_search_and_pagination(self):
        response=await self.client.get('/api/catalog?kind=outfit&q=%E7%99%BD%E8%89%B2')
        data=await response.json()
        self.assertEqual(data['total'],1)
        self.assertEqual(data['items'][0]['id'],'outfit-one')
        self.assertNotIn('path',data['items'][0])
        response=await self.client.get('/api/catalog?kind=pose&page=2')
        self.assertEqual((await response.json())['items'],[])

    async def test_dns_rebinding_host_denied(self):
        response=await self.client.get('/api/catalog',headers={'Host':'malicious.example'})
        self.assertEqual(response.status,403)

    async def test_foreign_origin_denied_without_side_effects(self):
        response=await self.client.post('/api/generate',json=self.generation(),headers={'Origin':'https://malicious.example'})
        self.assertEqual(response.status,403)
        self.assertEqual(self.prompts,[])
        self.assertEqual(self.application['jobs'],{})

    async def test_invalid_selection_never_calls_provider(self):
        for body in [[],{},dict(self.generation(),character='outfit-one'),dict(self.generation(),seed=True),dict(self.generation(),seed=-1),dict(self.generation(),angle='../../'),dict(self.generation(),size='4096'),dict(self.generation(),prompt='a'*1501)]:
            response=await self.client.post('/api/generate',json=body)
            self.assertEqual(response.status,400,body)
        self.assertEqual(self.prompts,[])
        self.assertEqual(self.application['jobs'],{})

    async def test_missing_view_denied(self):
        self.application['items']['pose-one']['views']={'front':'data/reference.png'}
        response=await self.client.post('/api/generate',json=dict(self.generation(),angle='side'))
        self.assertEqual(response.status,400)
        self.assertEqual(self.prompts,[])

    async def test_media_traversal_and_private_files_denied(self):
        for path in ['/media/missing','/data/catalog.json','/..%2Fapp.py','/results/missing.png']:
            response=await self.client.get(path)
            self.assertEqual(response.status,404,path)
        bad=dict(self.items[0],path='../outside.png',thumb='../outside.png')
        self.application['items']['bad']=bad
        self.assertEqual((await self.client.get('/media/bad')).status,404)

    async def test_upload_reencodes_and_persists(self):
        form=aiohttp.FormData()
        form.add_field('kind','character')
        form.add_field('image',self.png,filename='../../my-face.png',content_type='image/png')
        response=await self.client.post('/api/uploads',data=form)
        self.assertEqual(response.status,201)
        item=await response.json()
        self.assertEqual(item['name'],'my-face')
        saved=json.loads((studio.ROOT/'data/uploads.json').read_text(encoding='utf8'))
        self.assertEqual(saved[0]['id'],item['id'])
        file=studio.ROOT/saved[0]['path']
        with Image.open(file) as image:self.assertEqual(image.size,(40,60))
        self.assertEqual((await self.client.get(item['image'])).status,200)

    async def test_fake_image_denied_without_writes(self):
        form=aiohttp.FormData()
        form.add_field('kind','character')
        form.add_field('image',b'<svg><script>alert(1)</script></svg>',filename='fake.png',content_type='image/png')
        response=await self.client.post('/api/uploads',data=form)
        self.assertEqual(response.status,400)
        self.assertFalse((studio.ROOT/'data/uploads.json').exists())
        self.assertFalse((studio.ROOT/'data/uploads').exists())

    async def test_complete_three_reference_pipeline(self):
        response=await self.client.post('/api/generate',json=self.generation())
        self.assertEqual(response.status,202,await response.text())
        job=await response.json()
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        response=await self.client.get('/api/jobs/'+job['id'])
        result=await response.json()
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(result['seed'],42)
        self.assertEqual(len(self.uploads),3)
        self.assertEqual(len(self.prompts),1)
        names=[n['inputs']['image'] for n in self.prompts[0].values() if n['class_type']=='LoadImage']
        self.assertEqual(len(set(names)),3)
        self.assertEqual((await self.client.get(result['image'])).status,200)
        self.assertEqual((studio.ROOT/'data/results'/(job['id']+'.png')).read_bytes(),self.png)
        self.assertEqual((await self.client.get('/api/workflow/'+job['id'])).status,200)
        self.assertIsNone(self.application['active'])
        self.assertEqual(len(await (await self.client.get('/api/history')).json()),1)

    async def test_explicit_quality_uses_base_model_and_persists_native_dimensions(self):
        response=await self.client.post('/api/generate',json=dict(self.generation(),quality='quality'))
        self.assertEqual(response.status,202,await response.text())
        job=await response.json()
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        stored=json.loads((studio.ROOT/'data/jobs'/(job['id']+'.json')).read_text(encoding='utf8'))
        self.assertEqual((stored['quality'],stored['width'],stored['height']),('quality',896,1216))
        graph=self.prompts[0]
        self.assertEqual(graph['1']['inputs']['unet_name'],'flux-2-klein-base-4b-fp8.safetensors')
        self.assertEqual(graph['8']['inputs']['steps'],50)
        self.assertEqual(graph['10']['inputs']['cfg'],4.0)
        self.assertEqual((graph['9']['inputs']['width'],graph['9']['inputs']['height']),(896,1216))

    async def test_fast_mode_does_not_require_base_weights(self):
        (studio.ROOT/'runtime/ComfyUI/models/diffusion_models/flux-2-klein-base-4b-fp8.safetensors').unlink()
        response=await self.client.post('/api/generate',json=self.generation())
        self.assertEqual(response.status,202,await response.text())
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        self.assertEqual(self.prompts[0]['8']['inputs']['steps'],4)
        self.assertEqual(self.prompts[0]['10']['inputs']['cfg'],1.0)
        self.assertEqual(self.prompts[0]['9']['inputs']['width'],640)

    async def test_missing_quality_weights_does_not_silently_use_fast_model(self):
        (studio.ROOT/'runtime/ComfyUI/models/diffusion_models/flux-2-klein-base-4b-fp8.safetensors').unlink()
        response=await self.client.post('/api/generate',json=dict(self.generation(),quality='quality'))
        self.assertEqual(response.status,503)
        self.assertEqual(self.prompts,[])
        self.assertEqual(self.application['jobs'],{})

    async def test_invalid_quality_rejected_before_writes(self):
        for quality in ['ultra',None,[],{},True]:
            response=await self.client.post('/api/generate',json=dict(self.generation(),quality=quality))
            self.assertEqual(response.status,400,quality)
        self.assertEqual(self.prompts,[])
        self.assertEqual(self.application['jobs'],{})

    async def test_uploaded_hairstyle_is_browsable_and_used_as_reference(self):
        form=aiohttp.FormData()
        form.add_field('kind','hairstyle')
        form.add_field('image',self.png,filename='my-hair.png',content_type='image/png')
        response=await self.client.post('/api/uploads',data=form)
        self.assertEqual(response.status,201,await response.text())
        item=await response.json()
        response=await self.client.get('/api/catalog?kind=hairstyle')
        self.assertEqual((await response.json())['items'][0]['id'],item['id'])
        response=await self.client.post('/api/generate',json=dict(self.generation(),hairstyle=item['id']))
        self.assertEqual(response.status,202,await response.text())
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        self.assertEqual(len(self.uploads),4)
        self.assertIn('-hairstyle.png',self.prompts[0]['35']['inputs']['image'])

    async def test_named_hairstyle_changes_hair_without_an_extra_face_reference(self):
        self.application['items']['hairstyle-one']={**self.items[0],'id':'hairstyle-one','kind':'hairstyle','prompt':'short bob with wispy bangs','reference_mode':'description'}
        response=await self.client.post('/api/generate',json=dict(self.generation(),hairstyle='hairstyle-one',hairstyle_description='keep black hair'))
        self.assertEqual(response.status,202,await response.text())
        job=await response.json()
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        self.assertEqual(len(self.uploads),3)
        text=self.prompts[0]['4']['inputs']['text']
        self.assertIn('short bob with wispy bangs',text)
        self.assertIn('keep black hair',text)
        self.assertNotIn('Preserve the hairstyle and hair color',text)
        saved=json.loads((studio.ROOT/'data/jobs'/(job['id']+'.json')).read_text(encoding='utf8'))
        self.assertEqual(saved['selection']['hairstyle']['id'],'hairstyle-one')
        self.assertEqual(saved['hairstyle_description'],'keep black hair')

    async def test_uploaded_hairstyle_is_fifth_reference_after_background(self):
        for kind in ['background','hairstyle']:
            self.application['items'][kind+'-one']={**self.items[0],'id':kind+'-one','kind':kind}
        response=await self.client.post('/api/generate',json=dict(self.generation(),background='background-one',hairstyle='hairstyle-one',quality='quality'))
        self.assertEqual(response.status,202,await response.text())
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        graph=self.prompts[0]
        self.assertEqual(len(self.uploads),5)
        self.assertIn('-background.png',graph['35']['inputs']['image'])
        self.assertIn('-hairstyle.png',graph['hair-25']['inputs']['image'])
        text=graph['4']['inputs']['text']
        self.assertIn('image 4 as the background',text)
        self.assertNotIn('image 5',text)
        self.assertEqual(graph['hair-21']['inputs']['image'],['12',0])
        self.assertIn('hair in image 2',graph['hair-4']['inputs']['text'])
        self.assertNotIn('13',graph)
        self.assertEqual(sum(node['class_type']=='SamplerCustomAdvanced' for node in graph.values()),2)

    async def test_hairstyle_image_without_background_keeps_studio_location(self):
        self.application['items']['hairstyle-one']={**self.items[0],'id':'hairstyle-one','kind':'hairstyle'}
        response=await self.client.post('/api/generate',json=dict(self.generation(),hairstyle='hairstyle-one'))
        self.assertEqual(response.status,202,await response.text())
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        text=self.prompts[0]['4']['inputs']['text']
        self.assertIn('image 4 for hair',text)
        self.assertIn('Use a clean professional studio background',text)
        self.assertNotIn('image 4 as the background',text)

    async def test_fast_five_selection_uses_four_steps_per_pass(self):
        for kind in ['background','hairstyle']:
            self.application['items'][kind+'-one']={**self.items[0],'id':kind+'-one','kind':kind}
        response=await self.client.post('/api/generate',json=dict(self.generation(),background='background-one',hairstyle='hairstyle-one'))
        self.assertEqual(response.status,202,await response.text())
        job=await response.json()
        self.assertEqual((job['quality'],job['stages']),('fast',2))
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        graph=self.prompts[0]
        self.assertEqual(graph['8']['inputs']['steps'],4)
        self.assertEqual(graph['hair-8']['inputs']['steps'],4)
        self.assertEqual(graph['10']['inputs']['cfg'],1.0)
        self.assertEqual(graph['hair-10']['inputs']['cfg'],1.0)

    async def test_invalid_hairstyle_is_rejected_before_writes(self):
        for body in [dict(self.generation(),hairstyle='character-one'),dict(self.generation(),hairstyle=[]),dict(self.generation(),hairstyle_description='x'*401),dict(self.generation(),hairstyle_description={})]:
            response=await self.client.post('/api/generate',json=body)
            self.assertEqual(response.status,400)
        self.assertEqual(self.prompts,[])
        self.assertEqual(self.application['jobs'],{})

    async def test_gpu_busy_rejected_without_new_job(self):
        self.application['active']='existing-job'
        response=await self.client.post('/api/generate',json=self.generation())
        self.assertEqual(response.status,409)
        self.assertEqual(self.prompts,[])

    async def test_optional_background_image_is_fourth_reference(self):
        self.application['items']['background-one']={'id':'background-one','kind':'background','name':'Cafe','code':'CAFE','category':'室内','path':'data/reference.png','thumb':'data/reference.png','prompt':'a Paris cafe'}
        response=await self.client.post('/api/generate',json=dict(self.generation(),background='background-one',background_description='warm sunset'))
        self.assertEqual(response.status,202)
        job=await response.json()
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        result=await (await self.client.get('/api/jobs/'+job['id'])).json()
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(self.uploads),4)
        graph=self.prompts[0]
        self.assertIn('-background.png',graph['35']['inputs']['image'])
        self.assertIn('image 4',graph['4']['inputs']['text'])
        self.assertIn('warm sunset',graph['4']['inputs']['text'])
        self.assertEqual(result['selection']['background']['id'],'background-one')

    async def test_description_only_keeps_three_references(self):
        response=await self.client.post('/api/generate',json=dict(self.generation(),background_description='a quiet snowy city street'))
        self.assertEqual(response.status,202)
        await asyncio.wait_for(asyncio.gather(*list(self.application['tasks'])),timeout=10)
        self.assertEqual(len(self.uploads),3)
        text=self.prompts[0]['4']['inputs']['text']
        self.assertIn('a quiet snowy city street',text)
        self.assertNotIn('Use a clean professional studio background',text)

    async def test_invalid_background_is_rejected_before_writes(self):
        for body in [dict(self.generation(),background='character-one'),dict(self.generation(),background_description='x'*601),dict(self.generation(),background_description=[])]:
            response=await self.client.post('/api/generate',json=body)
            self.assertEqual(response.status,400)
        self.assertEqual(self.uploads,[])
        self.assertEqual(self.prompts,[])


class WorkflowTests(unittest.TestCase):
    def test_three_ordered_conditions_reach_sampler(self):
        graph=build_workflow(['face.png','outfit.png','pose.png'],'test',7)
        self.assertEqual(graph['20']['inputs']['image'],'face.png')
        self.assertEqual(graph['25']['inputs']['image'],'outfit.png')
        self.assertEqual(graph['30']['inputs']['image'],'pose.png')
        current=graph['10']['inputs']['positive']
        references=[]
        while graph[current[0]]['class_type']=='ReferenceLatent':
            node=graph[current[0]]
            references.append(node['inputs']['latent'])
            current=node['inputs']['conditioning']
        self.assertEqual(references,[['32',0],['27',0],['22',0]])
        self.assertEqual(current,['4',0])
        self.assertEqual(graph['8']['inputs']['steps'],4)
        self.assertEqual(graph['2']['inputs']['device'],'cpu')

if __name__=='__main__':unittest.main()
