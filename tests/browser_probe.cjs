const fs = require("node:fs");
const {createPmutKernel} = require("../web/core.js");
const K=createPmutKernel(), request=JSON.parse(fs.readFileSync(0,"utf8"));
(async()=>{
  let response;
  if(request.operation==="simulate") response=await K.simulate(request.config);
  else if(request.operation==="jinc") response=request.points.map(K.jinc);
  else if(request.operation==="parse") response=K.parseToml(request.text);
  else if(request.operation==="validate") {
    response=request.cases.map(c=>{try {K.validate(c);return null;}catch(e){return e.message;}});
  } else throw Error("Unknown probe");
  process.stdout.write(JSON.stringify(response,(_key,v)=>ArrayBuffer.isView(v)?Array.from(v):v));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
