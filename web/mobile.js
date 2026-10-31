'use strict';
const $=id=>document.getElementById(id);
let file=null,preview=null;
const token=location.hash.slice(1);
// The capability stays in the URL fragment and a request header, never an HTTP URL or access log.
history.replaceState(null,'',location.pathname);
if(!/^[A-Za-z0-9_-]{32}$/.test(token)){$('status').textContent='请从电脑扫码打开上传页。';$('camera').disabled=true;$('album').disabled=true;}
$('camera').onclick=()=>$('cameraInput').click();
$('album').onclick=()=>$('albumInput').click();
function choose(input){
  file=input.files[0];if(!file)return;
  if(file.size>20*1024*1024){$('status').textContent='请选择 20MB 以内的照片。';file=null;return;}
  if(preview)URL.revokeObjectURL(preview);preview=URL.createObjectURL(file);
  $('image').src=preview;$('image').hidden=false;$('preview').querySelector('span').hidden=true;$('send').hidden=false;$('status').textContent='确认照片后，上传到电脑。';
}
$('cameraInput').onchange=()=>choose($('cameraInput'));
$('albumInput').onchange=()=>choose($('albumInput'));
$('send').onclick=async()=>{
  if(!file)return;$('send').disabled=true;$('status').textContent='正在直接传输到你的电脑…';
  try{
    const data=new FormData();data.append('image',file);
    const response=await fetch('/api/upload',{method:'POST',headers:{'X-Upload-Token':token},body:data,signal:AbortSignal.timeout(60000)});
    let result;try{result=await response.json();}catch{throw new Error('上传失败，请回到电脑重新生成二维码。');}
    if(!response.ok)throw new Error(result.error||'上传失败');
    $('status').textContent='✓ 已上传到电脑！\n回到桌面，即可为自己搭配衣装。';$('send').hidden=true;$('camera').disabled=true;$('album').disabled=true;
  }catch(error){$('status').textContent=error.message||'网络中断，请确认连接同一 Wi-Fi。';$('send').disabled=false;}
};
