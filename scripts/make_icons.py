from pathlib import Path
from PIL import Image,ImageDraw

directory=Path(__file__).resolve().parents[1]/'web'
for size in [192,512]:
    image=Image.new('RGB',(size,size),'#191919')
    draw=ImageDraw.Draw(image)
    # An original geometric hanger mark, drawn directly as a native app icon.
    scale=size/512
    points=[(256,139),(256,119),(272,107),(294,113),(300,133),(287,149),(256,171),(256,208),(135,300),(135,316),(377,316),(377,300),(256,208)]
    draw.line([(int(x*scale),int(y*scale)) for x,y in points],fill='#f0ebe4',width=max(3,int(13*scale)),joint='curve')
    draw.rounded_rectangle((int(83*scale),int(68*scale),int(429*scale),int(428*scale)),radius=int(70*scale),outline='#706c65',width=max(1,int(3*scale)))
    draw.line((int(195*scale),int(365*scale),int(317*scale),int(365*scale)),fill='#a49d93',width=max(1,int(4*scale)))
    image.save(directory/f'icon-{size}.png')
