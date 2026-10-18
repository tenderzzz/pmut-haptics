/* Durable local records. Backup files remain the portable source of truth. */
function createPmutLibrary(K,T){
  "use strict";
  const plain=v=>JSON.parse(JSON.stringify(v,(_k,x)=>ArrayBuffer.isView(x)?Array.from(x):x));
  function record(result,name,notes,quality=null){
    const snapshot=plain(result);
    delete snapshot.wave;
    snapshot.trajectory={times:snapshot.trajectory.times,points:snapshot.trajectory.points};
    snapshot.archived=true;
    return {schema_version:1,id:typeof crypto!=="undefined"&&crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random().toString(36).slice(2),
      model_version:T.version,created_at:new Date().toISOString(),name:name.trim()||result.config.title,
      notes:notes||"",snapshot,quality};
  }
  function validate(r){
    if(!r||r.schema_version!==1||typeof r.id!=="string"||!r.id||typeof r.name!=="string"||
       typeof r.notes!=="string"||typeof r.created_at!=="string"||typeof r.model_version!=="string")
      throw Error("实验记录格式不完整。");
    const s=r.snapshot,c=K.validate(s.config),g=c.grid;
    if(!s.metrics||!s.field||!s.axes||!s.trajectory)throw Error("实验快照不完整。");
    const finite=(v,n)=>Array.isArray(v)&&v.length===n&&v.every(Number.isFinite);
    for(const [key,n] of [["x",g.nx],["y",g.ny],["z",g.nz]])if(!finite(s.axes[key],n))throw Error("实验坐标尺寸错误。");
    for(const [key,n] of [["re",g.nx*g.ny],["im",g.nx*g.ny],["rms",g.nx*g.ny],["radiation",g.nx*g.ny],["xzRms",g.nx*g.nz],["profileX",g.nx],["profileY",g.ny]])
      if(!finite(s.field[key],n))throw Error("实验场图尺寸错误。");
    K.actualPositions(K.positions(c),s.sample,c);
    if(r.quality&&(r.quality.model_version!==r.model_version||T.configKey(r.quality.config)!==T.configKey(c)))throw Error("质量报告与实验不匹配。");
    return plain(r);
  }
  function backup(records){return {format:"pmut-experiment-library",schema_version:1,created_at:new Date().toISOString(),records:records.map(validate)};}
  function restore(data,existing){
    if(data?.format!=="pmut-experiment-library"||data.schema_version!==1||!Array.isArray(data.records)||data.records.length>1000)throw Error("请选择实验库备份 JSON（最多 1000 条）。");
    const checked=data.records.map(validate),known=new Set(existing.map(r=>r.id)),added=[];
    for(const r of checked)if(!known.has(r.id)){known.add(r.id);added.push(r);}
    return added;
  }
  function open(){
    return new Promise((resolve,reject)=>{
      if(typeof indexedDB==="undefined"){reject(Error("此浏览器不支持实验本地存储"));return;}
      let request;
      try{request=indexedDB.open("pmut-experiments",1);}catch(e){reject(e);return;}
      request.onupgradeneeded=()=>request.result.createObjectStore("experiments",{keyPath:"id"});
      request.onerror=()=>reject(request.error);
      request.onblocked=()=>reject(Error("实验库正被另一页面占用，请关闭旧页面后重试"));
      request.onsuccess=()=>{
        const db=request.result;
        db.onversionchange=()=>db.close();
        function transact(mode,action){
          return new Promise((yes,no)=>{
            const tx=db.transaction("experiments",mode);let value;
            const req=action(tx.objectStore("experiments"));
            if(req)req.onsuccess=()=>{value=req.result;};
            tx.oncomplete=()=>yes(value);tx.onerror=()=>no(tx.error);tx.onabort=()=>no(tx.error||Error("存储事务中断"));
          });
        }
        resolve({all:()=>transact("readonly",s=>s.getAll()),put:r=>transact("readwrite",s=>s.put(validate(r))),
          remove:id=>transact("readwrite",s=>s.delete(id)),
          addMany:rs=>transact("readwrite",s=>{for(const r of rs)s.add(validate(r));})});
      };
    });
  }
  return {plain,record,validate,backup,restore,open};
}
if(typeof module!=="undefined"&&module.exports)module.exports={createPmutLibrary};
