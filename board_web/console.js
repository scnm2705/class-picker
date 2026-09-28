(function(root){
 'use strict';
 root.createPickerConsole=function(ctx){
  const $=id=>document.getElementById(id),esc=ctx.escapeHTML,prob=root.PickerProbability;
  const check=(id,label,value)=>'<label class="field">'+label+'<input id="'+id+'" type="checkbox" '+(value?'checked':'')+'></label>';
  const number=(id,label,value,step='1')=>'<label class="field">'+label+'<input id="'+id+'" type="number" step="'+step+'" value="'+value+'"></label>';
  const effects=[['Direct','直接显示','落格后显示结果卡，按设定时间停留。'],['Dice','骰子动画','每颗骰子的投掷、点数停留与淡出总时长。'],['Move','移动动画','每颗骰子走完所有格子的总时长。'],['Highlight','名字凸显','在屏幕中央显示大字，时长为完整可读的停留时间。']];
  function open(tab='rules'){
   const state=ctx.getState();if(!state){ctx.toast('请等待班级加载');return;}
   const draft=structuredClone(state.settings),rules=state.rules,view=state.view;
   ctx.showDialog('控制台','<nav class="console-tabs" aria-label="控制台分类">'+[['rules','抽取规则'],['chests','宝箱内容'],['roster','名单与 VIP'],['view','显示'],['more','更多']].map(([id,title])=>'<button data-tab="'+id+'">'+title+'</button>').join('')+'</nav>'+
    '<section data-pane="rules"><label class="field">当前抽取模式<select id="ruleMode">'+['不重复','普通','均衡'].map(m=>'<option '+(m===rules.mode?'selected':'')+'>'+m+'</option>').join('')+'</select></label>'+check('vipEnabled','启用 VIP 必抽安排',rules.VipEnabled)+number('vipQuota','每批 VIP 人数',rules.VipPerBatch)+check('vipFill','VIP 不足时由普通人员补齐',rules.FillVipShortage)+check('vipRandom','多人 VIP 随机抽取',rules.VipRandomForGroups)+check('keepAbsent','重开后保留临时缺席',rules.KeepAbsenceOnRestart)+'<h3>均衡模式权重</h3>'+number('baseWeight','基础权重',rules.BaseWeight,'0.05')+number('weightGrowth','每批未中增长',rules.Growth,'0.01')+number('maxWeight','权重上限',rules.MaxWeight,'0.05')+'<p class="dialog-note">每颗骰子只考虑前方 1～6 格。切换模式会进入该模式已有的轮次和棋盘。保存权重后按原有有效等待次数计算，历史记录保留。</p></section>'+
    '<section data-pane="chests">'+number('chestChance','普通宝箱格概率 %',draft.ChestChance,'0.1')+'<p class="dialog-note">VIP 必抽始终进入宝箱。前方没有可抽姓名时，概率大于 0 会进入宝箱；为 0 则停止。随机学生从全班可参与名单中按原模式概率抽取，仍遵守缺席、不重复及 VIP 规则。</p>'+check('smartProbability','智能配平：修改一项，其余按原比例调整',true)+'<div class="event-head"><span>宝箱内容</span><span>执行方式</span><span>概率 %</span></div><div id="eventRows"></div><div class="probability-tools"><button id="addEvent">＋ 自定义内容</button><button id="randomProbability">调整至随机概率</button></div><p id="probTotal" class="dialog-note"></p><p class="dialog-note">修改后点击“保存设置”生效。智能配平保持合计 100%；其余项原概率都为 0 时均分剩余概率。</p></section>'+
    '<section data-pane="roster"><p class="dialog-note">姓名、VIP、移出及恢复操作即时保存。改名保留学号与点名记录；同名学生在棋盘上自动加标识区分。导入导出及缺席登记在“更多”中打开完整管理。</p><input id="rosterSearch" class="console-search" placeholder="搜索姓名" aria-label="搜索姓名"><div id="consoleRoster"></div></section>'+
    '<section data-pane="view">'+check('followOption','镜头跟随棋子',view.Follow)+'<h3>点名显示与动画</h3><p class="dialog-note">四项可任意组合，也可全部关闭。播放顺序：骰子 → 移动 → 直接显示 → 名字凸显。右侧名单与本批结果始终保留。</p>'+effects.map(([key,title,note])=>'<div class="effect-option">'+check('effect'+key,title,view[key])+'<label class="field">'+(key==='Direct'||key==='Highlight'?'停留时间':'总时长')+'（秒）<input id="time'+key+'" type="number" min="0.1" max="60" step="0.1" value="'+view[key+'Seconds']+'"></label><p class="dialog-note">'+note+'</p></div>').join('')+'</section>'+
    '<section data-pane="more"><p class="dialog-note">常用抽取、VIP、宝箱和显示设置均可直接在控制台完成。</p><button class="primary" id="advancedManager">打开完整管理界面</button><p class="dialog-note">用于班级管理、名单导入导出、缺席登记、补抽、数据备份与恢复。</p></section><div class="console-save"><p id="consoleError" class="error-text" role="status"></p><button class="primary" id="saveConsole">保存设置</button></div>');
   function choose(id){$('dialogBody').querySelectorAll('[data-pane]').forEach(el=>el.hidden=el.dataset.pane!==id);$('dialogBody').querySelectorAll('[data-tab]').forEach(el=>el.setAttribute('aria-selected',String(el.dataset.tab===id)));}
   $('dialogBody').querySelectorAll('[data-tab]').forEach(el=>el.onclick=()=>choose(el.dataset.tab));choose(tab);
   function total(){$('probTotal').textContent='概率合计：'+Math.round(draft.Events.reduce((sum,e)=>sum+Number(e.Weight||0),0)*100)/100+'%';}
   function assign(weights){weights.forEach((w,i)=>draft.Events[i].Weight=w);}
   function rows(){
    $('eventRows').innerHTML=draft.Events.map((e,i)=>'<div class="event-row"><input data-title="'+i+'" aria-label="宝箱内容" maxlength="80" value="'+esc(e.Title)+'"><select data-action="'+i+'" aria-label="执行方式">'+[['message','仅展示'],['reroll','手动再掷'],['teacher','老师指定'],['random_student','随机学生'],['skip','跳过']].map(([a,t])=>'<option value="'+a+'" '+(a===e.Action?'selected':'')+'>'+t+'</option>').join('')+'</select><input data-weight="'+i+'" aria-label="概率" type="number" min="0" max="100" step="0.1" value="'+e.Weight+'"><button data-delete="'+i+'" aria-label="删除" '+(draft.Events.length===1?'disabled':'')+'>×</button></div>').join('');
    $('eventRows').querySelectorAll('[data-title]').forEach(el=>el.oninput=()=>draft.Events[el.dataset.title].Title=el.value);
    $('eventRows').querySelectorAll('[data-action]').forEach(el=>el.onchange=()=>draft.Events[el.dataset.action].Action=el.value);
    $('eventRows').querySelectorAll('[data-weight]').forEach(el=>{
     el.onfocus=()=>{el.originalWeights=draft.Events.map(e=>e.Weight);};
     el.oninput=()=>{
      const value=Number(el.value);if(el.value===''||!Number.isFinite(value)||value<0||value>100)return;
      if($('smartProbability').checked){assign(prob.rebalance(el.originalWeights||draft.Events.map(e=>e.Weight),Number(el.dataset.weight),value));$('eventRows').querySelectorAll('[data-weight]').forEach(other=>{if(other!==el)other.value=String(draft.Events[other.dataset.weight].Weight);});}
      else draft.Events[el.dataset.weight].Weight=value;
      total();
     };
     el.onblur=()=>{el.value=String(draft.Events[el.dataset.weight].Weight);};
    });
    $('eventRows').querySelectorAll('[data-delete]').forEach(el=>el.onclick=()=>{if(draft.Events.length===1)return;draft.Events.splice(Number(el.dataset.delete),1);if($('smartProbability').checked)assign(prob.allocate(draft.Events.map(e=>e.Weight)));rows();});total();
   }
   rows();$('addEvent').onclick=()=>{if(draft.Events.length<30){draft.Events.push({Id:crypto.randomUUID(),Title:'自定义课堂事件',Weight:0,Action:'message'});rows();}};
   $('randomProbability').onclick=()=>{assign(prob.randomize(draft.Events.length));rows();};
   $('smartProbability').onchange=()=>{if($('smartProbability').checked){assign(prob.allocate(draft.Events.map(e=>e.Weight)));rows();}};
   function roster(){
    const items=ctx.getState().roster.filter(s=>s.name.includes($('rosterSearch').value.trim()));
    $('consoleRoster').innerHTML=items.map((s,i)=>'<div class="console-person"><div class="person-name"><input data-name="'+i+'" aria-label="修改 '+esc(s.name)+' 的姓名" maxlength="80" value="'+esc(s.rawName||s.name)+'"><small>'+esc(s.name)+(s.archived?' · 已移出':s.absent?' · 缺席':s.held?' · 本轮 VIP 已完成':'')+'</small></div><div class="person-actions"><button data-rename="'+i+'">保存姓名</button><label>VIP <input type="checkbox" data-vip="'+i+'" '+(s.vip?'checked':'')+' '+(s.held||s.archived?'disabled':'')+'></label><button data-archive="'+i+'">'+(s.archived?'恢复':'移出')+'</button></div></div>').join('');
    $('consoleRoster').querySelectorAll('[data-rename]').forEach(el=>el.onclick=async()=>{
     const i=Number(el.dataset.rename),input=Array.from($('consoleRoster').querySelectorAll('[data-name]')).find(e=>Number(e.dataset.name)===i);
     el.disabled=true;try{ctx.applyState(await ctx.api('rename',{layoutId:ctx.getState().layoutId,studentId:items[i].id,name:input.value}));$('consoleError').textContent='姓名已保存';roster();}catch(e){$('consoleError').textContent=e.message;el.disabled=false;}
    });
    $('consoleRoster').querySelectorAll('[data-archive]').forEach(el=>el.onclick=async()=>{
     const s=items[Number(el.dataset.archive)];el.disabled=true;try{ctx.applyState(await ctx.api('archive',{layoutId:ctx.getState().layoutId,studentId:s.id,archived:!s.archived}));$('consoleError').textContent=s.archived?'已恢复':'已移出，可随时恢复';}catch(e){$('consoleError').textContent=e.message;}finally{roster();}
    });
    $('consoleRoster').querySelectorAll('[data-vip]').forEach(el=>el.onchange=async()=>{
     el.disabled=true;try{ctx.applyState(await ctx.api('vip',{layoutId:ctx.getState().layoutId,studentId:items[el.dataset.vip].id,enabled:el.checked}));$('consoleError').textContent='VIP 安排已保存';}
     catch(e){$('consoleError').textContent=e.message;}finally{roster();}
    });
   }
   roster();$('rosterSearch').oninput=roster;
   $('advancedManager').onclick=()=>{$('dialog').close();ctx.native('original');};
   $('saveConsole').onclick=async()=>{
    const rules={mode:$('ruleMode').value,VipEnabled:$('vipEnabled').checked,VipPerBatch:Number($('vipQuota').value),FillVipShortage:$('vipFill').checked,VipRandomForGroups:$('vipRandom').checked,KeepAbsenceOnRestart:$('keepAbsent').checked,BaseWeight:Number($('baseWeight').value),Growth:Number($('weightGrowth').value),MaxWeight:Number($('maxWeight').value)};
    draft.ChestChance=Number($('chestChance').value);$('saveConsole').disabled=true;
    const view={Follow:$('followOption').checked};
    for(const [key] of effects){view[key]=$('effect'+key).checked;view[key+'Seconds']=Number($('time'+key).value);}
    try{ctx.applyState(await ctx.api('console',{layoutId:ctx.getState().layoutId,rules,settings:draft,view}));$('dialog').close();ctx.toast('控制台设置已保存');}
    catch(e){$('consoleError').textContent=e.message;}finally{$('saveConsole').disabled=false;}
   };
  }
  return {open};
 };
})(typeof window!=='undefined'?window:globalThis);
