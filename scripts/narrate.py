"""Offline Mandarin neural narration using Kokoro 1.1-zh on CPU."""
import json
import os
import sys
import wave
from pathlib import Path

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'

def main():
    import numpy as np
    import torch
    from kokoro import KModel,KPipeline
    torch.set_num_threads(4)
    source=Path(sys.argv[1]).resolve();edit=json.loads(source.read_text(encoding='utf8'))
    root=Path(__file__).resolve().parents[1];folder=root/'runtime/voice'
    model=KModel(repo_id='hexgrad/Kokoro-82M-v1.1-zh',config=str(folder/'config.json'),model=str(folder/'kokoro-v1_1-zh.pth')).to('cpu').eval()
    pipeline=KPipeline(lang_code='z',repo_id='hexgrad/Kokoro-82M-v1.1-zh',model=model,device='cpu')
    for index,scene in enumerate(edit['scenes']):
        parts=[result.audio.numpy() for result in pipeline(scene['narration'],voice=str(folder/'zf_094.pt'),speed=1.05) if result.audio is not None]
        if not parts:raise RuntimeError('Neural narrator returned no audio')
        audio=np.concatenate(parts)
        # Fit complete narration into the shot using modest speed adjustment, never truncation.
        maximum=7.6
        if len(audio)/24000>maximum:
            speed=1.05*(len(audio)/24000/maximum)
            if speed>1.5:raise RuntimeError(f'Scene {index+1}: narration too long; please shorten it')
            parts=[result.audio.numpy() for result in pipeline(scene['narration'],voice=str(folder/'zf_094.pt'),speed=speed) if result.audio is not None]
            audio=np.concatenate(parts)
        with wave.open(str(source.parent/f'voice-{index:02}.wav'),'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(24000)
            out.writeframes((np.clip(audio,-1,1)*32767).astype('<i2').tobytes())
        print(f'Kokoro scene {index+1}: {len(audio)/24000:.2f}s',flush=True)

if __name__=='__main__':main()
