"""ComfyUI native FLUX.2 Klein graph; three separate image conditions."""
IMAGE_PROFILES = {
    'fast': {'label':'快速预览', 'model':'flux-2-klein-4b-fp8.safetensors', 'steps':4, 'cfg':1.0,
             'sizes':{'portrait':(640,896), 'square':(768,768), 'large':(768,1024)}, 'reference_mp':0.25},
    'quality': {'label':'精细成片', 'model':'flux-2-klein-base-4b-fp8.safetensors', 'steps':50, 'cfg':4.0,
                'sizes':{'portrait':(896,1216), 'square':(1024,1024), 'large':(1024,1536)}, 'reference_mp':0.5},
}


def build_workflow(images, prompt, seed, width=640, height=896, steps=None, quality='fast'):
    profile=IMAGE_PROFILES[quality]
    steps=profile['steps'] if steps is None else steps
    graph={
        '1':{'class_type':'UNETLoader','inputs':{'unet_name':profile['model'],'weight_dtype':'default'}},
        '2':{'class_type':'CLIPLoader','inputs':{'clip_name':'qwen_3_4b.safetensors','type':'flux2','device':'cpu'}},
        '3':{'class_type':'VAELoader','inputs':{'vae_name':'flux2-vae.safetensors'}},
        '4':{'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':prompt}},
        '5':({'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':''}} if quality=='quality' else {'class_type':'ConditioningZeroOut','inputs':{'conditioning':['4',0]}}),
        '6':{'class_type':'RandomNoise','inputs':{'noise_seed':seed}},
        '7':{'class_type':'KSamplerSelect','inputs':{'sampler_name':'euler'}},
        '8':{'class_type':'Flux2Scheduler','inputs':{'steps':steps,'width':width,'height':height}},
        '9':{'class_type':'EmptyFlux2LatentImage','inputs':{'width':width,'height':height,'batch_size':1}},
    }
    positive=['4',0]
    negative=['5',0]
    for index,image in enumerate(images):
        node=20+index*5
        graph[str(node)]={'class_type':'LoadImage','inputs':{'image':image}}
        graph[str(node+1)]={'class_type':'ImageScaleToTotalPixels','inputs':{'image':[str(node),0],'upscale_method':'lanczos','megapixels':profile['reference_mp'] if index!=2 else 0.25,'resolution_steps':16}}
        graph[str(node+2)]={'class_type':'VAEEncode','inputs':{'pixels':[str(node+1),0],'vae':['3',0]}}
        graph[str(node+3)]={'class_type':'ReferenceLatent','inputs':{'conditioning':positive,'latent':[str(node+2),0]}}
        graph[str(node+4)]={'class_type':'ReferenceLatent','inputs':{'conditioning':negative,'latent':[str(node+2),0]}}
        positive=[str(node+3),0]
        negative=[str(node+4),0]
    graph.update({
        '10':{'class_type':'CFGGuider','inputs':{'model':['1',0],'positive':positive,'negative':negative,'cfg':profile['cfg']}},
        '11':{'class_type':'SamplerCustomAdvanced','inputs':{'noise':['6',0],'guider':['10',0],'sampler':['7',0],'sigmas':['8',0],'latent_image':['9',0]}},
        '12':{'class_type':'VAEDecodeTiled','inputs':{'samples':['11',0],'vae':['3',0],'tile_size':512,'overlap':64,'temporal_size':64,'temporal_overlap':8}},
        '13':{'class_type':'SaveImage','inputs':{'images':['12',0],'filename_prefix':'LocalLookStudio/look'}},
    })
    return graph


def add_hairstyle_pass(graph, hairstyle_image, prompt, seed, width, height, quality):
    """Keep each Klein pass within four image references when all five are used."""
    hair=build_workflow(['body-output',hairstyle_image],prompt,(seed+1)%(2**53),width,height,quality=quality)
    # The second pass reads the generated body image directly; no file roundtrip.
    hair.pop('20')
    hair['21']['inputs']['image']=['body-output',0]
    for key,node in hair.items():
        inputs={name:((['12',0] if value[0]=='body-output' else ['hair-'+value[0],value[1]]) if isinstance(value,list) else value) for name,value in node['inputs'].items()}
        graph['hair-'+key]={'class_type':node['class_type'],'inputs':inputs}
    graph.pop('13')
    return graph
