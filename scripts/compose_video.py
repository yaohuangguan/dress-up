"""Cut generated shots, burn captions, and mux local Windows narration with PyAV."""
import json
import os
import subprocess
import sys
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FPS=24
RATE=24000

def lines(text,font,width):
    result=[];line=''
    for char in text:
        if font.getlength(line+char)>width and line:result.append(line);line=''
        line+=char
    if line:result.append(line)
    return result

def main():
    source=Path(sys.argv[1]).resolve()
    edit=json.loads(source.read_text(encoding='utf8'));folder=source.parent
    subprocess.run([sys.executable,str(Path(__file__).with_name('narrate.py')),str(source)],check=True,timeout=600,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    fontfile=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'
    font=ImageFont.truetype(str(fontfile),17);small=ImageFont.truetype(str(fontfile),13)
    metadata=[]
    for clip in edit['clips']:
        with av.open(clip) as container:
            stream=container.streams.video[0]
            metadata.append((stream.width,stream.height,stream.frames))
    width,height,_=metadata[0]
    if any((w,h)!=(width,height) or count<1 for w,h,count in metadata):raise RuntimeError('Inconsistent or empty generated shots')
    output=av.open(str(folder/'film.partial.mp4'),'w')
    video=output.add_stream('libx264',rate=FPS);video.width=width;video.height=height;video.pix_fmt='yuv420p';video.options={'crf':'18','preset':'fast'}
    audio=output.add_stream('aac',rate=RATE);audio.layout='mono';audio.bit_rate=96000
    frame_index=0
    try:
        for index,(clip,scene) in enumerate(zip(edit['clips'],edit['scenes'])):
            count=metadata[index][2];samples=count*(RATE//FPS)
            pcm=np.zeros(samples,dtype=np.float32)
            with wave.open(str(folder/f'voice-{index:02}.wav'),'rb') as wav:
                if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,RATE):raise RuntimeError('Unexpected narration WAV format')
                raw=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768
            # Never cut spoken words: report a long narration so the script can be shortened.
            offset=RATE//4
            if len(raw)+offset>samples:raise RuntimeError(f'Scene {index+1} narration is longer than the generated shot; shorten its text.')
            pcm[offset:offset+len(raw)]=raw
            caption=lines(scene['narration'],font,width-36)
            overlay=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(overlay)
            block_height=len(caption)*27+24
            draw.rectangle((0,height-block_height,width,height),fill=(8,10,16,180))
            for row,line in enumerate(caption):draw.text((width/2,height-block_height+10+row*27),line,font=font,anchor='mt',fill='white',stroke_width=1,stroke_fill='black')
            draw.text((14,14),f'{index+1:02} / {scene["title"]}',font=small,fill='white',stroke_width=1,stroke_fill='black')
            decoded=0
            with av.open(clip) as container:
                for frame in container.decode(video=0):
                    image=Image.alpha_composite(frame.to_image().convert('RGBA'),overlay).convert('RGB')
                    vf=av.VideoFrame.from_image(image);vf.pts=frame_index;vf.time_base=Fraction(1,FPS)
                    for packet in video.encode(vf):output.mux(packet)
                    start=decoded*(RATE//FPS)
                    af=av.AudioFrame.from_ndarray(pcm[start:start+RATE//FPS].reshape(1,-1),format='fltp',layout='mono')
                    af.sample_rate=RATE;af.pts=frame_index*(RATE//FPS);af.time_base=Fraction(1,RATE)
                    for packet in audio.encode(af):output.mux(packet)
                    frame_index+=1;decoded+=1
            if decoded!=count:raise RuntimeError('Shot frame count differs from metadata')
            print(f'Scene {index+1}: {decoded} generated frames, narration {len(raw)/RATE:.2f}s',flush=True)
        for stream in [video,audio]:
            for packet in stream.encode(None):output.mux(packet)
    finally:output.close()
    (folder/'film.partial.mp4').replace(folder/'film.mp4')
    print(f'Exported {frame_index/FPS:.2f}s MP4 with Chinese narration and subtitles',flush=True)

if __name__=='__main__':main()
