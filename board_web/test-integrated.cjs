// Pure geometry and fake-DOM integration checks. No browser or GPU is driven here.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const M=require('./board-model.js'),T=require('./vendor/three.min.js'),solid=require('./dice.js');
global.PickerModel=M;const createWorld=require('./scene.js');
const geometry=solid.roundedGeometry(T),p=geometry.attributes.position,idx=geometry.index;
const key=i=>[p.getX(i),p.getY(i),p.getZ(i)].map(n=>n.toFixed(6)).join(',');
const edges=new Map();
for(let i=0;i<idx.count;i+=3){const tri=[idx.getX(i),idx.getX(i+1),idx.getX(i+2)];for(let j=0;j<3;j++){const pair=[key(tri[j]),key(tri[(j+1)%3])].sort().join('|');edges.set(pair,(edges.get(pair)||0)+1);}}
assert.ok([...edges.values()].every(n=>n===2),'die body must be watertight, including beveled corners');
for(let value=1;value<=6;value++){const up=new T.Vector3(...solid.normals[value]).applyQuaternion(solid.pose(T,value));assert.ok(up.distanceTo(new T.Vector3(0,1,0))<1e-6,'wrong upper result face');}
for(let count=2;count<200;count++)assert.equal(M.routePositions(count).length,count);
let time=0,raf=[],timers=[],modalCalls=0,apiCasts=0,audioStarts=0,nativeActions=[],nextKind='vip';
class Element{
 constructor(){this.hidden=false;this.style={};this.children=[];this.dataset={};this.attrs={};this.textContent='';this.set=new Set();this.classList={add:(...x)=>x.forEach(v=>this.set.add(v)),remove:(...x)=>x.forEach(v=>this.set.delete(v)),toggle:(x,on)=>{if(on===undefined)on=!this.set.has(x);if(on)this.set.add(x);else this.set.delete(x);},contains:x=>this.set.has(x)};}
 append(...x){this.children.push(...x)}replaceChildren(...x){this.children=x}addEventListener(type,fn){(this.handlers??={})[type]=fn}setAttribute(k,v){this.attrs[k]=v}getBoundingClientRect(){return{left:1130,top:740,width:44,height:44}}showModal(){modalCalls++}close(){}setPointerCapture(){}
}
const elements={},html=fs.readFileSync(__dirname+'/index.html','utf8');
for(const match of html.matchAll(/<[^>]+id="([^"]+)"[^>]*>/g)){elements[match[1]]=new Element();elements[match[1]].hidden=/\bhidden\b/.test(match[0]);}
const body=new Element(),hint=new Element();
const document={body,getElementById:id=>{assert.ok(elements[id],'missing DOM: '+id);return elements[id]},createElement:()=>new Element(),querySelector:()=>hint};
class Renderer{constructor(){this.shadowMap={};this.domElement=new Element()}setPixelRatio(){}setSize(){}render(){}}
class AudioParam{setValueAtTime(){}exponentialRampToValueAtTime(){}}
class AudioContext{constructor(){this.currentTime=0;this.state='running';this.destination={}}resume(){}createOscillator(){return{frequency:new AudioParam(),connect(){},start(){audioStarts++},stop(){}}}createGain(){return{gain:new AudioParam(),connect(){}}}}
const window={THREE:{...T,WebGLRenderer:Renderer},AudioContext,devicePixelRatio:1,location:{pathname:'/test-session/index.html'},handlers:{},addEventListener(type,fn){this.handlers[type]=fn}};
const slots=M.buildBoard(M.names),saved={className:'测试',mode:'不重复',round:1,layoutId:'demo',slots,position:0,total:50,called:[],waitingVip:[],history:[],events:[],eligible:50,available:[],settings:{ChestChance:100,Events:[]}};
const fetch=async(url,options)=>{
 const req=JSON.parse(options.body);let data;
 assert.equal(options.headers['X-Picker-Session'],'test-session');
 if(url==='api/state')data=structuredClone(saved);
 else if(url==='api/presented'||url==='api/ready')data={ok:true};
 else if(url==='api/native'){nativeActions.push(req.action);data={ok:true};}
 else if(url==='api/draw'){
  apiCasts++;const rolls=[];
  for(let i=0;i<req.count;i++){
   const targetKind=nextKind==='student'?'student':'chest';
   const step=Array.from({length:6},(_,k)=>k+1).find(k=>slots[(saved.position+k)%slots.length].kind===targetKind);
   const from=saved.position;saved.position=(from+step)%slots.length;
   if(nextKind==='event')rolls.push({from,to:saved.position,steps:step,kind:'chest',event:{Title:'分享一个发现',Handled:true,Action:'message'}});
   else{const person={name:M.names[saved.called.length],vip:nextKind==='vip'};saved.called.push(person.name);rolls.push({from,to:saved.position,steps:step,kind:targetKind,person,...(nextKind==='random'?{event:{Title:'随机学生',Handled:true,Action:'random_student'}}:{})});}
  }
  data={batch:{BoardRolls:rolls},state:structuredClone(saved)};
 }else throw Error(url);
 return {ok:true,json:async()=>data};
};
const context={document,window,PickerModel:M,createBoardWorld:createWorld,innerWidth:1440,innerHeight:900,devicePixelRatio:1,performance:{now:()=>time},console,fetch,structuredClone,crypto:require('node:crypto').webcrypto,requestAnimationFrame:fn=>raf.push(fn),setTimeout:(fn,delay)=>{timers.push({fn,end:time+delay});return timers.length},clearTimeout(){},confirm(){throw Error('unexpected confirmation');}};
vm.runInNewContext(fs.readFileSync(__dirname+'/dice.js','utf8'),context);context.DiceView=window.DiceView;
vm.runInNewContext(fs.readFileSync(__dirname+'/probability.js','utf8'),context);
vm.runInNewContext(fs.readFileSync(__dirname+'/console.js','utf8'),context);context.createPickerConsole=window.createPickerConsole;
let source=fs.readFileSync(__dirname+'/app.js','utf8').replace(' window.previewInfo=', ' window.testFunctions={rollBatch,applyState,getCalled:()=>called.size};\n window.previewInfo=');vm.runInNewContext(source,context);
async function run(promise,observe=()=>{}){
 let finished=false,error;promise.then(()=>finished=true,e=>{finished=true;error=e});
 for(let n=0;n<4500&&!finished;n++){time+=16;const cb=raf;raf=[];cb.forEach(fn=>fn(time));const due=timers.filter(t=>t.end<=time);timers=timers.filter(t=>t.end>time);due.forEach(t=>t.fn());await Promise.resolve();await Promise.resolve();observe();}
 assert.ok(finished,'animation did not finish');if(error)throw error;
}
(async()=>{
 for(let i=0;i<12;i++)await Promise.resolve();
 assert.equal(window.previewInfo().slots,60);
 saved.pending=false;
 assert.equal(elements.animationSettings.hidden,false);assert.equal(elements.fastForward,undefined);
 await elements.fullscreen.onclick();assert.deepEqual(nativeActions,['board-fullscreen']);
 const start=window.previewInfo().position;let centralFrames=0,revealFrames=0;
 await run(window.testFunctions.rollBatch(1),()=>{
  if(!elements.diceStage.hidden){centralFrames++;assert.equal(window.testFunctions.getCalled(),0);assert.equal(elements.roundPeopleList.children.length,0);assert.equal(window.previewInfo().position,start);}
  if(!elements.revealStage.hidden){revealFrames++;assert.equal(window.testFunctions.getCalled(),1);assert.equal(elements.roundPeopleList.children.length,1);assert.equal(elements.diceStage.hidden,true);assert.equal(window.previewInfo().position,(start+Number(elements.diceValue.textContent))%60);}
 });
 assert.ok(centralFrames>5&&revealFrames>5);
 assert.equal(window.previewInfo().openChests,0,'chest left open');
 const initial=window.previewInfo().renderedRolls;await run(window.testFunctions.rollBatch(3));
 assert.equal(window.previewInfo().renderedRolls-initial,3);assert.equal(window.previewInfo().openChests,0);
 for(let mask=0;mask<16;mask++){
  const view={Follow:true,DirectSeconds:.7,DiceSeconds:.5,MoveSeconds:.6,HighlightSeconds:1.3};
  ['Direct','Dice','Move','Highlight'].forEach((key,i)=>view[key]=!!(mask&(1<<i)));
  saved.view=view;window.testFunctions.applyState(structuredClone(saved));
  const before=time,calledBefore=window.testFunctions.getCalled();let diceFrames=0,highlightFrames=0,readableFrames=0,directFrames=0;
  await run(window.testFunctions.rollBatch(1),()=>{
   if(!elements.diceStage.hidden){diceFrames++;assert.equal(window.testFunctions.getCalled(),calledBefore);}
   if(!elements.revealStage.hidden){highlightFrames++;if(elements.revealStage.style.opacity==='1')readableFrames++;}
   if(!elements.result.hidden&&elements.resultType.textContent==='VIP 点名')directFrames++;
  });
  assert.equal(diceFrames>0,view.Dice);assert.equal(highlightFrames>0,view.Highlight);assert.equal(directFrames>0,view.Direct);
  if(view.Highlight)assert.ok(readableFrames*16>=1300,'center name must remain readable for selected hold time');
  if(view.Move)assert.ok(time-before>=600,'movement duration must not be skipped');
  if(!mask)assert.ok(time-before<250,'all unchecked must have no timed presentation');
  assert.equal(window.previewInfo().position,saved.position);assert.equal(window.testFunctions.getCalled(),calledBefore+1);
  assert.equal(elements.result.hidden,false);assert.equal(window.previewInfo().openChests,0);
 }
 saved.view={...saved.view,Direct:false,Dice:false,Move:false,Highlight:true,HighlightSeconds:4};window.testFunctions.applyState(structuredClone(saved));
 let readableFrames=0;await run(window.testFunctions.rollBatch(2),()=>{if(!elements.revealStage.hidden&&elements.revealStage.style.opacity==='1')readableFrames++;});
 assert.ok(readableFrames*16>=8000,'two names must each hold for four seconds');
 assert.equal(elements.diceStage.hidden,true);assert.equal(elements.revealStage.hidden,true);assert.equal(modalCalls,0);assert.equal(apiCasts,19);
 saved.view.Highlight=false;window.testFunctions.applyState(structuredClone(saved));nextKind='event';
 const beforeEvent=window.testFunctions.getCalled();await run(window.testFunctions.rollBatch(1));
 assert.equal(window.testFunctions.getCalled(),beforeEvent);assert.ok(elements.resultName.children.some(c=>c.textContent==='宝箱 · 分享一个发现'));
 nextKind='student';await run(window.testFunctions.rollBatch(1));assert.equal(window.testFunctions.getCalled(),beforeEvent+1);assert.equal(window.previewInfo().position,saved.position);
 assert.equal(elements.refreshState,undefined,'manual sync button must be removed');
 saved.className='从管理界面修改';await window.handlers.focus();assert.equal(elements.className.textContent,saved.className);
 nextKind='random';await run(window.testFunctions.rollBatch(1));assert.ok(elements.resultName.children.some(c=>c.textContent==='宝箱 · 随机学生'));
 nextKind='vip';
 for(const phase of ['request','dice','move','direct','highlight','chest']){
  saved.view={Follow:true,Direct:true,Dice:phase==='dice',Move:phase==='move'||phase==='chest',Highlight:true,DirectSeconds:phase==='direct'?60:.1,DiceSeconds:60,MoveSeconds:phase==='move'?60:.2,HighlightSeconds:60};
  window.testFunctions.applyState(structuredClone(saved));const beforeCalls=apiCasts,beforePeople=saved.called.length;let skippedAt=null,startTime=time;
  const promise=window.testFunctions.rollBatch(2);
  if(phase==='request'){elements.stage.handlers.dblclick();skippedAt=time;}
  await run(promise,()=>{
   const ready=phase==='dice'&&!elements.diceStage.hidden||phase==='move'&&time-startTime>150||phase==='direct'&&!elements.result.hidden||phase==='highlight'&&!elements.revealStage.hidden||phase==='chest'&&window.previewInfo().openChests>0;
   if(skippedAt===null&&ready){elements.stage.handlers.dblclick();skippedAt=time;}
  });
  assert.notEqual(skippedAt,null,'skip phase reached');assert.ok(time-skippedAt<500,'skip must promptly finish entire batch');
  assert.equal(apiCasts,beforeCalls+1);assert.equal(window.testFunctions.getCalled(),beforePeople+2);assert.equal(window.previewInfo().position,saved.position);
  assert.equal(window.previewInfo().busy,false);assert.equal(window.previewInfo().openChests,0);assert.equal(elements.rollButton.disabled,false);
  assert.equal(elements.diceStage.hidden,true);assert.equal(elements.revealStage.hidden,true);assert.equal(elements.result.hidden,false);
 }
 // A skip is local to its batch; the next chosen highlight must still run.
 saved.view={...saved.view,Move:false,Dice:false,Direct:false,Highlight:true,HighlightSeconds:1};window.testFunctions.applyState(structuredClone(saved));
 let nextReadable=0;await run(window.testFunctions.rollBatch(1),()=>{if(!elements.revealStage.hidden&&elements.revealStage.style.opacity==='1')nextReadable++;});assert.ok(nextReadable*16>=1000);
 assert.equal(audioStarts,0,'no sound may play');
 console.log(JSON.stringify({result:'PASS',combinations:16,skipPhases:6,centralFrames,revealFrames,audioStarts,checks:['all presentation combinations','independent readable hold time','whole batch skip retains results','next batch animations unaffected','auto sync on returning to board','random student event and name retained','correct landing and closed chests','native fullscreen request','no audio'],visualBrowserVerified:false},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
