/* Shared browser batch/diagnostic workflows. No DOM, storage or network access. */
function createPmutTasks(K){
  "use strict";
  const version="2.0", keys=["target_pressure_rms_pa","pressure_rms_max_pa","target_lateral_error_m","pressure_x_minus6db_m","sidelobe_x_db","force_over_displayed_plane_n"];
  const summary=m=>Object.fromEntries(keys.map(k=>[k,k==="pressure_x_minus6db_m"?m.pressure_x_minus6db.width_m:m[k]??null]));
  const stable=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==="object"&&!Array.isArray(x)&&!ArrayBuffer.isView(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):ArrayBuffer.isView(x)?Array.from(x):x);
  const configKey=c=>stable(K.validate(c));
  function staticConfig(input){
    const c=K.validate(input);
    if(c.trajectory.kind!=="static")throw Error("请先勾选创建静态副本；原实验保持不变。");
    return c;
  }
  function values(t){
    if(!["carrier_hz","focus.z_m","array.side","array.pitch_m","array.pitch_wavelengths","element.velocity_peak_m_s"].includes(t.parameter))throw Error("不支持的扫描参数。");
    let v=t.values;
    if(v===undefined){
      if(!Number.isInteger(t.count)||t.count<2||t.count>50||!Number.isFinite(t.start)||!Number.isFinite(t.stop))throw Error("等间距扫描需 2–50 点和有限的起止值。");
      v=Array.from({length:t.count},(_,i)=>t.start+(t.stop-t.start)*i/(t.count-1));
    }
    if(!Array.isArray(v)||v.length<1||v.length>50||v.some(x=>!Number.isFinite(x)))throw Error("网页扫描需要 1–50 个有限数值。");
    return v;
  }
  function sweepConfig(base,t,value){
    const c=K.clone(base),p=t.parameter;
    if(p==="carrier_hz"){
      if(!["physical","wavelength"].includes(t.frequency_pitch||"physical"))throw Error("未知的扫频间距模式。");
      if((t.frequency_pitch||"physical")==="physical"){c.array.pitch_mode="physical";c.array.pitch_m=K.pitch(base);}
      else{c.array.pitch_mode="wavelength";c.array.pitch_wavelengths=K.pitch(base)*base.carrier_hz/base.medium.sound_speed_m_s;}
      c.carrier_hz=value;
    }else if(p==="array.side"){
      if(!Number.isInteger(value)||value<1)throw Error("阵列边长须为正整数。");
      c.array.nx=value;c.array.ny=value;
    }else{
      const [section,key]=p.split(".");c[section][key]=value;
      if(p.startsWith("array.pitch"))c.array.pitch_mode=key==="pitch_m"?"physical":"wavelength";
    }
    const norm=t.normalization||"fixed_sum_squared_velocity";
    if(!["fixed_sum_squared_velocity","per_element"].includes(norm))throw Error("未知的归一化方式。");
    if(norm==="fixed_sum_squared_velocity"&&p==="array.side")c.element.velocity_peak_m_s*=Math.sqrt(base.array.nx*base.array.ny/(value*value));
    return K.validate(c);
  }
  function quantile(v,p){
    const a=v.slice().sort((x,y)=>x-y),at=(a.length-1)*p,lo=Math.floor(at);
    return a.length?a[lo]+(a[Math.min(lo+1,a.length-1)]-a[lo])*(at-lo):null;
  }
  function aggregate(rows){
    return Object.fromEntries(keys.map(k=>{
      const v=rows.filter(r=>r.status==="ok"&&Number.isFinite(r.metrics[k])).map(r=>r.metrics[k]);
      return [k,{valid:v.length,missing:rows.length-v.length,median:quantile(v,.5),p5:quantile(v,.05),p95:quantile(v,.95)}];
    }));
  }
  async function batch(t,compute,onRow=()=>{},stop=()=>false){
    if(t.schema_version!==1||!["sweep","robustness"].includes(t.kind))throw Error("任务版本或类型不受支持。");
    const base=staticConfig(t.config),out={schema_version:1,model_version:version,task:K.clone(t),rows:[],status:"running",distribution_note:"sample quantiles, not confidence intervals"};
    let jobs=[],variants=[];
    if(t.kind==="sweep")jobs=values(t).map((value,index)=>({index,value,phase_bits:null}));
    else{
      if(!Number.isInteger(t.count)||t.count<1||t.count>100)throw Error("网页鲁棒性试验需要 1–100 次。");
      variants=t.quantization_comparison?[0,3,4,6,8]:[base.imperfections.phase_bits];
      for(let i=0;i<t.count;i++)for(const b of variants)jobs.push({index:i,value:null,phase_bits:b});
      const ideal=K.clone(base);ideal.array.phase_error_std_deg=0;ideal.imperfections=K.clone(K.defaults.imperfections);
      try{out.ideal=summary((await compute(ideal)).metrics);}catch(e){if(!stop())throw e;out.status="cancelled";return out;}
    }
    for(const job of jobs){
      if(stop()){out.status="cancelled";break;}
      const row={...job};
      try{
        let c;
        if(t.kind==="sweep")c=sweepConfig(base,t,job.value);
        else{c=K.clone(base);c.seed=(base.seed+job.index)%4294967296;c.imperfections.rng="portable-v1";c.imperfections.phase_bits=job.phase_bits;}
        const sample=K.sample(c);row.config=c;row.sample=sample;
        const r=await compute(c,sample);
        row.status="ok";row.metrics=summary(r.metrics);row.pitch_m=K.pitch(c);row.sum_squared_velocity_m2_s2=r.metrics.sum_squared_velocity_m2_s2;
      }catch(e){
        if(stop()){out.status="cancelled";break;}
        row.status="invalid";row.reason=e.message;
      }
      out.rows.push(row);onRow(row,out,jobs.length);
    }
    if(out.status==="running")out.status="complete";
    if(t.kind==="robustness")out.statistics=Object.fromEntries(variants.map(b=>[String(b),aggregate(out.rows.filter(r=>r.phase_bits===b))]));
    return out;
  }
  function change(before,after,threshold){
    if(before===null||after===null||before===0)return {status:"unevaluable",reason:"zero baseline or missing/clipped metric",before,after};
    const value=Math.abs(after-before)/Math.abs(before);
    return {status:value<=threshold?"pass":"sensitive",relative_change:value,threshold,before,after};
  }
  async function quality(input,compute,options={}){
    const c=staticConfig(input),sample=K.sample(c),gt=options.grid_tolerance??.02,rt=options.region_tolerance??.05;
    if(!(gt>0&&gt<=1&&rt>0&&rt<=1))throw Error("检查阈值须大于 0 且不超过 100%。");
    const base=await compute(c,sample),g=c.grid;
    const report={schema_version:1,model_version:version,config:c,sample,checks:{},model_note:"uniform piston, element far-field; normal-incidence force approximation",input_note:"assumed velocity; not voltage calibrated; no perception validation"};
    for(const name of ["grid","region"]){
      const q=K.clone(c),h=q.grid;h.nx=2*g.nx-1;h.ny=2*g.ny-1;
      if(name==="grid")h.nz=2*g.nz-1;
      else{h.x_min_m=(3*g.x_min_m-g.x_max_m)/2;h.x_max_m=(3*g.x_max_m-g.x_min_m)/2;h.y_min_m=(3*g.y_min_m-g.y_max_m)/2;h.y_max_m=(3*g.y_max_m-g.y_min_m)/2;}
      if(Math.max(h.nx*h.ny,h.nx*h.nz)>100000||h.nx*(h.ny+h.nz)*c.array.nx*c.array.ny>35000000||Math.max(h.nx,h.ny,h.nz)>601){
        report.checks[name]={status:"unchecked",reason:"diagnostic budget exceeded"};continue;
      }
      const r=await compute(q,sample,true),m=summary(r.metrics),b=summary(base.metrics);
      const ks=name==="region"?["force_over_displayed_plane_n"]:["pressure_rms_max_pa","pressure_x_minus6db_m","force_over_displayed_plane_n"];
      report.checks[name]=Object.fromEntries(ks.map(k=>[k,change(b[k],m[k],name==="region"?rt:gt)]));
    }
    for(const k of ["pressure_x_minus6db","pressure_y_minus6db"])report.checks[k]=base.metrics[k];
    report.checks.focus={lateral_error_m:base.metrics.target_lateral_error_m,scope:"sampled target plane only"};
    report.checks.reference={status:"unchecked",reason:"Python quality --reference; import matching report here"};
    return report;
  }
  return {version,keys,summary,stable,configKey,staticConfig,values,sweepConfig,aggregate,batch,change,quality};
}
if(typeof module!=="undefined"&&module.exports)module.exports={createPmutTasks};
