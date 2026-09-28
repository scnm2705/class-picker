/* Local Python-backed 3D board. Results are revealed only after landing. */
(function(){
 'use strict';
 const $=id=>document.getElementById(id), M=PickerModel, T=window.THREE;
 let roster=M.names.slice(), entries=[], world, labels=[], selected=-1;
 let position=0, round=1, count=1, busy=false, skipBatch=false, renderedRolls=0;
 let called=new Set(), waitingVip=new Set(roster.slice(0,5)), vipEnabled=true, vipQuota=1;
 let backend=null;
 let roundPeople=[];
 let history=[], pendingEvents=[], follow=true, lastTime=performance.now();
 let presentation={Direct:true,Dice:true,Move:true,Highlight:true,DirectSeconds:2,DiceSeconds:1.6,MoveSeconds:1.2,HighlightSeconds:2.5};
 const stage=$('stage'), host=$('scene'), labelLayer=$('labels');
 let renderer;
 try{
   renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance'});
   renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));renderer.shadowMap.enabled=true;
   renderer.shadowMap.type=T.PCFSoftShadowMap;renderer.outputColorSpace=T.SRGBColorSpace;
   renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.12;
   host.append(renderer.domElement);
 }catch(e){$('loading').textContent='此设备未能启动 3D 显示。请用支持 WebGL 的浏览器打开。';return;}
 const camera=new T.OrthographicCamera(-20,20,12,-12,.1,150);
 const offset=new T.Vector3(17,36,34), center=new T.Vector3(0,1,0), desired=center.clone();
 const scratch=new T.Vector3();let zoom=1,width=innerWidth,height=innerHeight;
 function minZoom(){return .18;}
 function escapeHTML(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
 function toast(text){$('toast').textContent=text;$('toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.remove('show'),2600);}
 function setCamera(){camera.position.copy(center).add(offset);camera.lookAt(center);camera.zoom=zoom;camera.updateProjectionMatrix();camera.updateMatrixWorld();$('zoomText').textContent=Math.round(zoom*100)+'%';}
 function resize(){width=innerWidth;height=innerHeight;renderer.setSize(width,height);camera.left=-12*width/height;camera.right=12*width/height;camera.top=12;camera.bottom=-12;setCamera();}
 function pan(dx,dy){const d=M.panOffset(dx,dy,height,zoom);center.x+=d.x;center.z+=d.z;desired.copy(center);setCamera();}
 function fit(){
   center.set(0,1,0);desired.copy(center);zoom=1;setCamera();
   const p=world.positions.map(q=>new T.Vector3(q.x,q.y+.3,q.z).project(camera));
   const minX=Math.min(...p.map(v=>v.x)),maxX=Math.max(...p.map(v=>v.x)),minY=Math.min(...p.map(v=>v.y)),maxY=Math.max(...p.map(v=>v.y));
   zoom=Math.min(1.5,(width-320)/(Math.max(.1,maxX-minX)*width/2),(height-330)/(Math.max(.1,maxY-minY)*height/2));
   zoom=Math.max(.15,zoom);setCamera();
   pan(-(minX+maxX)*width*zoom/4-105,(minY+maxY)*height*zoom/4-35);
 }
 function disposeWorld(){if(!world)return;const g=new Set(),m=new Set();world.scene.traverse(o=>{if(o.geometry)g.add(o.geometry);if(o.material)for(const a of Array.isArray(o.material)?o.material:[o.material])m.add(a);});g.forEach(a=>a.dispose());m.forEach(a=>a.dispose());}
 function makeBoard(slots){
   disposeWorld();entries=slots;world=createBoardWorld(T,entries);position=0;selected=-1;
   labelLayer.replaceChildren();labels=[];
   entries.forEach((s,i)=>{if(s.kind!=='student')return;const el=document.createElement('div');el.className='name-label';el.textContent=s.name;el.dataset.index=i;labelLayer.append(el);labels.push({el,index:i});});
   setPawn(world.positions[0]);$('result').hidden=true;
   document.querySelector('.hint span').textContent=roster.length+' 个姓名格 + '+entries.filter(s=>s.kind==='chest').length+' 个宝箱格';
   resize();fit();update();
 }
 function setPawn(p,lift=0){world.pawn.position.set(p.x,p.y+.24+lift,p.z-.39);world.ring.position.set(p.x,p.y+.245,p.z);}
 function update(){
   $('total').textContent=roster.length;$('called').textContent=called.size;$('remaining').textContent=roster.length-called.size;$('round').textContent=round;
   $('diceCount').textContent=count;$('rollCaption').textContent='计划点名 '+count+' 人';
   $('countMinus').disabled=busy||count<=1;$('countPlus').disabled=busy||count>=roster.length;
   for(const id of ['rosterButton','nextRound','settingsButton'])$(id).disabled=busy;
   $('rollButton').disabled=busy||!backend||!backend.eligible||backend.pending;
   $('animationSettings').disabled=busy;
   for(const {el,index}of labels){el.classList.toggle('called',called.has(entries[index].name));el.classList.toggle('selected',selected===index);}
   updateRoundPeople();
 }
 function updateRoundPeople(){
  $('roundPeopleCount').textContent=roundPeople.length+' 人';$('roundPeopleEmpty').hidden=roundPeople.length>0;$('roundPeopleList').replaceChildren();
  for(const p of roundPeople){const li=document.createElement('li'),name=document.createElement('span'),badge=document.createElement('small');name.textContent=p.name;badge.textContent=(p.vip?'VIP':'')+(p.count>1?' · '+p.count+' 次':'');li.className=p.vip?'vip':'';li.append(name,badge);$('roundPeopleList').append(li);}
 }
 function rememberPerson(p){const i=roundPeople.findIndex(x=>p.id?x.id===p.id:x.name===p.name),previous=i<0?null:roundPeople.splice(i,1)[0];roundPeople.unshift({...p,count:(previous?.count||0)+1,vip:p.vip||previous?.vip||false});}
 function render(time){
   const delta=Math.min(.1,(time-lastTime)/1000);lastTime=time;
   center.lerp(desired,Math.min(1,delta*5));setCamera();
   if(world){
     world.hub.rotation.z+=delta*.04;
     for(const {el,index}of labels){const p=world.positions[index];scratch.set(p.x,p.y+.34,p.z+.2).project(camera);const x=(scratch.x+1)*width/2,y=(1-scratch.y)*height/2;
       el.style.display=x< -80||x>width+80||y< -30||y>height+30?'none':'';
       el.style.transform='translate('+x+'px,'+y+'px) translate(-50%,-50%)';
       el.style.fontSize=Math.max(14,Math.min(21,14*zoom*height/850))+'px';
     }
     renderer.render(world.scene,camera);
   }
   requestAnimationFrame(render);
 }
 let drag=null;
 stage.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY};stage.setPointerCapture(e.pointerId);stage.classList.add('dragging');});
 stage.addEventListener('pointermove',e=>{if(!drag)return;pan(e.clientX-drag.x,e.clientY-drag.y);drag={x:e.clientX,y:e.clientY};});
 for(const event of ['pointerup','pointercancel'])stage.addEventListener(event,()=>{drag=null;stage.classList.remove('dragging');});
 stage.addEventListener('dblclick',()=>{if(busy){skipBatch=true;toast('跳过本批动画，点名结果会完整保留');}});
 stage.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(minZoom(),Math.min(3.4,zoom*Math.exp(-e.deltaY*.001)));setCamera();},{passive:false});
 stage.addEventListener('keydown',e=>{if(e.key==='F11'){e.preventDefault();toggleBoardFullscreen();return;}const d={ArrowLeft:[-45,0],ArrowRight:[45,0],ArrowUp:[0,-45],ArrowDown:[0,45]}[e.key];if(d){e.preventDefault();pan(...d);}});
 $('zoomIn').onclick=()=>{zoom=Math.min(3.4,zoom*1.15);setCamera();};$('zoomOut').onclick=()=>{zoom=Math.max(minZoom(),zoom/1.15);setCamera();};$('fit').onclick=fit;
 $('locate').onclick=()=>{const p=world.positions[position];desired.set(p.x,p.y,p.z);};
 async function toggleBoardFullscreen(){try{await api('native',{action:'board-fullscreen'});}catch(e){toast('全屏切换失败：'+e.message);}}
 $('fullscreen').onclick=toggleBoardFullscreen;
 window.addEventListener('resize',resize);
 $('countMinus').onclick=()=>{count=Math.max(1,count-1);update();};$('countPlus').onclick=()=>{count=Math.min(roster.length,count+1);update();};
 const dieView=new DiceView(T,$('centerDice'));
 function animate(ms,fn){if(skipBatch){fn(1);return Promise.resolve();}return new Promise(resolve=>{let start;function step(t){if(start===undefined)start=t;const p=skipBatch?1:Math.min(1,(t-start)/ms);fn(p);if(p>=1)resolve();else requestAnimationFrame(step);}requestAnimationFrame(step);});}
 async function dice(value){
   $('dice').setAttribute('aria-label','骰子点数 '+value);renderedRolls++;
   if(!presentation.Dice||skipBatch)return;
   const duration=presentation.DiceSeconds*1000;
   const overlay=$('diceStage'),flight=$('diceFlight'),cube=$('centerDice'),shadow=$('diceShadow');
   const origin=$('dice').getBoundingClientRect();
   const startX=origin.left+origin.width/2-width/2,startY=origin.top+origin.height/2-height/2;
   desired.copy(center);overlay.hidden=false;overlay.style.opacity='1';$('diceLanding').hidden=true;
   $('diceValue').textContent='';document.body.classList.add('is-rolling');
   try{
     await animate(duration*.66,p=>{
       const ease=1-Math.pow(1-p,3), travel=Math.min(1,p/.57), arrive=1-Math.pow(1-travel,3);
       const bounce=p<.57?Math.sin(travel*Math.PI)*-90:-Math.abs(Math.sin((p-.57)/.43*Math.PI*2))*30*(1-p)/.43;
       const x=startX*(1-arrive),y=startY*(1-arrive)+bounce;
       flight.style.transform='translate('+x+'px,'+y+'px) scale('+(.35+.65*arrive)+')';
       dieView.setRoll(value,p);
       shadow.style.transform='translate(-50%,-50%) translateX('+x+'px) scale('+(.5+.5*arrive-Math.abs(bounce)/250)+')';
       shadow.style.opacity=String(.12+.35*arrive);
     });
     dieView.setRoll(value,1);
     $('diceValue').textContent=value;$('diceLanding').hidden=false;
     await animate(duration*.24,()=>{});
     await animate(duration*.1,p=>{overlay.style.opacity=String(1-p);});
   }finally{overlay.hidden=true;document.body.classList.remove('is-rolling');}
 }
 async function reveal(type,name,isVip=false){
   if(!presentation.Highlight||skipBatch)return;
   $('revealType').textContent=type;$('revealName').textContent=name;
   const overlay=$('revealStage');overlay.classList.toggle('vip-reveal',isVip);overlay.hidden=false;
   overlay.style.opacity='0';document.body.classList.add('is-revealing');
   try{
     await animate(170,p=>{overlay.style.opacity=String(p);});
     await animate(presentation.HighlightSeconds*1000,()=>{});
     await animate(230,p=>{overlay.style.opacity=String(1-p);});
   }finally{overlay.hidden=true;document.body.classList.remove('is-revealing');}
 }
 async function move(steps){
   if(!presentation.Move||skipBatch){position=(position+steps)%entries.length;setPawn(world.positions[position]);return;}
   for(let i=0;i<steps;i++){
     const from=world.positions[position], next=(position+1)%entries.length,to=world.positions[next];
     await animate(presentation.MoveSeconds*1000/steps,p=>{const q=p*p*(3-2*p);setPawn({x:from.x+(to.x-from.x)*q,y:from.y+(to.y-from.y)*q,z:from.z+(to.z-from.z)*q},Math.sin(p*Math.PI)*.32);if(follow&&!drag)desired.set(to.x*.55+center.x*.45,1,to.z*.55+center.z*.45);});
     position=next;world.tiles[position].top.material.emissive.set('#936020');world.tiles[position].top.material.emissiveIntensity=.5;
     setTimeout(()=>{if(world.tiles[next])world.tiles[next].top.material.emissiveIntensity=0;},380);
   }
   setPawn(world.positions[position]);
 }
 async function openChest(index){const chest=world.chests.find(c=>c.index===index);if(!chest)return;await animate(410,p=>{chest.group.position.y=.24+Math.sin(p*Math.PI)*.2;chest.lid.rotation.x=-p*Math.PI*.62;});}

 async function closeChest(index){const chest=world.chests.find(c=>c.index===index);if(!chest)return;const angle=chest.lid.rotation.x;await animate(290,p=>{chest.lid.rotation.x=angle*(1-p);chest.group.position.y=.24;});}
 function result(type,name,note){$('result').hidden=false;$('resultType').textContent=type;$('resultName').textContent=name;$('resultNote').textContent=note;$('eventAction').hidden=true;}
 async function api(command,payload={}){
  const session=decodeURIComponent(window.location.pathname.split('/')[1]||'');
  const response=await fetch('api/'+command,{method:'POST',mode:'same-origin',referrerPolicy:'same-origin',headers:{'Content-Type':'application/json','X-Picker-Session':session},body:JSON.stringify({...payload,requestId:crypto.randomUUID()})});
  const data=await response.json();if(!response.ok)throw new Error(data.error||'主程序连接失败');return data;
 }
 function eventView(e){return {...e,title:e.Title,handled:e.Handled,action:e.Action};}
 function applyState(state){
  const changed=!backend||backend.layoutId!==state.layoutId||JSON.stringify(entries)!==JSON.stringify(state.slots);
  backend=state;roster=state.slots.filter(s=>s.kind==='student').map(s=>s.name);round=state.round;
  called=new Set(state.called);waitingVip=new Set(state.waitingVip);history=state.history;
  roundPeople=structuredClone(state.roundPeople||state.called.map(name=>({name,count:1,vip:false})));
  if(state.view){follow=state.view.Follow;presentation={...presentation,...state.view};}
  pendingEvents=state.events.map(eventView);count=Math.max(1,Math.min(count,roster.length));
  if(!roster.length){stage.hidden=true;$('loading').hidden=false;$('loading').textContent='名单为空，请到名单管理中添加学生';update();return;}
  stage.hidden=false;$('loading').hidden=true;
  if(changed)makeBoard(state.slots);
  position=state.position;setPawn(world.positions[position]);
  $('className').textContent=state.className;$('modeName').textContent=state.mode;
  $('rollStatus').textContent=state.pending?'请先在主界面处理上一批缺额':!state.eligible?'本轮暂无可抽学生':'准备就绪';
  update();eventButton();
 }
 async function sync(){if(busy)return;try{const state=await api('state');if(!busy)applyState(state);}catch(e){toast(e.message);}}
 function eventButton(){
  if(pendingEvents.some(e=>!e.handled)){
   $('result').hidden=false;$('eventAction').hidden=false;$('eventAction').textContent='处理宝箱事件';$('eventAction').onclick=eventDialog;
  }
 }
 async function rollBatch(requested=count){
  if(busy||!backend)return;
  busy=true;skipBatch=false;selected=-1;$('result').hidden=true;update();
  let response;
  try{
   response=await api('draw',{layoutId:backend.layoutId,position,count:requested});
   const people=[],events=[],rolls=response.batch.BoardRolls;
   for(let i=0;i<rolls.length;i++){
    const roll=rolls[i];$('rollStatus').textContent='第 '+(i+1)+' / '+rolls.length+' 颗骰子';
    await dice(roll.steps);await move(roll.steps);selected=position;
    const chest=roll.kind==='chest';
    try{
     if(chest&&presentation.Move&&!skipBatch)await openChest(position);
     if(roll.event)events.push(eventView(roll.event));
     if(roll.person){
      const p=roll.person;people.push(p);called.add(p.name);waitingVip.delete(p.name);rememberPerson(p);
      if(presentation.Direct){result(p.vip?'VIP 点名':'本次点名',p.name,p.vip?'VIP 必抽项已完成':'已到达姓名格');}
      update();
      if(presentation.Direct)await animate(presentation.DirectSeconds*1000,()=>{});
      await reveal(p.vip?'VIP 点名':'本次点名',p.name,p.vip);
     }else{
      const e=eventView(roll.event);
      if(presentation.Direct){result('特殊事件',e.title,e.handled?'事件已完成':'本批结束后由老师处理');await animate(presentation.DirectSeconds*1000,()=>{});}
      await reveal('特殊事件',e.title);
     }
    }finally{if(chest&&presentation.Move)await closeChest(position);}
   }
   applyState(response.state);
   {
    result('本批结果','','投掷 '+rolls.length+' 次 · 点名 '+people.length+' 人 · 宝箱事件 '+events.length+' 次');
    for(const p of people){const el=document.createElement('span');el.className='batch-chip'+(p.vip?' vip':'');el.textContent=p.name+(p.vip?' · VIP':'');$('resultName').append(el);}
    for(const e of events){const el=document.createElement('span');el.className='batch-chip';el.textContent='宝箱 · '+e.title;$('resultName').append(el);}
   }
   eventButton();
  }catch(e){
   toast(e.message);if(response){applyState(response.state);result('结果已保存','请查看点名记录','动画中断，实际结果仍保留在本地记录中');}else{try{applyState(await api('state'));}catch(_e){}}
  }finally{
   for(const c of world.chests){c.lid.rotation.x=0;c.group.position.y=.24;}
   if(response){try{await api('presented',{batchId:response.batch.Id});}catch(e){toast('结果已保存，主界面可稍后同步');}}
   busy=false;skipBatch=false;update();
  }
 }
 $('rollButton').onclick=()=>rollBatch();
 window.addEventListener('focus',sync);
 $('nextRound').onclick=async()=>{if(busy)return;try{applyState(await api('next-round',{layoutId:backend.layoutId}));toast('新一轮已开始，姓名和宝箱已重新排列');}catch(e){toast(e.message);}};
 function showDialog(title,html){$('dialogTitle').textContent=title;$('dialogBody').innerHTML=html;$('dialog').showModal();}
 $('closeDialog').onclick=()=>$('dialog').close();
 $('dialog').addEventListener('click',e=>{if(e.target===$('dialog')){const r=$('dialog').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('dialog').close();}});
 async function native(action){try{await api('native',{action});toast('已打开管理界面，返回棋盘后自动更新');}catch(e){toast(e.message);}}
 $('historyButton').onclick=()=>{
  showDialog('点名记录',history.length?'<div class="history-list">'+history.map(b=>'<div class="history-item"><div>第 '+b.round+' 轮 · '+b.people.map(p=>escapeHTML(p.name)+(p.vip?'（VIP）':'')).join('、')+(b.events.length?'<p>宝箱：'+b.events.map(e=>escapeHTML(e.title)).join('、')+'</p>':'')+'<p class="dialog-note">骰点：'+b.rolls.map(r=>r.steps).join('、')+'</p></div><time>'+escapeHTML(b.time)+'</time></div>').join('')+'</div>':'<p class="dialog-note">还没有点名记录。</p>');
 };
 const control=createPickerConsole({getState:()=>backend,api,applyState,showDialog,toast,native,escapeHTML});
 $('animationSettings').onclick=()=>control.open('view');
 $('settingsButton').onclick=()=>control.open('rules');$('rosterButton').onclick=()=>control.open('roster');
 function eventDialog(){
  const events=pendingEvents.filter(e=>!e.handled);
  showDialog('宝箱事件',events.map((e,i)=>'<div class="history-item"><span>'+escapeHTML(e.title)+'</span><button class="primary" data-event="'+i+'">'+(e.action==='reroll'?'手动投掷 1 颗':'选择学生')+'</button></div>').join('')||'<p class="dialog-note">没有待处理事件。</p>');
  $('dialogBody').querySelectorAll('[data-event]').forEach(button=>button.onclick=async()=>{
   const e=events[Number(button.dataset.event)];
   const resolve=async studentId=>{
    const state=await api('resolve-event',{batchId:e.batchId,eventId:e.EventId,studentId});
    applyState(state);$('dialog').close();
   };
   if(e.action==='reroll'){
    button.disabled=true;try{await resolve();await rollBatch(1);}catch(err){toast(err.message);button.disabled=false;}
   }else{
    showDialog('老师指定一人','<div class="name-grid">'+backend.available.map((p,i)=>'<button data-person="'+i+'">'+escapeHTML(p.name)+'</button>').join('')+'</div>');
    $('dialogBody').querySelectorAll('[data-person]').forEach(b=>b.onclick=async()=>{const p=backend.available[Number(b.dataset.person)];b.disabled=true;try{await resolve(p.id);result('老师指定',p.name,'已保存点名结果');eventButton();}catch(err){toast(err.message);b.disabled=false;}});
   }
  });
 }
 api('state').then(state=>{
  applyState(state);$('loading').hidden=state.total>0;requestAnimationFrame(render);
  requestAnimationFrame(async()=>{
   if(world)renderer.render(world.scene,camera);
   const backdrop=$('sceneBackdrop');
   if(backdrop.decode)await backdrop.decode().catch(()=>{});
   api('ready',{students:roster.length,slots:entries.length,compact:world?.compact||false,webgl:renderer.capabilities?.isWebGL2?2:1,version:'1.0',backgroundLoaded:!!backdrop.naturalWidth,backgroundTransparent:world?.scene.background===null&&!!renderer.getContext?.()?.getContextAttributes?.()?.alpha}).catch(()=>{});
  });
 }).catch(e=>{$('loading').textContent='棋盘连接未成功：'+e.message+' 请重新启动 V1.0。';});
 window.previewInfo=()=>({students:roster.length,chests:entries.filter(s=>s.kind==='chest').length,slots:entries.length,position,renderedRolls,busy,openChests:world?.chests.filter(c=>Math.abs(c.lid.rotation.x)>.001).length});
})();
