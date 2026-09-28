(function (root) {
  'use strict';
  const names = '张子辰 李明轩 王一诺 赵嘉宁 陈宇航 刘思远 周梓涵 孙雨桐 吴俊熙 郑可欣 冯浩然 褚星宇 卫安然 蒋若宁 沈亦帆 韩乐言 杨书瑶 朱景行 秦予安 尤清越 许知夏 何沐阳 吕星河 施语宁 孔文博 曹以恒 严晨曦 华锦程 金若溪 魏承宇 陶书言 姜南星 戚明哲 谢云舒 邹逸辰 喻子墨 柏初晴 水安宁 窦清扬 章致远 云泽宇 苏言希 潘奕宁 葛星野 奚嘉禾 范可然 彭书墨 郎雨泽 鲁以宁 韦景澄'.split(' ');
  function randomInt(max) {
    if (!Number.isInteger(max) || max < 1) throw new Error('随机范围无效');
    if (globalThis.crypto && crypto.getRandomValues) {
      const n = new Uint32Array(1), cap = Math.floor(4294967296 / max) * max;
      do { crypto.getRandomValues(n); } while (n[0] >= cap);
      return n[0] % max;
    }
    return Math.floor(Math.random() * max);
  }
  function shuffle(list, rng = randomInt) {
    const result = list.slice();
    for (let i = result.length - 1; i > 0; i--) { const j = rng(i + 1); [result[i], result[j]] = [result[j], result[i]]; }
    return result;
  }
  function buildBoard(roster, rng = randomInt) {
    if (roster.length < 12 || roster.length > 90) throw new Error('预览支持 12～90 个姓名');
    if (new Set(roster).size !== roster.length) throw new Error('姓名不能重复，请检查名单');
    if (roster.some(n => !n.trim() || n.length > 8)) throw new Error('每个姓名请输入 1～8 个字');
    const students = shuffle(roster, rng), count = Math.max(1, Math.ceil(students.length / 5));
    const sizes = Array.from({length: count}, (_, i) => Math.floor(students.length / count) + (i < students.length % count ? 1 : 0));
    for (let i = 0; i < count; i++) {
      const j = rng(count);
      if (i !== j && sizes[i] > 4 && sizes[j] < 5) { sizes[i]--; sizes[j]++; }
    }
    const slots = []; let cursor = 0;
    for (let i = 0; i < sizes.length; i++) {
      for (let j = 0; j < sizes[i]; j++) slots.push({kind:'student', name:students[cursor++], id:students[cursor-1]});
      slots.push({kind:'chest', id:'chest-' + i, color:i % 2 ? 'gold' : 'purple'});
    }
    const offset=rng(slots.length);
    return slots.slice(offset).concat(slots.slice(0,offset));
  }
  function routePositions(count) {
    if(count<8){const r=Math.max(2.2,count*2.5/(2*Math.PI));return Array.from({length:count},(_,i)=>({x:count===2?i*1.9-.95:Math.cos(i*Math.PI*2/count)*r,y:.9,z:count===2?0:Math.sin(i*Math.PI*2/count)*r}));}
    if(count<48){
      const a=Math.max(2,Math.floor(count*.3)),b=Math.floor((count-2*a)/2),steps=[a,b,a,count-2*a-b];
      const w=Math.max(steps[0],steps[2])*1.9,h=Math.max(steps[1],steps[3])*1.9,v=[[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]],result=[];
      for(let i=0;i<4;i++)for(let j=0;j<steps[i];j++){const p=v[i],q=v[(i+1)%4],t=j/steps[i];result.push({x:p[0]+(q[0]-p[0])*t,y:.9+(i<2?.25:0),z:p[1]+(q[1]-p[1])*t});}
      return result;
    }
    const v = [[0,0],[15,0],[15,9],[10,9],[10,3],[6,3],[6,9],[0,9]];
    const lengths = v.map((p,i) => { const q=v[(i+1)%v.length]; return Math.abs(q[0]-p[0])+Math.abs(q[1]-p[1]); });
    const exact=lengths.map(n=>n/60*count), steps=exact.map(n=>Math.max(1,Math.floor(n)));
    const order=exact.map((n,i)=>({i,r:n-Math.floor(n)})).sort((a,b)=>b.r-a.r);
    let remaining=count-steps.reduce((a,b)=>a+b,0);
    while(remaining<0){const i=steps.indexOf(Math.max(...steps));steps[i]--;remaining++;}
    for(let k=0;remaining>0;k++,remaining--) steps[order[k%order.length].i]++;
    const scale=count/60*1.72, result=[];
    for(let i=0;i<v.length;i++) {
      const p=v[i],q=v[(i+1)%v.length];
      for(let j=0;j<steps[i];j++) {
        const x=(p[0]+(q[0]-p[0])*j/steps[i]-7.5)*scale;
        const z=(p[1]+(q[1]-p[1])*j/steps[i]-4.5)*scale;
        const y=0.82 + 1.15*Math.max(0, Math.min(1,(-z+2)/7));
        result.push({x,y,z});
      }
    }
    let gap=Infinity;
    for(let i=0;i<result.length;i++)for(let j=0;j<i;j++)gap=Math.min(gap,Math.max(Math.abs(result[i].x-result[j].x),Math.abs(result[i].z-result[j].z)));
    if(gap<1.72){const factor=1.72/gap;for(const p of result){p.x*=factor;p.z*=factor;}}
    return result;
  }
  function panOffset(dx,dy,height,zoom){const k=24/(height*zoom),yaw=Math.atan2(17,34),pitch=Math.atan2(36,Math.hypot(17,34));return{x:(-dx*Math.cos(yaw)-dy*Math.sin(yaw)/Math.sin(pitch))*k,z:(dx*Math.sin(yaw)-dy*Math.cos(yaw)/Math.sin(pitch))*k};}
  function reachable(board, position, called, vipRequired=false) {
    return Array.from({length:6},(_,i)=>({steps:i+1,index:(position+i+1)%board.length}))
      .filter(x => { const s=board[x.index]; return vipRequired ? s.kind==='chest' : s.kind==='chest'||!called.has(s.name); });
  }
  function completeStudent(name, called, waitingVip) {
    if(called.has(name))throw new Error('重复点名已阻止');
    const vip=waitingVip.has(name);called.add(name);waitingVip.delete(name);
    return {name,vip};
  }
  const api={names, randomInt, shuffle, buildBoard, routePositions, reachable, completeStudent,panOffset};
  root.PickerModel=api;
  if(typeof module!=='undefined') module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
