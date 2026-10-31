"""ComfyUI native FLUX.2 Klein graph; three separate image conditions."""
def build_workflow(images, prompt, seed, width=640, height=896, steps=4):
    graph={
        '1':{'class_type':'UNETLoader','inputs':{'unet_name':'flux-2-klein-4b-fp8.safetensors','weight_dtype':'default'}},
        '2':{'class_type':'CLIPLoader','inputs':{'clip_name':'qwen_3_4b.safetensors','type':'flux2','device':'cpu'}},
        '3':{'class_type':'VAELoader','inputs':{'vae_name':'flux2-vae.safetensors'}},
        '4':{'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':prompt}},
        '5':{'class_type':'ConditioningZeroOut','inputs':{'conditioning':['4',0]}},
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
        graph[str(node+1)]={'class_type':'ImageScaleToTotalPixels','inputs':{'image':[str(node),0],'upscale_method':'lanczos','megapixels':0.25,'resolution_steps':16}}
        graph[str(node+2)]={'class_type':'VAEEncode','inputs':{'pixels':[str(node+1),0],'vae':['3',0]}}
        graph[str(node+3)]={'class_type':'ReferenceLatent','inputs':{'conditioning':positive,'latent':[str(node+2),0]}}
        graph[str(node+4)]={'class_type':'ReferenceLatent','inputs':{'conditioning':negative,'latent':[str(node+2),0]}}
        positive=[str(node+3),0]
        negative=[str(node+4),0]
    graph.update({
        '10':{'class_type':'CFGGuider','inputs':{'model':['1',0],'positive':positive,'negative':negative,'cfg':1.0}},
        '11':{'class_type':'SamplerCustomAdvanced','inputs':{'noise':['6',0],'guider':['10',0],'sampler':['7',0],'sigmas':['8',0],'latent_image':['9',0]}},
        '12':{'class_type':'VAEDecodeTiled','inputs':{'samples':['11',0],'vae':['3',0],'tile_size':512,'overlap':64,'temporal_size':64,'temporal_overlap':8}},
        '13':{'class_type':'SaveImage','inputs':{'images':['12',0],'filename_prefix':'LocalLookStudio/look'}},
    })
    return graph
