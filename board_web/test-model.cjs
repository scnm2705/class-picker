const assert=require('node:assert/strict');
const M=require('./board-model.js');
const T=require('./vendor/three.min.js');
const create=require('./scene.js');
let seed=27;const rng=max=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%max;};
let checked=0;
for(let n=12;n<=90;n++)for(let round=0;round<12;round++){
 const roster=Array.from({length:n},(_,i)=>'学生'+(i+1)),board=M.buildBoard(roster,rng);
 assert.equal(board.length,n+Math.ceil(n/5));
 assert.equal(new Set(board.filter(s=>s.kind==='student').map(s=>s.name)).size,n);
 const frozen=JSON.stringify(board),called=new Set(roster.filter((_,i)=>i%3===0));
 for(let pos=0;pos<board.length;pos++){
  const vips=M.reachable(board,pos,called,true);assert.ok(vips.length>=1,'must reach a chest in 1–6 steps');
  for(const move of vips){assert.ok(move.steps>=1&&move.steps<=6);assert.equal((pos+move.steps)%board.length,move.index);assert.equal(board[move.index].kind,'chest');}
  for(const move of M.reachable(board,pos,called)){assert.ok(board[move.index].kind==='chest'||!called.has(board[move.index].name));}
 }
 assert.equal(JSON.stringify(board),frozen,'dice planning must not reshuffle board');
 const path=M.routePositions(board.length);assert.equal(path.length,board.length);assert.equal(new Set(path.map(p=>[p.x,p.z].join(','))).size,board.length);
 checked++;
}
assert.throws(()=>M.buildBoard(Array(50).fill('同名')),/重复/);
const called=new Set(),waiting=new Set(['张三','李四']);
assert.deepEqual(M.completeStudent('张三',called,waiting),{name:'张三',vip:true});
assert.ok(!waiting.has('张三'));assert.ok(called.has('张三'));
assert.throws(()=>M.completeStudent('张三',called,waiting),/重复/);
assert.deepEqual(M.completeStudent('王五',called,waiting),{name:'王五',vip:false});
const board=M.buildBoard(M.names,rng),world=create(T,board);
assert.equal(world.tiles.length,60);assert.equal(world.chests.length,10);
assert.equal(world.pawn.userData.pieceType,'king');
assert.ok(world.pawn.getObjectByName('king-turned-body'));
assert.ok(world.pawn.getObjectByName('king-cross-vertical'));
assert.ok(world.pawn.getObjectByName('king-cross-horizontal'));
assert.ok(new Set(world.positions.map(p=>p.y)).size>3);
for(let i=0;i<world.positions.length;i++){
 const a=world.positions[i],b=world.positions[(i+1)%world.positions.length];assert.ok(Math.abs(Math.hypot(a.x-b.x,a.z-b.z)-1.72)<1e-8,'continuous route, including loop seam');
}
let meshes=0;world.scene.traverse(o=>{if(o.isMesh){meshes++;assert.ok(o.position.toArray().every(Number.isFinite));}});
console.log(JSON.stringify({result:'PASS',variableBoards:checked,students:50,chests:10,slots:60,sceneMeshes:meshes,verified:['unique names','stable per-round layout','1–6-step endpoints','reachable VIP chest from every tile','no duplicate completion','direct name landing completes VIP','continuous closed 3D route']},null,2));
