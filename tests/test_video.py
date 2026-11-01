import asyncio
import json
import time
import unittest
from pathlib import Path

from aiohttp import web
import test_app
import video_engine
from video_workflow import build_video_workflow
from story_writer import validate_script

class VideoTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_app.StudioTests.asyncSetUp
    asyncTearDown=test_app.StudioTests.asyncTearDown
    system=test_app.StudioTests.system
    provider_upload=test_app.StudioTests.provider_upload
    websocket=test_app.StudioTests.websocket
    prompt=test_app.StudioTests.prompt

    async def provider_history(self,request):
        return web.json_response({'test-prompt':{'outputs':{'15':{'images':[{'filename':'film.mp4','subfolder':'LocalLookStudio','type':'output'}]}}}})

    async def provider_view(self,request):
        self.assertEqual(dict(request.query),{'filename':'film.mp4','subfolder':'LocalLookStudio','type':'output'})
        return web.Response(body=(Path(__file__).parent/'fixtures/tiny-video.mp4').read_bytes(),content_type='video/mp4')

    async def test_video_source_cannot_be_url_or_path(self):
        for body in [{'source_job':'../../secret'},{'source_asset':'https://example.com/private'},{'source_job':[]},[]]:
            response=await self.client.post('/api/video/generate',json=body)
            self.assertEqual(response.status,400)
        self.assertEqual(self.prompts,[])
        self.assertEqual(self.application['video_jobs'],{})

    async def test_invalid_story_and_motion_have_no_side_effects(self):
        for extra in [{'motion':'x'*2501},{'motion':12},{'motion':'x','frames':999999},{'motion':'x','mode':'story','template':'missing'},{'motion':'x','mode':'story','template':'tomorrow','scenes':[]}]:
            response=await self.client.post('/api/video/generate',json={'source_asset':'character-one',**extra})
            self.assertEqual(response.status,400)
        self.assertEqual(self.prompts,[])
        self.assertFalse((self.application['video_root']/'data/video_jobs').exists())

    async def test_shared_gpu_busy_denies_video_and_script(self):
        self.application['active']='an-image-job'
        for url,body in [('/api/video/generate',{'source_asset':'character-one','motion':'Natural motion'}),('/api/video/script',{'idea':'Suspense'})]:
            response=await self.client.post(url,json=body)
            self.assertEqual(response.status,409)
        self.assertEqual(self.prompts,[])

    async def test_story_narration_boundary_before_model_access(self):
        for length,status in [(45,503),(46,400)]:
            scenes=[{'title':'来信','narration':'我'*length,'visual':'A woman in a cafe.','motion':'Slow camera push.'} for _ in range(8)]
            response=await self.client.post('/api/video/generate',json={'source_asset':'character-one','motion':'Natural movement','mode':'story','template':'tomorrow','scenes':scenes})
            self.assertEqual(response.status,status)
        self.assertEqual(self.prompts,[])
        self.assertEqual(self.application['video_jobs'],{})

    async def test_video_routes_reject_foreign_origin(self):
        for url in ['/api/video/generate','/api/video/script']:
            response=await self.client.post(url,json={'idea':'test'},headers={'Origin':'https://attacker.example'})
            self.assertEqual(response.status,403)
        self.assertEqual(self.prompts,[])

    async def test_real_worker_stores_mp4_and_serves_ranges(self):
        app=self.application
        job={'id':'video-one','kind':'video','mode':'clip','created':time.time(),'seed':42,'motion':'The person blinks naturally.','frames':73,'status':'queued'}
        app['active']=job['id']
        await video_engine.run(app,job,app['video_root']/'data/reference.png')
        self.assertEqual(job['status'],'completed',job.get('message'))
        self.assertEqual(len(self.prompts),1)
        self.assertEqual(len(self.uploads),1)
        self.assertEqual(self.prompts[0]['7']['inputs']['length'],73)
        self.assertIsNone(app['active'])
        stored=json.loads((app['video_root']/'data/video_jobs/video-one.json').read_text(encoding='utf8'))
        self.assertEqual(stored['video'],'/videos/video-one.mp4')
        self.assertEqual(stored['dimensions'],[64,64])
        response=await self.client.get(stored['video'],headers={'Range':'bytes=0-31'})
        self.assertEqual(response.status,206)
        self.assertEqual(len(await response.read()),32)
        self.assertIn('no-store',response.headers['Cache-Control'])
        response=await self.client.get('/videos/missing.mp4');self.assertEqual(response.status,404)

class VideoContractTests(unittest.TestCase):
    def test_native_required_inputs_and_first_frame_condition(self):
        graph=build_video_workflow('start.png','A person looks up.',42,frames=193)
        contract=json.loads((Path(__file__).parent/'fixtures/video-node-inputs.json').read_text(encoding='utf8'))
        for key,node in graph.items():
            if node['class_type'] in contract:
                self.assertFalse(set(contract[node['class_type']])-set(node['inputs']),key)
        self.assertEqual(graph['7']['inputs']['image'],['6',0])
        self.assertEqual(graph['7']['inputs']['length'],193)
        self.assertEqual(graph['14']['inputs']['fps'],24.0)
        self.assertGreater(8*193/24,60)

    def test_writer_rejects_malformed_or_unbounded_story(self):
        for value in [{},[],{'title':'test','logline':'x','scenes':[]},{'title':'test','logline':'x','scenes':[{'title':'x','narration':'x'*46,'visual':'x','motion':'x'}]*8}]:
            with self.assertRaises(ValueError):validate_script(value)

    def test_writer_requires_english_visuals_for_video_model(self):
        story={'title':'深夜','logline':'悬疑故事','scenes':[{'title':'来信','narration':'一条短信亮起。','visual':'昏暗的咖啡馆，窗外下着雨。','motion':'缓慢推近镜头。'} for _ in range(8)]}
        with self.assertRaisesRegex(ValueError,'英文'):validate_script(story)

if __name__=='__main__':unittest.main()
