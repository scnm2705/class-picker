(function(root){
 'use strict';
 const normals={1:[0,1,0],6:[0,-1,0],2:[0,0,1],5:[0,0,-1],3:[1,0,0],4:[-1,0,0]};
 function pose(T,value){return new T.Quaternion().setFromUnitVectors(new T.Vector3(...normals[value]),new T.Vector3(0,1,0));}
 function roundedGeometry(T){
  const g=new T.BoxGeometry(1,1,1,12,12,12),p=g.attributes.position,n=g.attributes.normal,r=.105,inner=.5-r;
  const v=new T.Vector3(),c=new T.Vector3();
  for(let i=0;i<p.count;i++){
   v.fromBufferAttribute(p,i);c.copy(v).clampScalar(-inner,inner);v.sub(c).normalize();
   n.setXYZ(i,v.x,v.y,v.z);c.addScaledVector(v,r);p.setXYZ(i,c.x,c.y,c.z);
  }
  g.computeBoundingSphere();return g;
 }
 function createSolidDie(T){
  const group=new T.Group();
  const body=new T.Mesh(roundedGeometry(T),new T.MeshStandardMaterial({color:'#fff3e6',roughness:.24,metalness:.12}));
  body.name='closed-rounded-body';group.add(body);
  const red=new T.MeshStandardMaterial({color:'#b90828',roughness:.24,metalness:.2});
  const white=new T.MeshStandardMaterial({color:'#fff9eb',roughness:.3});
  const shape=new T.Shape(),s=.39,r=.075;
  shape.moveTo(-s+r,-s);shape.lineTo(s-r,-s);shape.quadraticCurveTo(s,-s,s,-s+r);shape.lineTo(s,s-r);shape.quadraticCurveTo(s,s,s-r,s);shape.lineTo(-s+r,s);shape.quadraticCurveTo(-s,s,-s,s-r);shape.lineTo(-s,-s+r);shape.quadraticCurveTo(-s,-s,-s+r,-s);
  const patch=new T.ShapeGeometry(shape,10),pipGeo=new T.CircleGeometry(.06,32);
  const dots={1:[[0,0]],2:[[-1,1],[1,-1]],3:[[-1,1],[0,0],[1,-1]],4:[[-1,1],[1,1],[-1,-1],[1,-1]],5:[[-1,1],[1,1],[0,0],[-1,-1],[1,-1]],6:[[-1,1],[1,1],[-1,0],[1,0],[-1,-1],[1,-1]]};
  for(let value=1;value<=6;value++){
   const face=new T.Group();face.name='face-'+value;
   const normal=new T.Vector3(...normals[value]);face.position.copy(normal).multiplyScalar(.5005);
   face.quaternion.setFromUnitVectors(new T.Vector3(0,0,1),normal);
   face.add(new T.Mesh(patch,red));
   for(const [x,y]of dots[value]){const pip=new T.Mesh(pipGeo,white);pip.position.set(x*.215,y*.215,.001);face.add(pip);}
   group.add(face);
  }
  return group;
 }
 class DiceView{
  constructor(T,host){
   this.T=T;this.renderer=new T.WebGLRenderer({alpha:true,antialias:true});
   this.renderer.setPixelRatio(Math.min(root.devicePixelRatio||1,2));this.renderer.setSize(260,260);
   this.renderer.outputColorSpace=T.SRGBColorSpace;host.replaceChildren(this.renderer.domElement);
   this.scene=new T.Scene();this.die=createSolidDie(T);this.scene.add(this.die);
   this.scene.add(new T.HemisphereLight('#ffffff','#b8543a',2.7));
   const light=new T.DirectionalLight('#fff4de',3.2);light.position.set(-3,7,5);this.scene.add(light);
   this.camera=new T.PerspectiveCamera(27,1,.1,30);this.camera.position.set(1.25,3.36,1.78);this.camera.lookAt(0,0,0);
   this.setRoll(1,1);
  }
  setRoll(value,progress){
   const T=this.T,rest=pose(T,value),a=(1-progress)**3;
   const spin=new T.Quaternion().setFromEuler(new T.Euler(a*Math.PI*6,0,a*Math.PI*8));
   this.die.quaternion.copy(spin).multiply(rest);this.renderer.render(this.scene,this.camera);
  }
 }
 root.DiceView=DiceView;root.SolidDie={createSolidDie,roundedGeometry,pose,normals};
 if(typeof module!=='undefined')module.exports=root.SolidDie;
})(typeof window!=='undefined'?window:globalThis);
