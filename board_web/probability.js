/* Integer tenths keep the displayed probabilities at exactly 100%. */
(function(root){
 'use strict';
 function allocate(weights, units=1000){
  if(!weights.length)return [];
  let safe=weights.map(w=>Number.isFinite(Number(w))?Math.max(0,Number(w)):0),sum=safe.reduce((a,b)=>a+b,0);
  if(!sum){safe=safe.map(()=>1);sum=safe.length;}
  const exact=safe.map(w=>w/sum*units),out=exact.map(Math.floor);
  const order=exact.map((x,i)=>({i,f:x-out[i]})).sort((a,b)=>b.f-a.f||a.i-b.i);
  for(let k=0,left=units-out.reduce((a,b)=>a+b,0);k<left;k++)out[order[k%order.length].i]++;
  return out.map(x=>x/10);
 }
 function rebalance(weights,index,value){
  if(weights.length===1)return [100];
  const fixed=Math.round(Math.min(100,Math.max(0,Number(value)||0))*10);
  const rest=allocate(weights.filter((_,i)=>i!==index),1000-fixed);let cursor=0;
  return weights.map((_,i)=>i===index?fixed/10:rest[cursor++]);
 }
 function randomize(count,rng=Math.random){return allocate(Array.from({length:count},()=>-Math.log(Math.max(Number.EPSILON,1-rng()))));}
 const api={allocate,rebalance,randomize};root.PickerProbability=api;
 if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
