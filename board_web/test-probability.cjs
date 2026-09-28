const assert=require('node:assert/strict'),P=require('./probability.js');
assert.deepEqual(P.rebalance([30,20,50],0,40),[40,17.1,42.9]);
assert.deepEqual(P.rebalance([20,0,0],0,30),[30,35,35]);
assert.deepEqual(P.rebalance([20,40,40],0,100),[100,0,0]);
assert.deepEqual(P.rebalance([100],0,40),[100]);
let seed=1234567;const rng=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
for(let n=1;n<=30;n++)for(let k=0;k<40;k++){
 const random=P.randomize(n,rng),index=Math.floor(rng()*n),value=Math.round(rng()*1000)/10;
 for(const weights of [random,P.rebalance(random,index,value)]){
  assert.equal(weights.length,n);assert.ok(weights.every(w=>w>=0&&w<=100));assert.equal(weights.reduce((sum,w)=>sum+Math.round(w*10),0),1000);
 }
 if(n>1)assert.equal(P.rebalance(random,index,value)[index],value);
}
console.log('PASS: 1200 random distributions and proportional edits, total exactly 100%, zero and single-item boundaries');
