const assert=require('node:assert/strict'),M=require('./board-model.js'),T=require('./vendor/three.min.js');
global.PickerModel=M;const create=require('./scene.js');
// Test the visible direction in projection, rather than repeating the pan formula.
for(const [dx,dy]of [[0,-80],[0,80],[-90,0],[90,0],[30,40]]){
 const camera=new T.OrthographicCamera(-16,16,12,-12,.1,150),offset=new T.Vector3(17,36,34);
 camera.position.copy(offset);camera.lookAt(0,0,0);camera.updateMatrixWorld();
 const before=new T.Vector3(1,1,1).project(camera),d=M.panOffset(dx,dy,900,1);
 camera.position.add(new T.Vector3(d.x,0,d.z));camera.lookAt(d.x,0,d.z);camera.updateMatrixWorld();
 const after=new T.Vector3(1,1,1).project(camera);
 assert.ok(Math.abs((after.x-before.x)*1200/2-dx)<1e-6);
 assert.ok(Math.abs(-(after.y-before.y)*900/2-dy)<1e-6);
}
let boards=0,clearances=0;
for(let students=1;students<=90;students++){
 const entries=[];for(let i=0;i<students;i++){entries.push({kind:'student',name:'学生'+i});if(i%5===4||i===students-1)entries.push({kind:'chest',color:'purple'});}
 const pts=M.routePositions(entries.length);assert.equal(pts.length,entries.length);
 for(let i=0;i<pts.length;i++)for(let j=0;j<i;j++)assert.ok(Math.max(Math.abs(pts[i].x-pts[j].x),Math.abs(pts[i].z-pts[j].z))>=1.67,'tiles overlap for '+students);
 if([1,2,3,5,8,10,15,25,35,49,50].includes(students)){
  const world=create(T,entries);world.scene.updateMatrixWorld(true);
  for(const object of world.ornaments){
   const b=new T.Box3().setFromObject(object);
   for(const p of pts){assert.ok(b.max.x<p.x-1||b.min.x>p.x+1||b.max.z<p.z-1||b.min.z>p.z+1,'decoration enters tile clearance for '+students);clearances++;}
  }
  const geometries=new Set(),materials=new Set();world.scene.traverse(o=>{if(o.geometry)geometries.add(o.geometry);if(o.material)materials.add(o.material)});geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());
 }
 boards++;
}
console.log(JSON.stringify({result:'PASS',projectedDragDirections:5,classSizes:boards,decorationClearances:clearances}));
