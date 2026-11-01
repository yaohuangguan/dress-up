'use strict';
const film={mode:'story',info:null,job:null,source:null,timer:null,history:[],images:[],scenes:[]};
const filmNav=document.createElement('button');filmNav.className='nav';filmNav.dataset.nav='video';filmNav.setAttribute('aria-label','短片');filmNav.title='短片';filmNav.innerHTML='<span>▷</span>故事短片<small>04</small>';
document.querySelector('.sidebar nav').append(filmNav);
const filmView=document.createElement('section');filmView.id='videoView';filmView.hidden=true;
filmView.innerHTML=`<div class="film-layout"><div class="film-preview"><div class="film-screen"><img id="filmPoster" alt="故事主角参考图" hidden><video id="filmPlayer" controls playsinline preload="metadata" hidden></video><span class="film-word">衣见 / MOTION PICTURES</span></div><div class="film-meta"><span id="filmCaption">一张照片，一段故事。</span><a id="filmDownload" hidden>↓ 下载 MP4</a></div><div class="film-source"><select id="filmSource" aria-label="选择短片参考图片"><option value="">选择已生成图片或当前人物</option></select><button id="filmUpload">＋ 上传参考图</button><input id="filmFile" type="file" accept="image/png,image/jpeg,image/webp" hidden></div><p class="film-source-note">参考人物会贯穿各分镜；换景后的五官、服装一致性可能有偏差。</p><div class="film-history" id="filmHistory"></div></div><div class="film-controls"><div class="film-kicker">DIRECT YOUR NEXT STORY / 04</div><div class="film-tabs"><button data-film-mode="story" class="active">故事短片 · 1 分钟+</button><button data-film-mode="clip">动态片段</button></div><div id="filmStory"><h2>来自明天的消息</h2><p>深夜，一条来自自己号码的短信，让她发现明天的事故已经发生过。</p><div class="film-llm"><input id="filmIdea" maxlength="600" value="悬疑短片：收到来自明天的消息" aria-label="故事主题"><button id="filmWrite">AI 写分镜</button></div><p id="filmWriterStatus">本地编剧模型正在准备；可先使用下面的完整分镜。</p><div class="film-storyboard" id="filmStoryboard"></div><p>8 个独立镜头 · 约 64 秒 · 中文旁白与字幕<br>在本机逐镜生成，期间可继续浏览素材，请保持电脑和服务运行。</p></div><div id="filmClip" hidden><h2>让这一刻动起来</h2><p>从人物参考或成图出发，先试一段镜头。</p><label class="film-field">动作与镜头<select id="filmMotion"><option value="The person breathes naturally and looks toward the camera, with subtle head movement and a gentle breeze moving the hair. A slow cinematic push-in. Stable facial identity and clothing, realistic live action.">自然轻动 · 镜头推进</option><option value="A gentle breeze moves the person's hair and fabric. The person remains mostly still, blinking naturally. Static camera, realistic live action, stable facial identity and clothing.">微风 · 固定机位</option><option value="The person gently turns their head toward the light and gives a subtle smile. The camera slowly drifts sideways. Small natural motion, stable facial identity, cinematic live action.">回望 · 侧向运镜</option></select></label><label class="film-field">补充动作描述（英文效果更稳定）<textarea id="filmPrompt" maxlength="1500" rows="4" placeholder="例如：She slowly lifts her eyes and looks toward the window…"></textarea></label><label class="film-field">片段长度<select id="filmLength"><option value="73">约 3 秒</option><option value="121">约 5 秒</option></select></label></div><button id="filmGenerate" class="film-shoot" disabled><span>生成故事短片</span><span>↗</span></button><div class="film-status"><span id="filmMessage">正在连接视频引擎…</span><progress id="filmProgress" max="100" value="0" hidden></progress></div></div></div>`;
$('historyView').after(filmView);
const toFilm=document.createElement('button');toFilm.id='videoFromImage';toFilm.textContent='▷ 做成短片';$('downloadButton').before(toFilm);

function filmBusy(){return film.job&&!['completed','failed','interrupted'].includes(film.job.status);}
function renderFilm(){
  $('filmGenerate').disabled=!film.info?.ready||(film.mode==='story'&&!film.info?.voice_ready)||!film.source||!!state.status?.active_job||filmBusy();
  $('filmGenerate').firstElementChild.textContent=filmBusy()?'正在逐镜生成…':film.mode==='story'?'生成故事短片':'生成动态片段';
  if(!filmBusy()&&!film.info?.ready)$('filmMessage').textContent='视频模型下载中 · '+(film.info?.models||[]).map(m=>m.ready?'✓ 已安装':`${(m.bytes/1e9).toFixed(2)} GB`).join(' / ');
  else if(!filmBusy()&&film.mode==='story'&&!film.info?.voice_ready)$('filmMessage').textContent='神经中文配音模型正在准备…';
}
function filmSource(source){film.source=source;$('filmPoster').src=source.poster;$('filmPoster').hidden=false;$('filmPlayer').hidden=true;$('filmPlayer').pause();$('filmDownload').hidden=true;renderFilm();}
function restoreFilmSource(job){
  const image=/^\/results\/([a-zA-Z0-9-]+)\.png$/.exec(job.poster||'');
  const asset=/^\/media\/([a-zA-Z0-9-]+)$/.exec(job.poster||'');
  const id=job.source_job||image?.[1]||job.source_asset||asset?.[1];
  if(!id)return;
  const kind=job.source_job||image?'job':'asset';
  film.source={poster:job.poster,[kind==='job'?'source_job':'source_asset']:id};
  const value=kind+':'+id;
  if(![...$('filmSource').options].some(x=>x.value===value))$('filmSource').add(new Option('这条短片的参考图',value));
  $('filmSource').value=value;
}
function renderStoryboard(){
  $('filmStoryboard').innerHTML=film.scenes.map((s,i)=>`<details class="film-shot"><summary><small>${String(i+1).padStart(2,'0')} / 8s</small><b>${esc(s.title)}</b></summary><label class="film-field">旁白<textarea data-scene="${i}" data-field="narration" maxlength="45" rows="2">${esc(s.narration)}</textarea></label><label class="film-field">场景画面<textarea data-scene="${i}" data-field="visual" maxlength="2000" rows="4">${esc(s.visual)}</textarea></label><label class="film-field">镜头动作<textarea data-scene="${i}" data-field="motion" maxlength="1200" rows="3">${esc(s.motion)}</textarea></label></details>`).join('');
}
async function openFilm(source){
  state.view='video';$('studioView').hidden=true;$('historyView').hidden=true;filmView.hidden=false;document.body.classList.remove('library-mode');
  $('pageTitle').textContent='故事短片';$('heading').innerHTML='让故事发生<span>。</span>';$('subheading').textContent='从一张人物照出发，写分镜、拍镜头，再把它们剪成一部短片。';
  document.querySelectorAll('[data-nav]').forEach(x=>x.classList.toggle('active',x.dataset.nav==='video'));
  try{
    const [info,images,history]=await Promise.all([api('/api/video/status'),api('/api/history'),api('/api/video/history')]);film.info=info;film.images=images.filter(x=>x.status==='completed');film.history=history;
    if(!film.scenes.length){film.scenes=structuredClone(info.templates[0].scenes);renderStoryboard();}
    $('filmSource').innerHTML='<option value="">选择参考图</option>'+(state.selected.character?`<option value="asset:${esc(state.selected.character.id)}">当前人物 · ${esc(state.selected.character.name)}</option>`:'')+film.images.map((x,i)=>`<option value="job:${x.id}">成图 ${i+1} · ${esc(x.selection?.outfit?.name||'本地图片')}</option>`).join('');
    if(source)filmSource(source);else if(filmBusy())restoreFilmSource(film.job);else if(!film.source){if(film.images[0])filmSource({source_job:film.images[0].id,poster:film.images[0].image});else if(state.selected.character)filmSource({source_asset:state.selected.character.id,poster:state.selected.character.image});}
    $('filmSource').value=film.source?.source_job?'job:'+film.source.source_job:film.source?.source_asset?'asset:'+film.source.source_asset:'';
    $('filmHistory').innerHTML=history.map(x=>`<button data-film-job="${x.id}"><img src="${esc(x.poster)}" alt="短片参考"><strong>${esc(x.title)}</strong>${x.status==='completed'?`${x.duration} 秒 · 播放 ↗`:esc(x.message)}</button>`).join('');
    if(info.active&&!filmBusy())window.resumeVideo(info.active);
    renderFilm();checkWriter();
  }catch(error){toast(error.message);}
}
function updateFilm(job){
  film.job=job;$('filmMessage').textContent=(job.scene?`分镜 ${job.scene}/8 · `:'')+job.message;
  $('filmProgress').hidden=!filmBusy();$('filmProgress').value=job.mode==='clip'?job.step_progress||job.progress:Math.min(99,(job.progress||0)+(job.step_progress||0)*.1);
  if(job.status==='completed'){
    if(!['127.0.0.1','localhost'].includes(location.hostname)){
      $('filmPlayer').pause();$('filmPlayer').hidden=true;$('filmPoster').src=job.poster;$('filmPoster').hidden=false;$('filmDownload').hidden=true;
      $('filmCaption').textContent=`${job.title} · ${job.duration} 秒 · 已保存在电脑`;
      $('filmMessage').textContent='当前公网入口可查看进度，完整视频请在电脑上的衣见播放。';renderFilm();return;
    }
    $('filmPlayer').src=job.video;$('filmPlayer').hidden=false;$('filmPoster').hidden=true;$('filmDownload').href=job.video+'?download=1';$('filmDownload').hidden=false;
    $('filmCaption').textContent=`${job.title} · ${job.duration} 秒 · ${job.dimensions?.join(' × ')} · 生成耗时 ${Math.round(job.elapsed/60)} 分钟`;
    refreshStatus();
  }
  renderFilm();
}
function pollFilm(){clearTimeout(film.timer);if(!filmBusy())return;film.timer=setTimeout(async()=>{try{updateFilm(await api('/api/video/jobs/'+film.job.id));}catch{$('filmMessage').textContent='正在重新连接，任务仍在本机运行…';}pollFilm();},2000);}
window.resumeVideo=async id=>{if(film.job?.id===id&&filmBusy())return;try{updateFilm(await api('/api/video/jobs/'+id));pollFilm();}catch{}};
async function checkWriter(){try{const r=await api('/api/video/writer');$('filmWrite').disabled=!r.ready;$('filmWriterStatus').textContent=r.ready?'本地 Qwen3 4B 编剧 · 神经中文旁白':'本地编剧模型尚未安装，可使用预设分镜';}catch{$('filmWrite').disabled=true;}}
filmNav.addEventListener('click',()=>openFilm());
toFilm.addEventListener('click',()=>openFilm(state.result?{source_job:state.result.id,poster:state.result.image}:state.selected.character?{source_asset:state.selected.character.id,poster:state.selected.character.image}:null));
$('filmSource').addEventListener('change',()=>{const [kind,id]=$('filmSource').value.split(':');if(kind==='job'){const item=film.images.find(x=>x.id===id);if(item)filmSource({source_job:id,poster:item.image});}else if(kind==='asset')filmSource({source_asset:id,poster:state.selected.character.image});else{film.source=null;renderFilm();}});
$('filmStoryboard').addEventListener('input',e=>{if(e.target.dataset.field)film.scenes[Number(e.target.dataset.scene)][e.target.dataset.field]=e.target.value;});
document.querySelectorAll('[data-film-mode]').forEach(b=>b.addEventListener('click',()=>{film.mode=b.dataset.filmMode;$('filmStory').hidden=film.mode!=='story';$('filmClip').hidden=film.mode!=='clip';document.querySelectorAll('[data-film-mode]').forEach(x=>x.classList.toggle('active',x===b));renderFilm();}));
$('filmGenerate').addEventListener('click',async()=>{
  if(!film.source)return;
  $('filmGenerate').disabled=true;
  try{const job=await api('/api/video/generate',{method:'POST',body:JSON.stringify({...film.source,mode:film.mode,template:'tomorrow',title:$('filmStory').querySelector('h2').textContent,scenes:film.scenes,motion:$('filmMotion').value+' '+$('filmPrompt').value,frames:Number($('filmLength').value)})});updateFilm(job);pollFilm();await refreshStatus();}catch(error){toast(error.message);renderFilm();}
});
$('filmUpload').addEventListener('click',()=>$('filmFile').click());
$('filmFile').addEventListener('change',async()=>{const file=$('filmFile').files[0];if(!file)return;if(file.size>20*1024*1024){toast('请选择 20MB 以内的图片');return;}try{const body=new FormData();body.append('kind','character');body.append('image',file);const item=await api('/api/uploads',{method:'POST',body});filmSource({source_asset:item.id,poster:item.image});$('filmSource').value='';}catch(error){toast(error.message);}finally{$('filmFile').value='';}});
$('filmHistory').addEventListener('click',async e=>{const b=e.target.closest('[data-film-job]');if(!b)return;try{const job=await api('/api/video/jobs/'+b.dataset.filmJob);restoreFilmSource(job);updateFilm(job);pollFilm();}catch(error){toast(error.message);}});
$('filmWrite').addEventListener('click',async()=>{const button=$('filmWrite');button.disabled=true;$('filmWriterStatus').textContent='本地编剧正在写 8 个分镜，首次加载需要几分钟…';try{let job=await api('/api/video/script',{method:'POST',body:JSON.stringify({idea:$('filmIdea').value})});const deadline=Date.now()+920000;while(job.status==='running'){if(Date.now()>deadline)throw new Error('编剧任务超时');await new Promise(resolve=>setTimeout(resolve,2000));job=await api('/api/video/script/'+job.id);}if(job.status!=='completed')throw new Error(job.message);const result=job.result;film.scenes=result.scenes;renderStoryboard();$('filmStory').querySelector('h2').textContent=result.title;$('filmStory').querySelector('p').textContent=result.logline;$('filmWriterStatus').textContent='分镜已生成，可展开修改后再拍摄。';}catch(error){toast(error.message);$('filmWriterStatus').textContent='编剧失败，可重试或使用已有分镜。';}finally{button.disabled=false;refreshStatus();}});
setInterval(()=>{if(!filmView.hidden)renderFilm();},3000);

const requestedFilm=new URLSearchParams(location.search).get('video');
if(requestedFilm&&/^[a-f0-9]{32}$/.test(requestedFilm))openFilm().then(async()=>{const job=await api('/api/video/jobs/'+requestedFilm);restoreFilmSource(job);updateFilm(job);pollFilm();}).catch(error=>toast(error.message));
