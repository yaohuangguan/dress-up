'use strict';
const $ = (id) => document.getElementById(id);
const labels = {character:'人物',outfit:'衣装',pose:'姿势',background:'背景',hairstyle:'发型'};
const names = {character:'人物参考',outfit:'挑件衣服',pose:'选择姿势',background:'去哪里拍？',hairstyle:'换个发型？'};
const symbols = {character:'♙',outfit:'♧',pose:'♧',background:'□',hairstyle:'◡'};
const state = {kind:'character',selected:{character:null,outfit:null,pose:null,background:null,hairstyle:null},angle:'front',category:'',q:'',page:1,pages:1,status:null,job:null,result:null,loadSequence:0,view:'studio'};
const legacySizes={portrait:[640,896],square:[768,768],large:[768,1024]};
function selectedProfile() {return state.status?.profiles?.[$('qualitySelect').value];}
function profileReady() {return selectedProfile()?.ready ?? false;}
function updateSizeLabels() {
  const sizes=selectedProfile()?.sizes;
  if(!sizes)return;
  for(const option of $('sizeSelect').options)option.textContent=`${sizes[option.value].join(' × ')} · ${{portrait:'竖幅',square:'方形',large:'大竖幅'}[option.value]}`;
}
let toastTimer, searchTimer, pollTimer, installPrompt, mobileTimer;
const phoneButton=document.createElement('button');
phoneButton.id='phoneButton';phoneButton.className='upload-button';phoneButton.textContent='▦ 扫码上传';phoneButton.hidden=true;
const libraryTools=document.createElement('div');libraryTools.className='library-tools';
$('uploadButton').before(libraryTools);libraryTools.append(phoneButton,$('uploadButton'));
const backgroundBox=document.createElement('div');backgroundBox.id='backgroundBox';backgroundBox.className='background-description';backgroundBox.hidden=true;
backgroundBox.innerHTML='<label for="backgroundPromptInput">也可以直接描述地点</label><textarea id="backgroundPromptInput" rows="2" maxlength="600" placeholder="例如：日落时的海边，远处是浅色海浪，柔和侧光…"></textarea><button id="clearBackground" class="text-button">移除背景图片，使用描述或默认影棚</button>';
$('libraryTitle').closest('.library-panel').after(backgroundBox);
const hairBox=document.createElement('div');hairBox.className='background-description';hairBox.hidden=true;
hairBox.innerHTML='<label for="hairPromptInput">也可以直接描述发型</label><textarea id="hairPromptInput" rows="2" maxlength="400" placeholder="例如：齐肩微卷、空气刘海，保留黑发…"></textarea><button id="clearHair" class="text-button">移除发型参考</button><small>不选发型、不填描述时，保留人物原发型。</small>';
backgroundBox.after(hairBox);
document.body.prepend(document.querySelector('.brand'));
document.body.append(document.querySelector('.sidebar-bottom'));
document.querySelectorAll('[data-nav]').forEach(button=>{const title={studio:'搭配',library:'素材',history:'作品'}[button.dataset.nav];button.setAttribute('aria-label',title);button.title=title;});
const esc = (v) => String(v ?? '').replace(/[&<>"']/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(url,options={}) {
  const response = await fetch(url,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),'X-Local-Look':'1',...options.headers},signal:options.signal||AbortSignal.timeout(30000)});
  let result;
  try {result=await response.json();} catch {throw new Error(response.status===413?'图片太大，请选择 20MB 以内的图片':'本地服务返回异常，请检查启动日志');}
  if(!response.ok) throw new Error(result.error || `操作失败 (${response.status})`);
  return result;
}

function toast(message) {
  $('toast').textContent=message;
  $('toast').hidden=false;
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>$('toast').hidden=true,7000);
}

function saveSelection() {
  try {localStorage.setItem('local-look-selection',JSON.stringify({selected:Object.fromEntries(Object.entries(state.selected).map(([k,v])=>[k,v?.id||null])),angle:state.angle,size:$('sizeSelect').value,quality:$('qualitySelect').value,quality_preference_version:1,background_description:$('backgroundPromptInput').value,hairstyle_description:$('hairPromptInput').value}));} catch {}
}

function renderSelection() {
  $('selectionSlots').innerHTML=Object.entries(labels).map(([kind,label],i)=>{
    const selected=state.selected[kind];
    return `<button class="slot ${state.kind===kind?'active':''}" data-kind="${kind}" aria-pressed="${state.kind===kind}"><span class="slot-index">0${i+1}</span>${selected?`<img src="${esc(selected.thumbnail)}" alt="${esc(selected.name)}">`:`<span class="slot-placeholder">${symbols[kind]}</span>`}<div><strong>${label}</strong><small>${esc(selected?.code || (kind==='background'?'可选':kind==='hairstyle'?'保持原发型':'点击选择'))}</small></div></button>`;
  }).join('');
  $('recipeItems').innerHTML=Object.entries(labels).map(([kind,label])=>`<span class="recipe-chip"><span>${label}</span>${esc(state.selected[kind]?.name || (kind==='hairstyle'?'保持原发型':'尚未选择'))}</span>`).join('');
  const ready=['character','outfit','pose'].every(kind=>!!state.selected[kind]);
  const busy=!!state.status?.active_job || (state.job && !['completed','failed','interrupted'].includes(state.job.status));
  const extraHairImage=state.selected.background && state.selected.hairstyle && state.selected.hairstyle.reference_mode!=='description';
  $('generateButton').disabled=!ready || !profileReady() || !!busy;
  $('generateLabel').textContent=busy?'正在本地生成…':'生成这套搭配';
  $('generateHint').textContent=busy?(state.job?.stages===2?'正在分两轮处理搭配和发型，页面会持续更新进度':'首次模型加载较慢，页面会持续更新进度'):!profileReady()?'本地引擎准备中 · 点击左下角查看状态':!ready?'选择人物、衣装与姿势，即可开始':extraHairImage?'包含自定义发型与背景，处理时间可能稍长':$('qualitySelect').value==='quality'?'Base 模型 · 原生高清 · 耗时较长，请耐心等待':'日常快速生成 · 通常约一分钟，实际随素材与显卡占用变化';
  $('angleSelect').hidden=state.kind!=='pose';
  phoneButton.hidden=state.kind!=='character';
  backgroundBox.hidden=state.kind!=='background';
  hairBox.hidden=state.kind!=='hairstyle';
  $('libraryTitle').textContent=names[state.kind];
  $('searchInput').placeholder=state.kind==='character'?'搜索人物名称…':state.kind==='outfit'?'搜索连衣裙、牛仔、白色、编号…':state.kind==='hairstyle'?'搜索波波头、狼尾、刘海、卷发…':state.kind==='background'?'搜索咖啡馆、海边、室内…':'搜索站姿、坐姿、动作编号…';
  renderPreview();
}

function renderPreview() {
  const output=state.result;
  const person=state.selected.character;
  const src=output?.image || person?.image;
  $('resultImage').hidden=!src;
  $('canvasEmpty').hidden=!!src;
  if(src && $('resultImage').getAttribute('src')!==src) $('resultImage').src=src;
  $('previewBadge').textContent=output?'已生成 · 本地成图':person?'人物参考 · 非成图':'参考预览';
  $('previewCaption').textContent=output?`种子 ${output.seed} · ${output.elapsed || '—'} 秒 · ${output.quality==='quality'?'Klein Base · 精细成片':'Klein · 快速预览'}`:'预览所选参考，生成后在此查看成图';
  const size=output?.size || $('sizeSelect').value;
  const dimensions=output?.width&&output?.height?[output.width,output.height]:output?legacySizes[size]:selectedProfile()?.sizes?.[size];
  $('dimensions').textContent=dimensions?dimensions.join(' × '):'精细成片';
  $('downloadButton').classList.toggle('disabled',!output);
  $('downloadButton').setAttribute('aria-disabled',String(!output));
  if(output) $('downloadButton').href=output.image+'?download=1'; else $('downloadButton').removeAttribute('href');
}

async function loadLibrary(reset=false) {
  if(reset)state.page=1;
  const seq=++state.loadSequence;
  const kind=state.kind;
  $('libraryCount').textContent='读取本地素材…';
  try {
    const params=new URLSearchParams({kind,q:state.q,category:state.category,angle:state.angle,page:String(state.page)});
    const data=await api('/api/catalog?'+params);
    if(seq!==state.loadSequence)return;
    state.pages=data.pages;
    $('libraryCount').textContent=`${data.total.toLocaleString()} ${kind==='outfit'?'套穿搭':kind==='pose'?'组动作':kind==='background'?'个地点':kind==='hairstyle'?'种发型':'位人物'} · 已存于本机`;
    $('categories').innerHTML=['',...data.categories].map(c=>`<button class="category ${state.category===c?'active':''}" data-category="${esc(c)}">${esc(c||'全部')}</button>`).join('');
    $('assetGrid').innerHTML=data.items.length?data.items.map(item=>`<button class="asset ${state.selected[kind]?.id===item.id?'selected':''}" data-item="${esc(item.id)}" aria-label="选择 ${esc(item.name)}" aria-pressed="${state.selected[kind]?.id===item.id}"><img src="${esc(item.thumbnail)}" loading="lazy" alt="${esc(item.name)}">${state.selected[kind]?.id===item.id?'<span class="asset-check">✓</span>':''}<div class="asset-text"><strong>${esc(item.name)}</strong><small>${esc(item.code)} · ${esc(item.category)}</small></div></button>`).join(''):`<div class="grid-empty"><span>＋</span>${kind==='character'?'导入一张清晰人物照，开始你的搭配。':'没有找到匹配素材，换个关键词试试。'}</div>`;
    $('pageInfo').textContent=`第 ${data.page} / ${data.pages} 页`;
    $('prevPage').disabled=state.page<=1;
    $('nextPage').disabled=state.page>=data.pages;
    $('assetGrid').scrollTop=0;
  } catch(error) {
    if(seq!==state.loadSequence)return;
    $('libraryCount').textContent='素材读取失败';
    toast(error.message);
  }
}

async function setKind(kind) {
  state.kind=kind;state.category='';state.q='';$('searchInput').value='';
  $('assetGrid').innerHTML='<div class="grid-empty">正在读取素材…</div>';
  renderSelection();
  await loadLibrary(true);
}

async function selectItem(id) {
  const item=await api('/api/items/'+encodeURIComponent(id)+'?angle='+state.angle);
  state.selected[item.kind]=item;
  state.result=null;
  saveSelection();renderSelection();await loadLibrary();
}

async function refreshStatus() {
  try {
    state.status=await api('/api/status');
    updateSizeLabels();
    document.body.classList.toggle('ready',profileReady());
    $('engineLabel').textContent=profileReady()?'本地引擎已就绪':state.status.connected?'模型下载中':'ComfyUI 未连接';
    $('footerStats').textContent=`${state.status.counts.outfit.toLocaleString()} 套衣装 / ${state.status.counts.pose} 组姿势 / ${state.status.pose_images.toLocaleString()} 张参考`;
    if(state.status.active_job && state.status.active_kind==='video') {
      if(window.resumeVideo)window.resumeVideo(state.status.active_job);
    } else if(state.status.active_job && state.status.active_job!=='scriptwriter' && !state.job) {
      state.job=await api('/api/jobs/'+state.status.active_job);
      updateJob(state.job);schedulePoll();
    }
  } catch {
    state.status=null;document.body.classList.remove('ready');$('engineLabel').textContent='本地服务已断开';
  }
  renderSelection();
}

function updateJob(job) {
  state.job=job;
  const active=!['completed','failed','interrupted'].includes(job.status);
  $('generating').hidden=!active;
  $('generationMessage').textContent=job.message;
  $('generationProgress').value=job.progress||0;
  if(job.status==='completed') {
    state.result=job;
    toast('新搭配已生成，图片已保存在本机。');
  } else if(['failed','interrupted'].includes(job.status))toast(job.message);
  renderSelection();
}

function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer=setTimeout(async()=>{
    if(!state.job || ['completed','failed','interrupted'].includes(state.job.status))return;
    try {
      const job=await api('/api/jobs/'+state.job.id);updateJob(job);
      if(!['completed','failed','interrupted'].includes(job.status))schedulePoll();
    } catch(error) {
      $('generationMessage').textContent='连接中断，正在重新连接本地服务…';
      schedulePoll();
    }
  },1500);
}

async function generate() {
  const raw=$('seedInput').value.trim();
  const seed=raw===''?null:Number(raw);
  if(seed!==null && (!Number.isSafeInteger(seed)||seed<0)){toast('随机种子需要填写有效的非负整数');return;}
  $('generateButton').disabled=true;
  try {
    const job=await api('/api/generate',{method:'POST',body:JSON.stringify({...Object.fromEntries(Object.entries(state.selected).map(([k,v])=>[k,v?.id||null])),background_description:$('backgroundPromptInput').value,hairstyle_description:$('hairPromptInput').value,angle:state.angle,size:$('sizeSelect').value,quality:$('qualitySelect').value,prompt:$('promptInput').value,seed})});
    state.result=null;updateJob(job);schedulePoll();
  } catch(error) {toast(error.message);renderSelection();}
}

async function uploadFile(file) {
  if(!file)return;
  if(file.size>20*1024*1024){toast('请选择 20MB 以内的 PNG、JPG 或 WebP 图片');return;}
  const kind=state.kind;
  $('uploadButton').disabled=true;$('uploadButton').textContent='导入中…';
  try {
    const form=new FormData();form.append('kind',kind);form.append('image',file);
    const item=await api('/api/uploads',{method:'POST',body:form});
    state.selected[kind]=item;state.result=null;state.category='';state.q='';$('searchInput').value='';
    if(state.kind!==kind)state.kind=kind;
    saveSelection();renderSelection();await loadLibrary(true);await refreshStatus();toast('图片已导入本地素材库');
  } catch(error) {toast(error.message);} finally {$('uploadButton').disabled=false;$('uploadButton').textContent='＋ 导入图片';$('fileInput').value='';}
}

async function showHistory() {
  if($('videoView'))$('videoView').hidden=true;
  state.view='history';$('studioView').hidden=true;$('historyView').hidden=false;
  document.body.classList.remove('library-mode');
  $('pageTitle').textContent='生成记录';$('heading').textContent='生成记录 / 03';$('subheading').textContent='回看你的搭配灵感，下载成图，或沿用组合继续探索。';
  document.querySelectorAll('[data-nav]').forEach(x=>x.classList.toggle('active',x.dataset.nav==='history'));
  $('historyGrid').innerHTML='<div class="grid-empty">正在读取生成记录…</div>';
  try {
    const history=await api('/api/history');
    $('historyGrid').innerHTML=history.length?history.map(job=>`<button class="history-card" data-job="${esc(job.id)}">${job.image?`<img src="${esc(job.image)}" loading="lazy" alt="生成的搭配图片">`:`<div class="history-placeholder">${job.status==='failed'?'↺':'◷'}</div>`}<div><strong>${esc(job.selection?.outfit?.name || '我的搭配')}</strong><p>${esc(new Date(job.created*1000).toLocaleString('zh-CN'))}<br>${esc(job.status==='completed'?`${job.elapsed} 秒 · 种子 ${job.seed}`:job.message)}</p></div></button>`).join(''):'<div class="grid-empty"><span>◷</span>还没有生成记录。<br>选好三张参考图，开始第一套搭配。</div>';
  } catch(error) {toast(error.message);}
}

function showStudio(library=false) {
  if($('videoView'))$('videoView').hidden=true;
  state.view=library?'library':'studio';$('studioView').hidden=false;$('historyView').hidden=true;
  document.body.classList.toggle('library-mode',library);
  $('pageTitle').textContent=library?'素材图书馆':'搭配工作台';
  $('heading').innerHTML=library?'挑点新灵感<span> / MATERIALS</span>':'换个样子<span>。</span>';
  $('subheading').textContent=library?'人物、服装、动作、地点，都在这里。':'选好人物、衣装与姿势，把这一套试上身。';
  document.querySelectorAll('[data-nav]').forEach(x=>x.classList.toggle('active',x.dataset.nav===state.view));
  if(library)$('libraryTitle').scrollIntoView({block:'center',behavior:'smooth'});
}

async function openJob(id) {
  try {
    const job=await api('/api/jobs/'+id);
    state.selected={character:null,outfit:null,pose:null,background:null,hairstyle:null,...job.selection};state.angle=job.angle;$('angleSelect').value=job.angle;$('sizeSelect').value=job.size;updateSizeLabels();$('promptInput').value=job.prompt||'';$('seedInput').value=job.seed;$('backgroundPromptInput').value=job.background_description||'';$('hairPromptInput').value=job.hairstyle_description||'';
    if(job.status==='completed')state.result=job;else state.result=null;
    showStudio();saveSelection();renderSelection();await loadLibrary(true);
    if(job.status!=='completed')toast(job.message);
  } catch(error) {toast(error.message);}
}

function dialog(title,html) {$('dialogTitle').textContent=title;$('dialogBody').innerHTML=html;$('infoDialog').showModal();}
function showEngine() {
  const status=state.status;
  dialog('本地引擎',`<p><strong>${esc(profileReady()?'已就绪，可开始生成':status?.error||'模型正在准备')}</strong></p><p>计算引擎：FLUX.2 Klein Base 4B / Klein 4B<br>精细成片：Base · 50 步，原生 896 × 1216 起；快速预览：4 步。<br>显卡：${esc(status?.gpu?.name||'等待 ComfyUI 返回显卡信息')}<br>低显存配置：CPU 文本编码、GPU 模型按需卸载、分块解码。</p>${(status?.models||[]).map(m=>`<div class="model-row">${m.ready?'✓':'◷'} ${esc(m.name)}<br>${m.ready?'已安装':`已下载 ${(m.bytes/1e9).toFixed(2)} GB`}</div>`).join('')}<p>本机地址：<a href="http://127.0.0.1:8188" target="_blank" rel="noopener">ComfyUI 8188 ↗</a><br>请保持本地服务运行。PWA 可安装到桌面；停止服务后无法生成图片。</p>`);
}

function showSources() {
  dialog('素材来源',`<p>姿势库：<a href="https://github.com/wquguru/shisei" target="_blank" rel="noopener">Shisei · wquguru ↗</a><br>本地已集成 280 组动作、1,158 张多角度线稿，图片与数据为 CC0。内置人物由本机 FLUX.2 Klein 4B 生成，均为虚构成年人物。</p><p>服装库：<a href="https://github.com/paipiange/nvzhuang" target="_blank" rel="noopener">COSTUME-DB-01 镜像 · paipiange ↗</a><br>原始作者：ギア (@giaaibusi)。已下载 1,407 套服装的 WebP 展示图和缩略图，供本机参考。</p><p>原始图片条款与镜像的 MIT 声明存在差异；本项目保留两者记录，未将服装素材重新声明为 MIT 或 CC0。分享项目时请排除服装素材，使用前查看原始来源说明。</p><p>新增人像与发型来源：<a href="https://ai-portrait-gallery.pages.dev/" target="_blank" rel="noopener">あぎ · AI Model Face Database ↗</a>，CC0；本机使用预览图，未将其打包发布。1,499 张人像按发长检索，50 种发型按描述调整造型。<br>你可以随时导入自己的人物照、服装图、发型图和姿势图。上传和生图均在本机完成。</p>`);
}

async function openMobileUpload(ip) {
  clearTimeout(mobileTimer);
  dialog('手机上传人物','<p>正在准备本地上传二维码…</p>');
  try {
    const session=await api('/api/mobile-session',{method:'POST',body:JSON.stringify(ip?{ip}:{})});
    state.mobileSession=session.id;
    $('dialogBody').innerHTML=`<div class="qr-panel"><img src="${esc(session.qr)}" alt="手机上传二维码"><strong>用手机相机扫码</strong><p>手机与电脑连接同一 Wi-Fi<br>拍照或选择照片，上传后会自动出现在人物库</p><label>本机网卡<select id="mobileIp">${session.addresses.map(x=>`<option value="${esc(x.ip)}" ${x.ip===session.ip?'selected':''}>${esc(x.name)} · ${esc(x.ip)}</option>`).join('')}</select></label><span id="mobileCountdown">10 分钟有效 · 仅可上传一次</span><small>打不开时，确认同一 Wi-Fi、网卡地址和 Windows 防火墙设置。</small></div>`;
    $('mobileIp').addEventListener('change',()=>openMobileUpload($('mobileIp').value));
    pollMobile(session);
  } catch(error){$('dialogBody').textContent=error.message;}
}

function pollMobile(session) {
  mobileTimer=setTimeout(async()=>{
    if(state.mobileSession!==session.id)return;
    try {
      const result=await api('/api/mobile-session/'+session.id);
      if(result.status==='uploaded') {
        state.selected.character=result.item;state.result=null;
        if($('infoDialog').open && $('dialogTitle').textContent==='手机上传人物')$('infoDialog').close();
        state.kind='character';state.category='';state.q='';$('searchInput').value='';
        saveSelection();renderSelection();loadLibrary(true);refreshStatus();toast('手机照片已收到，人物已自动选中。');
        return;
      }
      if(['expired','revoked'].includes(result.status)) {if($('mobileCountdown'))$('mobileCountdown').textContent='二维码已失效，请重新点击扫码上传';return;}
      const seconds=Math.max(0,Math.ceil(result.expires-Date.now()/1000));
      if($('mobileCountdown'))$('mobileCountdown').textContent=`${Math.floor(seconds/60)} 分 ${seconds%60} 秒后失效 · 仅可上传一次`;
      pollMobile(session);
    } catch {pollMobile(session);}
  },1500);
}

async function init() {
  let saved={};
  try {saved=JSON.parse(localStorage.getItem('local-look-selection')||'{}');} catch {}
  state.angle=['front','diag','side','above','below'].includes(saved.angle)?saved.angle:'front';$('angleSelect').value=state.angle;
  if(saved.quality_preference_version===1 && ['quality','fast'].includes(saved.quality))$('qualitySelect').value=saved.quality;
  else $('qualitySelect').value='fast';
  if(['portrait','square','large'].includes(saved.size))$('sizeSelect').value=saved.size;
  if(typeof saved.hairstyle_description==='string')$('hairPromptInput').value=saved.hairstyle_description.slice(0,400);
  if(typeof saved.background_description==='string')$('backgroundPromptInput').value=saved.background_description.slice(0,600);
  await Promise.all(Object.keys(labels).map(async kind=>{
    try {
      if(['background','hairstyle'].includes(kind)&&!saved.selected?.[kind])return;
      if(saved.selected?.[kind])state.selected[kind]=await api('/api/items/'+encodeURIComponent(saved.selected[kind])+'?angle='+state.angle);
      else {
        const filter=kind==='pose'?'&q=standing':'';
        const data=await api('/api/catalog?kind='+kind+'&angle='+state.angle+filter);
        state.selected[kind]=data.items[0]||null;
      }
    } catch {}
  }));
  renderSelection();await Promise.all([loadLibrary(),refreshStatus()]);
  setInterval(refreshStatus,12000);
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
}

$('selectionSlots').addEventListener('click',e=>{const b=e.target.closest('[data-kind]');if(b)setKind(b.dataset.kind);});
$('assetGrid').addEventListener('click',e=>{const b=e.target.closest('[data-item]');if(b)selectItem(b.dataset.item).catch(error=>toast(error.message));});
$('categories').addEventListener('click',e=>{const b=e.target.closest('[data-category]');if(b){state.category=b.dataset.category;loadLibrary(true);}});
$('searchInput').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.q=$('searchInput').value;loadLibrary(true);},250);});
$('angleSelect').addEventListener('change',async()=>{
  state.angle=$('angleSelect').value;
  if(state.selected.pose) {
    if(state.selected.pose.angles?.length && !state.selected.pose.angles.includes(state.angle)) {
      state.selected.pose=null;toast('该动作没有这个视角，请重新选择姿势');
    } else state.selected.pose=await api('/api/items/'+state.selected.pose.id+'?angle='+state.angle);
  }
  state.result=null;saveSelection();renderSelection();loadLibrary(true);
});
$('prevPage').addEventListener('click',()=>{if(state.page>1){state.page--;loadLibrary();}});
$('nextPage').addEventListener('click',()=>{if(state.page<state.pages){state.page++;loadLibrary();}});
$('uploadButton').addEventListener('click',()=>$('fileInput').click());
phoneButton.addEventListener('click',()=>openMobileUpload());
$('fileInput').addEventListener('change',()=>uploadFile($('fileInput').files[0]));
$('generateButton').addEventListener('click',generate);
$('resetButton').addEventListener('click',()=>{state.selected={character:null,outfit:null,pose:null,background:null,hairstyle:null};state.result=null;$('backgroundPromptInput').value='';$('hairPromptInput').value='';saveSelection();renderSelection();loadLibrary();});
$('clearBackground').addEventListener('click',()=>{state.selected.background=null;state.result=null;saveSelection();renderSelection();loadLibrary();});
$('backgroundPromptInput').addEventListener('input',saveSelection);
$('hairPromptInput').addEventListener('input',saveSelection);
$('clearHair').addEventListener('click',()=>{state.selected.hairstyle=null;state.result=null;saveSelection();renderSelection();loadLibrary();});
$('reuseButton').addEventListener('click',()=>{state.result=null;renderPreview();});
$('qualitySelect').addEventListener('change',()=>{updateSizeLabels();saveSelection();renderSelection();refreshStatus();});
$('sizeSelect').addEventListener('change',()=>{saveSelection();renderPreview();});
$('historyButton').addEventListener('click',showHistory);
$('historyGrid').addEventListener('click',e=>{const b=e.target.closest('[data-job]');if(b)openJob(b.dataset.job);});
document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>b.dataset.nav==='history'?showHistory():showStudio(b.dataset.nav==='library')));
$('engineButton').addEventListener('click',showEngine);$('sourcesButton').addEventListener('click',showSources);
$('closeDialog').addEventListener('click',()=>$('infoDialog').close());
$('infoDialog').addEventListener('click',e=>{if(e.target===$('infoDialog')){const r=$('infoDialog').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('infoDialog').close();}});
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;$('installButton').hidden=false;});
$('installButton').addEventListener('click',async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;$('installButton').hidden=true;}});
window.addEventListener('appinstalled',()=>$('installButton').hidden=true);
init().catch(error=>toast(error.message));
