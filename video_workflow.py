"""Native LTX-Video 0.9.8 distilled image-to-video graph (no custom nodes)."""
MODEL='ltxv-2b-0.9.8-distilled-fp8.safetensors'
ENCODER='t5xxl_fp8_e4m3fn.safetensors'

def build_video_workflow(image,prompt,seed,width=512,height=704,frames=97):
    return {
        '1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':MODEL}},
        '2':{'class_type':'CLIPLoader','inputs':{'clip_name':ENCODER,'type':'ltxv','device':'cpu'}},
        '3':{'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':prompt}},
        '4':{'class_type':'ConditioningZeroOut','inputs':{'conditioning':['3',0]}},
        '5':{'class_type':'LTXVConditioning','inputs':{'positive':['3',0],'negative':['4',0],'frame_rate':24.0}},
        '6':{'class_type':'LoadImage','inputs':{'image':image}},
        '7':{'class_type':'LTXVImgToVideo','inputs':{'positive':['5',0],'negative':['5',1],'vae':['1',2],'image':['6',0],'width':width,'height':height,'length':frames,'batch_size':1,'strength':1.0}},
        '8':{'class_type':'RandomNoise','inputs':{'noise_seed':seed}},
        '9':{'class_type':'KSamplerSelect','inputs':{'sampler_name':'euler'}},
        # First-pass schedule published by Lightricks, including the terminal zero.
        '10':{'class_type':'ManualSigmas','inputs':{'sigmas':'1.0, 0.9937, 0.9875, 0.9812, 0.9750, 0.9094, 0.7250, 0.0'}},
        '11':{'class_type':'CFGGuider','inputs':{'model':['1',0],'positive':['7',0],'negative':['7',1],'cfg':1.0}},
        '12':{'class_type':'SamplerCustomAdvanced','inputs':{'noise':['8',0],'guider':['11',0],'sampler':['9',0],'sigmas':['10',0],'latent_image':['7',2]}},
        '13':{'class_type':'VAEDecodeTiled','inputs':{'samples':['12',0],'vae':['1',2],'tile_size':256,'overlap':64,'temporal_size':16,'temporal_overlap':8}},
        '14':{'class_type':'CreateVideo','inputs':{'images':['13',0],'fps':24.0}},
        '15':{'class_type':'SaveVideo','inputs':{'video':['14',0],'filename_prefix':'LocalLookStudio/video','format':'mp4','format.codec':'h264'}},
    }
