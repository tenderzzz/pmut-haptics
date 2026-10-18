const fs = require("node:fs");
const {createPmutKernel} = require("../web/core.js");
const {createPmutTasks}=require("../web/tasks.js");
const {createPmutLibrary}=require("../web/library.js");
const K=createPmutKernel(), request=JSON.parse(fs.readFileSync(0,"utf8"));
(async()=>{
  let response;
  if(request.operation==="simulate") response=await K.simulate(request.config,()=>{},()=>false,request.sample||null);
  else if(request.operation==="sample")response=K.sample(K.validate(request.config));
  else if(request.operation==="random"){const r=K.random(request.seed);response=Array.from({length:8},()=>r.uniform());}
  else if(request.operation==="batch")response=await createPmutTasks(K).batch(request.task,(c,s,d)=>K.simulate(c,()=>{},()=>false,s,d));
  else if(request.operation==="quality")response=await createPmutTasks(K).quality(request.config,(c,s,d)=>K.simulate(c,()=>{},()=>false,s,d),request.options);
  else if(request.operation==="library"){
    const T=createPmutTasks(K),L=createPmutLibrary(K,T),result=await K.simulate(request.config);
    const record=L.record(result,"test","note"),backup=L.backup([record]),restored=L.restore(backup,[]);
    response={record,restored:restored.length,duplicates:L.restore(backup,restored).length};
  }
  else if(request.operation==="jinc") response=request.points.map(K.jinc);
  else if(request.operation==="parse") response=K.parseToml(request.text);
  else if(request.operation==="validate") {
    response=request.cases.map(c=>{try {K.validate(c);return null;}catch(e){return e.message;}});
  } else throw Error("Unknown probe");
  process.stdout.write(JSON.stringify(response,(_key,v)=>ArrayBuffer.isView(v)?Array.from(v):v));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
