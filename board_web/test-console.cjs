// Exercise the console form in a minimal DOM; no browser UI automation.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map();
class Element{
 constructor(attrs={}){this.attrs=attrs;this.dataset={};this.value=attrs.value||'';this.checked='checked'in attrs;this.hidden=false;this.disabled=false;this.children=[];for(const[k,v]of Object.entries(attrs))if(k.startsWith('data-'))this.dataset[k.slice(5)]=v;}
 set innerHTML(html){this.children=[];for(const m of html.matchAll(/<(input|select|button|section|div|p|nav)\b([^>]*)>/g)){
  const attrs={};for(const a of m[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g))attrs[a[1]]=a[2]||'';
  const el=new Element(attrs);this.children.push(el);if(attrs.id)elements.set(attrs.id,el);
  if(m[1]==='select'){const end=html.indexOf('</select>',m.index),body=html.slice(m.index+m[0].length,end);const options=[...body.matchAll(/<option([^>]*)>([^<]*)/g)];const chosen=options.find(o=>o[1].includes('selected'))||options[0];el.value=chosen?.[1].match(/value="([^"]*)"/)?.[1]||chosen?.[2]||'';}
 }}
 querySelectorAll(selector){const attr=selector.slice(1,-1);return this.children.filter(e=>attr in e.attrs);}
 setAttribute(k,v){this.attrs[k]=v}close(){this.closed=true}
}
elements.set('dialog',new Element());elements.set('dialogBody',new Element());
let nativeCalls=0,savedPayload;
let state={layoutId:'layout',settings:{ChestChance:20,Events:[{Id:'one',Title:'课堂事件',Weight:100,Action:'message'}]},view:{Follow:true,Pace:1},rules:{mode:'不重复',VipEnabled:true,VipPerBatch:1,FillVipShortage:true,VipRandomForGroups:false,KeepAbsenceOnRestart:true,BaseWeight:1,Growth:.05,MaxWeight:2},roster:[{id:'a',name:'张三',vip:false,absent:false,held:false}]};
const window={},context={window,document:{getElementById:id=>{assert.ok(elements.has(id),'missing '+id);return elements.get(id)}},structuredClone,crypto:require('node:crypto').webcrypto};
vm.runInNewContext(fs.readFileSync(__dirname+'/probability.js','utf8'),context);
vm.runInNewContext(fs.readFileSync(__dirname+'/console.js','utf8'),context);
const control=window.createPickerConsole({getState:()=>state,escapeHTML:String,toast(){},native(){nativeCalls++},showDialog(title,html){assert.equal(title,'控制台');elements.get('dialogBody').innerHTML=html;},applyState:s=>{state=s},api:async(command,payload)=>{savedPayload={command,payload};return {...state,rules:payload.rules||state.rules,settings:payload.settings||state.settings,view:payload.view||state.view};}});
(async()=>{
 control.open('rules');assert.equal(nativeCalls,0);
 assert.equal(elements.get('ruleMode').value,'不重复');
 elements.get('ruleMode').value='均衡';elements.get('vipQuota').value='3';elements.get('followOption').checked=false;
 for(const key of ['Direct','Dice','Move','Highlight']){elements.get('effect'+key).checked=key==='Highlight';elements.get('time'+key).value='4.5';}
 await elements.get('saveConsole').onclick();
 assert.equal(savedPayload.command,'console');assert.equal(savedPayload.payload.rules.VipPerBatch,3);assert.equal(savedPayload.payload.rules.mode,'均衡');assert.equal(savedPayload.payload.view.HighlightSeconds,4.5);assert.equal(savedPayload.payload.view.Highlight,true);assert.equal(savedPayload.payload.view.Dice,false);assert.equal(nativeCalls,0);
 control.open('view');assert.equal(elements.get('effectHighlight').checked,true);assert.equal(elements.get('effectDice').checked,false);assert.equal(elements.get('timeHighlight').value,'4.5');
 control.open('roster');const toggle=elements.get('consoleRoster').querySelectorAll('[data-vip]')[0];toggle.checked=true;await toggle.onchange();
 assert.equal(savedPayload.command,'vip');assert.equal(savedPayload.payload.studentId,'a');assert.equal(nativeCalls,0);
 control.open('roster');const rename=elements.get('consoleRoster').querySelectorAll('[data-rename]')[0];elements.get('consoleRoster').querySelectorAll('[data-name]')[0].value='新姓名';await rename.onclick();
 assert.equal(savedPayload.command,'rename');assert.equal(savedPayload.payload.name,'新姓名');assert.equal(savedPayload.payload.studentId,'a');
 const archive=elements.get('consoleRoster').querySelectorAll('[data-archive]')[0];await archive.onclick();assert.equal(savedPayload.command,'archive');assert.equal(savedPayload.payload.archived,true);
 state.settings.Events=[{Id:'one',Title:'A',Weight:30,Action:'random_student'},{Id:'two',Title:'B',Weight:20,Action:'message'},{Id:'three',Title:'C',Weight:50,Action:'skip'}];
 control.open('chests');let weights=elements.get('eventRows').querySelectorAll('[data-weight]');
 weights[0].onfocus();weights[0].value='40';weights[0].oninput();weights[0].onblur();assert.equal(Number(weights[1].value),17.1);assert.equal(Number(weights[2].value),42.9);
 await elements.get('saveConsole').onclick();assert.deepEqual(Array.from(savedPayload.payload.settings.Events,e=>e.Weight),[40,17.1,42.9]);assert.equal(savedPayload.payload.settings.Events[0].Action,'random_student');
 control.open('chests');elements.get('smartProbability').checked=false;weights=elements.get('eventRows').querySelectorAll('[data-weight]');weights[0].value='10';weights[0].oninput();assert.equal(Number(weights[1].value),17.1);
 elements.get('randomProbability').onclick();await elements.get('saveConsole').onclick();const randomized=savedPayload.payload.settings.Events.map(e=>e.Weight);assert.equal(randomized.reduce((sum,w)=>sum+Math.round(w*10),0),1000);
 assert.equal(nativeCalls,0);
 console.log(JSON.stringify({result:'PASS',checks:['console renders all settings','save typed rules and view in one request','VIP editing remains in 3D','no forced native interface']}));
})().catch(e=>{console.error(e);process.exitCode=1});
