(function(root){
 'use strict';
 function createBoardWorld(T, entries){
  const scene=new T.Scene(); scene.background=null;
  const board=new T.Group(), scenery=new T.Group(); scene.add(scenery,board);
  const material=(color,metalness=.25,roughness=.65)=>new T.MeshStandardMaterial({color,metalness,roughness});
  const m={gold:material('#ba8b45',.65,.35),dark:material('#26222a'),red:material('#652039',.2,.65),stone:material('#4b3b41'),trim:material('#785633'),black:material('#211e26'),cream:material('#e9c691'),purple:material('#6537a0',.45,.36)};
  const glow=new T.MeshBasicMaterial({color:'#ffe4a0'});
  const geoBox=new T.BoxGeometry(1,1,1);
  function mesh(geometry,mat,parent,x=0,y=0,z=0){ const o=new T.Mesh(geometry,mat);o.position.set(x,y,z);o.castShadow=true;o.receiveShadow=true;parent.add(o);return o; }
  function box(parent,x,y,z,w,h,d,mat){const o=mesh(geoBox,mat,parent,x,y,z);o.scale.set(w,h,d);return o;}
  function cylinder(parent,x,y,z,r,h,mat,sides=16){return mesh(new T.CylinderGeometry(r,r,h,sides),mat,parent,x,y,z);}
  function rod(parent,a,b,r,mat){const start=new T.Vector3(...a),end=new T.Vector3(...b),o=mesh(new T.CylinderGeometry(r,r,start.distanceTo(end),10),mat,parent);o.position.copy(start.add(end).multiplyScalar(.5));o.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),new T.Vector3(...b).sub(new T.Vector3(...a)).normalize());return o;}
  const positions=PickerModel.routePositions(entries.length), scale=entries.length/60,compact=entries.length<60;
  const ext={minX:Math.min(...positions.map(p=>p.x)),maxX:Math.max(...positions.map(p=>p.x)),minZ:Math.min(...positions.map(p=>p.z)),maxZ:Math.max(...positions.map(p=>p.z))};
  const floorW=compact?Math.max(14,ext.maxX-ext.minX+9):29*scale,floorD=compact?Math.max(12,ext.maxZ-ext.minZ+11):18.5*scale;
  box(scenery,0,-.15,0,floorW,.5,floorD,m.black);
  box(scenery,0,-.4,0,floorW+.2,.14,floorD+.2,m.gold);
  box(scenery,0,-.72,0,floorW-.5,.5,floorD-.2,m.red);
  for(let x=-floorW/2+.5;x<floorW/2;x+=1.1)box(scenery,x,.112,0,.025,.018,floorD-.8,m.stone);
  const tiles=[], chests=[];
  function chest(parent,index,color){
    const g=new T.Group();parent.add(g);g.position.y=.24;
    const mat=color==='purple'?m.purple:material('#ce8d2a',.6,.42);
    box(g,0,.17,0,.76,.36,.53,mat);box(g,0,.015,0,.81,.07,.59,m.gold);
    const lid=new T.Group();lid.position.set(0,.34,-.27);g.add(lid);
    box(lid,0,.05,.27,.79,.17,.57,mat);
    box(lid,-.29,.15,.27,.065,.035,.59,m.gold);box(lid,.29,.15,.27,.065,.035,.59,m.gold);
    box(g,-.29,.19,.274,.065,.35,.04,m.gold);box(g,.29,.19,.274,.065,.35,.04,m.gold);
    box(g,0,.31,.29,.14,.2,.07,m.gold);
    const stone=mesh(new T.OctahedronGeometry(.075),color==='purple'?glow:m.cream,g,0,.32,.35);
    if(color==='purple')stone.material=new T.MeshBasicMaterial({color:'#be8df1'});
    g.rotation.y=.12;chests.push({index,group:g,lid});return g;
  }
  positions.forEach((p,i)=>{
    const s=entries[i],g=new T.Group();g.position.set(p.x,p.y,p.z);board.add(g);
    box(g,0,-p.y/2,0,1.58,p.y,1.58,m.red);
    box(g,0,-p.y+.15,0,1.65,.15,1.65,m.trim);
    box(g,0,.04,0,1.62,.12,1.62,m.gold);
    const top=box(g,0,.13,0,1.48,.10,1.48,s.kind==='chest'?material(s.color==='purple'?'#392544':'#60422a'):m.red.clone());
    const border=box(g,0,.19,0,1.35,.016,1.35,m.trim);
    box(g,0,.20,0,1.28,.018,1.28,s.kind==='chest'?m.dark:m.red);
    for(const corner of [-1,1])box(g,corner*.57,.232,.57,.035,.015,.08,m.gold);
    if(s.kind==='chest')chest(g,i,s.color);
    else{const emblem=mesh(new T.CylinderGeometry(.18,.18,.022,5),m.gold,g,0,-.37,.808);emblem.rotation.x=Math.PI/2;}
    const arrow=new T.Shape();arrow.moveTo(-.075,-.08);arrow.lineTo(.075,0);arrow.lineTo(-.075,.08);arrow.lineTo(-.035,0);arrow.closePath();
    const next=positions[(i+1)%positions.length],a=mesh(new T.ShapeGeometry(arrow),m.cream,g,.43,.232,-.43);a.rotation.x=-Math.PI/2;a.rotation.z=-Math.atan2(next.z-p.z,next.x-p.x);
    tiles.push({group:g,top,position:p});
  });
  function lamp(x,z,y=0){
    const g=new T.Group();scenery.add(g);g.position.set(x,y,z);
    cylinder(g,0,.1,0,.17,.2,m.gold);cylinder(g,0,.83,0,.046,1.5,m.gold);
    box(g,0,1.64,0,.22,.34,.22,m.black);box(g,0,1.65,.125,.14,.22,.03,glow);box(g,.125,1.65,0,.03,.22,.14,glow);
    mesh(new T.ConeGeometry(.22,.18,4),m.gold,g,0,1.9,0);return g;
  }
  let hub;const ornaments=[];
  if(!compact){
  for(const [x,z] of [[-13.8,-8.6],[13.8,-8.6],[-13.8,8.6],[13.8,8.6],[-4.7,-8.6],[5,-8.6]])lamp(x*scale,z*scale,1.4);
  function tower(x,z,w,d,h){
    const g=new T.Group();scenery.add(g);g.position.set(x,.15,z);
    box(g,0,h/2,0,w,h,d,m.stone);box(g,0,h+.1,0,w+.3,.25,d+.3,m.trim);box(g,0,h+.25,0,w+.4,.08,d+.4,m.gold);
    box(g,0,h+.34,0,w,.14,d,m.red);
    for(let k=0;k<3;k++){ const a=(k-1)*w*.25;box(g,a,h*.48,d/2+.02,.12,h*.75,.07,m.trim); }
    return g;
  }
  tower(-8*scale,-1*scale,4.2*scale,4.8*scale,1.4);
  const stage=tower(8.5*scale,-1.5*scale,3.8*scale,4.2*scale,1.05);
  for(const x of [-1.6,1.6]){box(stage,x,2,-1.8,.17,2.3,.17,m.gold);box(stage,x,2.2,-1.8,.46,1.8,.08,m.red);}
  box(stage,0,3.15,-1.8,3.8,.16,.22,m.gold);
  const awning=mesh(new T.ConeGeometry(2.3,1,4),m.red,stage,0,3.7,-.5);awning.rotation.y=Math.PI/4;awning.scale.z=.7;
  const wheel=new T.Group();scenery.add(wheel);wheel.position.set(-3*scale,4.3,-10.7*scale);
  hub=new T.Group();wheel.add(hub);
  for(const r of [2.5,2.85])mesh(new T.TorusGeometry(r,.07,8,64),m.gold,hub);
  mesh(new T.TorusGeometry(2.7,.12,8,64),m.red,hub);
  cylinder(hub,0,0,0,.45,.3,m.gold).rotation.x=Math.PI/2;
  for(let i=0;i<12;i++){
    const angle=i*Math.PI/6;rod(hub,[0,0,0],[2.6*Math.cos(angle),2.6*Math.sin(angle),0],.035,m.gold);
    mesh(new T.SphereGeometry(.065,8,6),glow,hub,2.7*Math.cos(angle),2.7*Math.sin(angle),.13);
    const spoke=box(hub,2.5*Math.cos(angle),2.5*Math.sin(angle),0,.35,.48,.32,m.red);spoke.rotation.z=angle;
  }
  rod(wheel,[-1.2,-4.1,.5],[0,0,.35],.14,m.gold);rod(wheel,[1.2,-4.1,.5],[0,0,.35],.14,m.gold);
  box(wheel,0,-4.05,.3,3.1,.35,1.6,m.red);
  // Perimeter scenery stays outside the playing route; no decorative text.
  const perimeter=Math.max(.7,scale);
  for(const side of [-1,1]){
    for(let i=0;i<13;i++){
      const x=(i-6)*2.12*perimeter,z=side*9.55*perimeter;
      cylinder(scenery,x,.52,z,.055,.85,m.gold,8);
      mesh(new T.SphereGeometry(.09,8,6),m.gold,scenery,x,.97,z);
      if(i<12){rod(scenery,[x,.73,z],[x+2.12*perimeter,.73,z],.026,m.gold);rod(scenery,[x,.35,z],[x+2.12*perimeter,.35,z],.022,m.trim);}
    }
    for(const x of [-15.4,15.4]){
      const tent=new T.Group();scenery.add(tent);tent.position.set(x*perimeter,.15,side*5.3*perimeter);
      cylinder(tent,0,.15,0,1.2,.3,m.gold,12);
      for(const a of [-1,1]){cylinder(tent,a*.77,1.1,0,.075,1.9,m.gold);box(tent,a*.77,1.24,0,.38,1.25,.11,m.red);}
      cylinder(tent,0,1.02,0,.88,.18,m.red,24);
      mesh(new T.ConeGeometry(1.42,.85,8),m.red,tent,0,2.27,0);
      mesh(new T.TorusGeometry(1.4,.055,8,40),m.gold,tent,0,1.85,0).rotation.x=Math.PI/2;
      mesh(new T.SphereGeometry(.13,12,8),m.gold,tent,0,2.75,0);
      for(let n=0;n<8;n++){const a=n*Math.PI/4;mesh(new T.SphereGeometry(.07,8,6),glow,tent,1.38*Math.cos(a),1.84,1.38*Math.sin(a));}
    }
  }
  for(const x of [-12,10]){
    const gate=new T.Group();scenery.add(gate);gate.position.set(x*perimeter,.2,-11.3*perimeter);
    for(const a of [-1,1]){cylinder(gate,a*1.15,1.5,0,.12,3,m.gold);box(gate,a*1.15,1.85,.06,.5,1.25,.09,m.red);}
    const arch=mesh(new T.TorusGeometry(1.15,.12,10,36,Math.PI),m.gold,gate,0,2.9,0);
    for(let i=0;i<9;i++){const a=i*Math.PI/8;mesh(new T.SphereGeometry(.07,8,6),glow,gate,Math.cos(a)*1.15,2.9+Math.sin(a)*1.15,.13);}
    for(let i=0;i<3;i++)box(gate,0,.07+i*.08,.75-i*.18,2.6-i*.2,.1,.9,m.trim);
  }
  for(let i=0;i<25;i++){
    const x=(-13+i*1.08)*perimeter,z=-12.7*perimeter,y=3.5-.55*Math.sin(i/24*Math.PI);
    if(i<24)rod(scenery,[x,y,z],[x+1.08*perimeter,3.5-.55*Math.sin((i+1)/24*Math.PI),z],.018,m.black);
    mesh(new T.SphereGeometry(.065,8,6),glow,scenery,x,y-.08,z);
    if(i%3===0){const flag=new T.Shape();flag.moveTo(-.23,0);flag.lineTo(.23,0);flag.lineTo(0,-.46);flag.closePath();mesh(new T.ShapeGeometry(flag),new T.MeshStandardMaterial({color:i%2?'#b89045':'#712740',side:T.DoubleSide}),scenery,x,y-.12,z);}
  }
  }else{
    for(const x of [ext.minX-2.4,ext.maxX+2.4])for(const z of [ext.minZ-2,ext.maxZ+2])ornaments.push(lamp(x,z,.2));
    const wheel=new T.Group();wheel.position.set(0,2.65,ext.minZ-4);scenery.add(wheel);ornaments.push(wheel);
    hub=new T.Group();wheel.add(hub);
    mesh(new T.TorusGeometry(1.55,.09,8,40),m.gold,hub);
    mesh(new T.TorusGeometry(1.4,.1,8,40),m.red,hub);
    for(let i=0;i<8;i++){const a=i*Math.PI/4;rod(hub,[0,0,0],[1.5*Math.cos(a),1.5*Math.sin(a),0],.035,m.gold);mesh(new T.SphereGeometry(.065,8,6),glow,hub,1.5*Math.cos(a),1.5*Math.sin(a),.12);}
    rod(wheel,[-.8,-2.5,.2],[0,0,0],.1,m.gold);rod(wheel,[.8,-2.5,.2],[0,0,0],.1,m.gold);
    for(const side of [-1,1]){
      const pavilion=new T.Group();pavilion.position.set(side<0?ext.minX-3.4:ext.maxX+3.4,.15,0);scenery.add(pavilion);ornaments.push(pavilion);
      box(pavilion,0,.2,0,1.6,.4,1.6,m.red);
      for(const x of [-.6,.6])cylinder(pavilion,x,.95,0,.055,1.6,m.gold);
      mesh(new T.ConeGeometry(1.1,.65,4),m.red,pavilion,0,1.95,0).rotation.y=Math.PI/4;
      cylinder(pavilion,0,.42,0,.72,.08,m.gold);
    }
    for(let i=0;i<positions.length;i++){
      const a=positions[i],b=positions[(i+1)%positions.length];
      if(Math.hypot(a.x-b.x,a.z-b.z)>2)rod(board,[a.x,a.y-.04,a.z],[b.x,b.y-.04,b.z],.22,m.trim);
    }
  }
  // A recognisable chess king: turned body, circular plinth and cross finial.
  const pawn=new T.Group();pawn.name='chess-king';pawn.userData.pieceType='king';board.add(pawn);
  const ivory=material('#eee0c1',.22,.3);
  const profile=[[0,0],[.27,0],[.32,.045],[.32,.09],[.29,.13],[.285,.18],[.24,.23],[.205,.30],[.16,.43],[.135,.59],[.13,.72],[.17,.78],[.22,.81],[.22,.86],[.17,.90],[.16,.98],[.10,1.04],[0,1.04]].map(([r,y])=>new T.Vector2(r,y));
  mesh(new T.LatheGeometry(profile,40),ivory,pawn).name='king-turned-body';
  cylinder(pawn,0,.02,0,.30,.035,m.black,32);
  cylinder(pawn,0,.155,0,.293,.035,m.gold,32);
  cylinder(pawn,0,.835,0,.224,.025,m.gold,32);
  const crown=mesh(new T.SphereGeometry(.105,24,16),ivory,pawn,0,1.015,0);crown.scale.y=.65;
  box(pawn,0,1.175,0,.075,.30,.085,m.gold).name='king-cross-vertical';
  box(pawn,0,1.205,0,.255,.075,.085,m.gold).name='king-cross-horizontal';
  pawn.rotation.y=.46;
  const ring=mesh(new T.TorusGeometry(.57,.035,8,48),glow,board);ring.rotation.x=-Math.PI/2;
  scene.add(new T.HemisphereLight('#e6e1e4','#35242e',2));
  const sun=new T.DirectionalLight('#ffe7c1',3.3);sun.position.set(-10,24,17);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);sun.shadow.camera.left=-25;sun.shadow.camera.right=25;sun.shadow.camera.top=25;sun.shadow.camera.bottom=-25;sun.shadow.normalBias=.08;scene.add(sun);
  const fill=new T.DirectionalLight('#9cabc7',1.1);fill.position.set(10,10,-10);scene.add(fill);
  const bounds=new T.Box3().setFromObject(board);
  return {scene,board,scenery,tiles,chests,pawn,ring,positions,hub,bounds,compact,ornaments};
 }
 root.createBoardWorld=createBoardWorld;
 if(typeof module!=='undefined')module.exports=createBoardWorld;
})(typeof window!=='undefined'?window:globalThis);
