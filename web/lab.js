/* Laboratory UI: snapshots, local library, tasks and diagnostics. */
function mountPmutLab(api){
  "use strict";
  const {K,T,$}=api,L=createPmutLibrary(K,T);
  const labels={target_pressure_rms_pa:"目标点 RMS 声压 (Pa)",pressure_rms_max_pa:"平面最大 RMS 声压 (Pa)",target_lateral_error_m:"横向焦点偏差 (mm)",pressure_x_minus6db_m:"x 主瓣 −6 dB 宽度 (mm)",sidelobe_x_db:"x 旁瓣 (dB)",force_over_displayed_plane_n:"有限区域合力 (μN)"};
  const scale=k=>k.endsWith("_m")?1000:k.endsWith("_n")?1e6:1;
  const number=(v,k="")=>Number.isFinite(v)?Number((v*scale(k)).toPrecision(6)).toLocaleString("en-US",{maximumSignificantDigits:6}):"不可评价";
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  let records=[],db=null,selected=new Set(),qualityReport=null,lastSweep=null,lastRobust=null,editing=null;
  const say=(id,text,error=false)=>{const el=$(id);el.textContent=text;el.className="notice"+(error?" error":"");};
  const download=(name,v)=>api.download(name,api.serialize(v));
  function bind(id,fn){$(id).addEventListener("click",()=>Promise.resolve().then(fn).catch(e=>api.notice(e.message,"error")));}
  function table(target,headers,rows){
    const wrapper=typeof target==="string"?$(target):target;
    const t=document.createElement("table"),head=document.createElement("thead"),body=document.createElement("tbody"),tr=document.createElement("tr");
    for(const h of headers){const th=document.createElement("th");th.scope="col";th.textContent=h;tr.append(th);}head.append(tr);
    for(const row of rows){const tr=document.createElement("tr");for(const value of row){const td=document.createElement("td");td.textContent=String(value??"—");tr.append(td);}body.append(tr);}
    t.append(head,body);wrapper.replaceChildren(t);
  }
  function displayLibrary(){
    const body=$("library-rows");body.replaceChildren();
    for(const r of records){
      const tr=document.createElement("tr"),select=document.createElement("td"),name=document.createElement("td"),date=document.createElement("td"),actions=document.createElement("td");
      const input=document.createElement("input");input.type="checkbox";input.checked=selected.has(r.id);input.setAttribute("aria-label","比较 "+r.name);
      input.addEventListener("change",()=>{if(input.checked&&selected.size===4){input.checked=false;api.notice("最多选择四个实验。","error");return;}input.checked?selected.add(r.id):selected.delete(r.id);});
      select.append(input);name.textContent=r.name;const notes=document.createElement("small");notes.textContent=r.notes;name.append(notes);
      date.textContent=new Date(r.created_at).toLocaleString()+" / "+r.model_version;
      const rowActions=document.createElement("div");rowActions.className="lab-actions";
      const button=(label,fn)=>{const b=document.createElement("button");b.textContent=label;b.addEventListener("click",()=>Promise.resolve().then(fn).catch(e=>api.notice(e.message,"error")));rowActions.append(b);};
      button("打开",()=>{api.ensureIdle();api.openRecord(r.snapshot);qualityReport=r.quality||null;editing=null;$("experiment-name").value=r.name;$("experiment-notes").value=r.notes;renderQuality();api.notice("已打开保存的静态结果。重新运行可恢复轨迹和完整波形。");});
      button("复制参数",()=>{api.ensureIdle();api.fill(K.clone(r.snapshot.config));editing=null;$("experiment-name").value=r.name+" 副本";$("experiment-notes").value=r.notes;api.notice("已复制参数，点击运行仿真生成新结果。","stale");});
      button("编辑名称/备注",()=>{editing=r.id;$("experiment-name").value=r.name;$("experiment-notes").value=r.notes;$("library-save").textContent="保存名称和备注";$("experiment-name").focus();});
      button("删除",async()=>{if(db)await db.remove(r.id);records=records.filter(v=>v.id!==r.id);selected.delete(r.id);if(editing===r.id){editing=null;$("library-save").textContent="保存当前实验";}displayLibrary();$("library-comparison").replaceChildren();say("library-status","已删除这条本地实验记录；备份文件未改变。");});
      actions.append(rowActions);tr.append(select,name,date,actions);body.append(tr);
    }
    if(!records.length){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=4;td.textContent="还没有实验。运行仿真后，填写名称并保存。";tr.append(td);body.append(tr);}
  }
  const ready=L.open().then(async store=>{const saved=await store.all();records=saved.map(L.validate);db=store;say("library-status","本地实验库已就绪："+records.length+" 条记录。");}).catch(e=>{say("library-status","本地存储不可用："+e.message+"。仍可保存到本页并下载备份，关闭页面会丢失未备份记录。",true);}).finally(displayLibrary);
  async function persist(r){
    await ready;
    let durable=Boolean(db);
    if(db)try{await db.put(r);}catch(e){durable=false;say("library-status","保存到浏览器失败："+e.message+"。记录保留在本页，请立即备份。",true);}
    const at=records.findIndex(v=>v.id===r.id);if(at<0)records.unshift(r);else records[at]=r;
    if(durable)say("library-status","已保存到本地实验库。建议同时下载备份。");
    else say("library-status","记录仅保存在本页；请下载备份后再关闭页面。",true);
    displayLibrary();
  }
  bind("library-save",async()=>{
    if(editing){
      const old=records.find(r=>r.id===editing);if(!old)throw Error("待编辑记录不存在。");
      await persist({...old,name:$("experiment-name").value.trim()||old.name,notes:$("experiment-notes").value});
      editing=null;$("library-save").textContent="保存当前实验";return;
    }
    const r=api.getResult();if(!r)throw Error("先运行一次仿真。");
    const q=qualityReport&&T.configKey(qualityReport.config)===T.configKey(r.config)?qualityReport:null;
    await persist(L.record(r,$("experiment-name").value,$("experiment-notes").value,q));
  });
  bind("library-backup",async()=>{await ready;download("pmut-experiment-library.json",L.backup(records));});
  bind("library-import",()=>$("library-file").click());
  $("library-file").addEventListener("change",async e=>{
    try{
      await ready;const f=e.target.files[0];if(!f)return;if(f.size>100*1024*1024)throw Error("实验库备份须小于 100 MiB。");
      const added=L.restore(JSON.parse(await f.text()),records);let durable=Boolean(db);
      if(db)try{await db.addMany(added);}catch(error){durable=false;api.notice("本地存储失败："+error.message,"error");}
      records.push(...added);displayLibrary();say("library-status","恢复 "+added.length+" 条；重复 ID 已跳过。"+(durable?"":"记录仅保留在本页，请备份。"),!durable);
    }catch(error){say("library-status",error.message,true);}finally{e.target.value="";}
  });
  bind("library-compare",()=>{
    const chosen=records.filter(r=>selected.has(r.id));if(chosen.length<2||chosen.length>4)throw Error("请选择 2–4 个实验。");
    const out=$("library-comparison");out.replaceChildren();
    const metrics=document.createElement("div");metrics.className="table-wrap";out.append(metrics);
    table(metrics,["指标",...chosen.map(r=>r.name)],T.keys.map(k=>[labels[k],...chosen.map(r=>number(T.summary(r.snapshot.metrics)[k],k))]));
    const maps=document.createElement("div");maps.className="lab-maps";out.append(maps);
    const first=chosen[0].snapshot,same=chosen.every(r=>T.stable(r.snapshot.axes.x)===T.stable(first.axes.x)&&T.stable(r.snapshot.axes.y)===T.stable(first.axes.y)&&r.snapshot.config.focus.z_m===first.config.focus.z_m);
    const maximum=Math.max(...chosen.map(r=>r.snapshot.field.rms.reduce((a,b)=>Math.max(a,b),0)));
    function map(name,s,values,opts){
      const fig=document.createElement("div");fig.className="figure";const h=document.createElement("h3");h.textContent=name;const canvas=document.createElement("canvas");canvas.setAttribute("role","img");canvas.setAttribute("aria-label",name);fig.append(h,canvas);maps.append(fig);
      api.heatmap(canvas,values,s.axes.x,s.axes.y,opts);
    }
    for(const r of chosen)map(r.name+" · z="+number(r.snapshot.config.focus.z_m*1000)+" mm",r.snapshot,r.snapshot.field.rms,{unit:"Pa RMS",max:maximum||1});
    if(same)for(const r of chosen.slice(1)){
      const d=r.snapshot.field.rms.map((v,i)=>v-first.field.rms[i]),peak=d.reduce((a,b)=>Math.max(a,Math.abs(b)),0)||1;
      map(r.name+" − "+chosen[0].name,r.snapshot,d,{unit:"Δ Pa RMS",min:-peak,max:peak});
    }
    const note=document.createElement("p");note.className="hint";note.textContent=same?"统一声压色标；差值为对应网格 RMS 声压之差。":"坐标网格或焦平面不同：仅并排展示，未重采样，不计算差值。";out.append(note);
  });
  function staticCopy(c,id){
    c=K.clone(c);
    if(c.trajectory.kind!=="static"){if(!$(id).checked)throw Error("该实验含运动轨迹，请勾选创建静态副本。");c.trajectory.kind="static";c.modulation.duration_s=.05;}
    return c;
  }
  const sweepScale=()=>({"carrier_hz":1000,"focus.z_m":.001,"array.pitch_m":.001}[$("sweep-parameter").value]||1);
  function sweepTask(){
    const t={schema_version:1,kind:"sweep",config:staticCopy(api.read(),"sweep-static"),parameter:$("sweep-parameter").value,normalization:$("sweep-normalization").value,frequency_pitch:$("sweep-pitch").value};
    const scale=sweepScale();
    if($("sweep-mode").value==="list"){
      const parts=$("sweep-values").value.trim().split(/[,，\s]+/);if(parts.some(x=>!x))throw Error("数值列表不能为空。");
      t.values=parts.map(x=>Number(x)*scale);
    }else{t.start=$("sweep-start").valueAsNumber*scale;t.stop=$("sweep-stop").valueAsNumber*scale;t.count=$("sweep-count").valueAsNumber;}
    T.values(t);return t;
  }
  function robustTask(){return {schema_version:1,kind:"robustness",config:staticCopy(api.read(),"robust-static"),count:$("robust-count").valueAsNumber,quantization_comparison:$("robust-quantization").checked};}
  $("sweep-mode").addEventListener("change",()=>{const list=$("sweep-mode").value==="list";for(const id of ["sweep-start","sweep-stop","sweep-count"])$(id).disabled=list;$("sweep-values").disabled=!list;});
  $("sweep-parameter").addEventListener("change",()=>{
    const defaults={"focus.z_m":[30,70,9],"carrier_hz":[90,130,9],"array.side":[8,16,5],"array.pitch_m":[1,2,6],"array.pitch_wavelengths":[.35,.8,10],"element.velocity_peak_m_s":[.5,1.5,5]};
    const [a,b,n]=defaults[$("sweep-parameter").value];$("sweep-start").value=a;$("sweep-stop").value=b;$("sweep-count").value=n;$("sweep-values").value=[a,(a+b)/2,b].join(",");
  });
  function rowTable(id,out){
    table(id,["样本 / 取值","相位位数","状态 / 原因","间距 mm",...T.keys.map(k=>labels[k])],out.rows.map(r=>[
      out.task.kind==="sweep"?number(r.value/(out.task.parameter==="carrier_hz"?1000:["focus.z_m","array.pitch_m"].includes(out.task.parameter)?.001:1)):r.index+1,
      r.phase_bits===null?"—":r.phase_bits||"连续",r.status==="ok"?"完成":r.reason,number(r.pitch_m*1000),...T.keys.map(k=>number(r.metrics?.[k],k))]));
  }
  function plots(id,out){
    const el=$(id);if(window.Plotly)for(const child of el.children)Plotly.purge(child);el.replaceChildren();
    if(!window.Plotly)return;
    for(const key of T.keys){
      const div=document.createElement("div");div.className="lab-plot";el.append(div);
      let traces;
      if(out.task.kind==="sweep"){
        const unit=out.task.parameter==="carrier_hz"?1000:["focus.z_m","array.pitch_m"].includes(out.task.parameter)?.001:1;
        traces=[{type:"scatter",mode:"lines+markers",x:out.rows.map(r=>r.value/unit),y:out.rows.map(r=>r.status==="ok"&&r.metrics[key]!==null?r.metrics[key]*scale(key):null),connectgaps:false,line:{color:"#146f84"}}];
      }else{
        traces=Object.keys(out.statistics||{}).map(b=>({type:"histogram",name:b==="0"?"连续相位":b+" 位",opacity:.6,x:out.rows.filter(r=>String(r.phase_bits)===b&&r.status==="ok"&&r.metrics[key]!==null).map(r=>r.metrics[key]*scale(key))}));
      }
      Plotly.newPlot(div,traces,{title:{text:labels[key],font:{size:13}},margin:{l:60,r:15,t:45,b:45},paper_bgcolor:"#fff",plot_bgcolor:"#fff",font:{family:"PingFang SC, Microsoft YaHei, sans-serif",color:"#15364c",size:11},barmode:"overlay",xaxis:{title:{text:out.task.kind==="sweep"?"扫描参数（界面单位）":labels[key]}},yaxis:{title:{text:out.task.kind==="sweep"?labels[key]:"样本数"}},legend:{orientation:"h"}},{responsive:true,displayModeBar:false}).catch(()=>{div.textContent="图表无法绘制，数值表和导出仍可使用。";});
    }
  }
  function robustSummary(out){
    const rows=[];
    for(const [bits,stats] of Object.entries(out.statistics||{}))for(const k of T.keys){
      const v=stats[k],ideal=out.ideal[k],delta=v.median!==null&&ideal!==null?v.median-ideal:null;
      rows.push([bits==="0"?"连续":bits+" 位",labels[k],number(ideal,k),number(v.median,k),number(delta,k),number(v.p5,k),number(v.p95,k),v.valid,v.missing]);
    }
    table("robust-summary",["相位","指标","理想基准","中位数","中位数 − 理想","P5","P95","有效","缺失/无效"],rows);
  }
  async function runBatch(kind){
    const task=kind==="sweep"?sweepTask():robustTask(),prefix=kind==="sweep"?"sweep":"robust",job=api.startJob();
    if(kind==="sweep")lastSweep=null;else lastRobust=null;
    $(prefix+"-export").disabled=true;
    say(prefix+"-status","正在运行；可在顶部取消，已完成的结果会保留。");
    try{
      const out=await T.batch(task,job.compute,(row,partial,total)=>{
        if(kind==="sweep")lastSweep=partial;else lastRobust=partial;
        $(prefix+"-export").disabled=false;say(prefix+"-status","已完成 "+partial.rows.length+" / "+total+" 组；本组"+(row.status==="ok"?"成功":"无效："+row.reason));
        rowTable(prefix+"-results",partial);
      },job.stop);
      if(kind==="sweep")lastSweep=out;else{lastRobust=out;robustSummary(out);}
      rowTable(prefix+"-results",out);plots(prefix+"-plots",out);$(prefix+"-export").disabled=false;
      say(prefix+"-status",(out.status==="cancelled"?"已取消":"已完成")+"，保留 "+out.rows.length+" 组。"+(kind==="robustness"?"P5–P95 为样本分位范围。":"失败组合的原因已列出。"));
    }catch(e){say(prefix+"-status",e.message,true);}finally{job.finish();}
  }
  bind("sweep-run",()=>runBatch("sweep"));bind("robust-run",()=>runBatch("robustness"));
  bind("sweep-task",()=>download("pmut-sweep-task.json",sweepTask()));
  bind("robust-task",()=>download("pmut-robustness-task.json",robustTask()));
  bind("sweep-export",()=>{if(lastSweep)download("pmut-sweep-results.json",lastSweep);});
  bind("robust-export",()=>{if(lastRobust)download("pmut-robustness-results.json",lastRobust);});
  const statuses={pass:"达到参考阈值",sensitive:"对该项敏感",unevaluable:"不可评价",unchecked:"未检查"};
  function qualityRows(report){
    const rows=[];
    for(const [kind,label] of [["grid","网格加密"],["region","区域扩大"]]){
      const check=report.checks[kind];
      if(check.status)rows.push([label,statuses[check.status]||check.status,"—",check.reason]);
      else for(const [metric,item] of Object.entries(check))rows.push([label+" / "+(labels[metric]||metric),statuses[item.status]||item.status,Number.isFinite(item.relative_change)?number(item.relative_change*100)+"%":"—",Number.isFinite(item.threshold)?"参考阈值 "+number(item.threshold*100)+"%":item.reason]);
    }
    for(const key of ["pressure_x_minus6db","pressure_y_minus6db"]){const v=report.checks[key];rows.push([key.startsWith("pressure_x")?"x 主瓣":"y 主瓣",v.clipped?"视野截断":v.reason==="zero_signal"?"无信号":"完整",number(v.width_m,"pressure_x_minus6db_m")+" mm","仅目标平面"]); }
    const reference=report.checks.reference;
    rows.push(["独立圆盘积分",statuses[reference.status]||reference.status,Number.isFinite(reference.relative_l2_error)?number(reference.relative_l2_error*100)+"%":"—",reference.reason]);
    rows.push(["横向焦点偏差","平面内采样估计",number(report.checks.focus.lateral_error_m*1000)+" mm","不代表三维峰值定位"]);
    return rows;
  }
  function renderQuality(){
    $("quality-export").disabled=!qualityReport;
    if(!qualityReport){$("quality-results").replaceChildren();say("quality-status","尚未检查。");return;}
    table("quality-results",["检查","结论","变化 / 数值","范围 / 原因"],qualityRows(qualityReport));
    const r=api.getResult(),matches=r&&T.configKey(r.config)===T.configKey(qualityReport.config);
    say("quality-status",matches?"报告对应当前已计算结果。":"报告对应另一个配置或静态副本；不会附加到当前实验。",!matches);
  }
  function qualityConfig(){const r=api.getResult();if(!r)throw Error("先运行一次仿真。");return staticCopy(r.config,"quality-static");}
  bind("quality-run",async()=>{
    const c=qualityConfig(),job=api.startJob();say("quality-status","正在分别检查网格和积分区域…");
    try{qualityReport=await T.quality(c,job.compute,{grid_tolerance:$("quality-grid").valueAsNumber/100,region_tolerance:$("quality-region").valueAsNumber/100});renderQuality();}
    catch(e){say("quality-status",job.stop()?"已取消检查；保留先前报告。":e.message,true);}
    finally{job.finish();}
  });
  bind("quality-config",()=>api.download("pmut-quality-config.toml",K.toml(qualityConfig()),"text/plain"));
  bind("quality-export",()=>{if(qualityReport)download("pmut-quality.json",qualityReport);});
  bind("quality-import",()=>$("quality-file").click());
  $("quality-file").addEventListener("change",async e=>{
    try{
      const f=e.target.files[0];if(!f)return;if(f.size>5*1024*1024)throw Error("报告不得超过 5 MiB。");
      const report=JSON.parse(await f.text()),c=qualityConfig();
      if(report.schema_version!==1||report.model_version!==T.version||T.configKey(report.config)!==T.configKey(c))throw Error("报告配置或模型版本不匹配。请导出检查用 TOML 后运行 Python quality --reference。");
      qualityRows(report);qualityReport=report;renderQuality();
    }catch(error){say("quality-status",error.message,true);}finally{e.target.value="";}
  });
  bind("experiment-report",()=>{
    const r=api.getResult();if(!r)throw Error("先运行一次仿真。");
    const q=qualityReport&&T.configKey(qualityReport.config)===T.configKey(r.config)?qualityReport:null;
    const wrap=document.createElement("div");wrap.style.cssText="position:absolute;left:-10000px;width:680px";const canvas=document.createElement("canvas");canvas.style.cssText="width:680px;height:440px";wrap.append(canvas);document.body.append(wrap);
    api.heatmap(canvas,r.field.rms,r.axes.x,r.axes.y,{unit:"Pa RMS"});const map=canvas.toDataURL("image/png");wrap.remove();
    const rows=T.keys.map(k=>"<tr><th>"+esc(labels[k])+"</th><td>"+esc(number(T.summary(r.metrics)[k],k))+"</td></tr>").join("");
    const checks=q?"<h2>数值质量检查</h2><table>"+qualityRows(q).map(row=>"<tr>"+row.map(v=>"<td>"+esc(v)+"</td>").join("")+"</tr>").join("")+"</table>":"<p>此实验尚未附有匹配的数值质量报告。</p>";
    const html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>pMUT 实验摘要</title><style>body{font:15px/1.7 "PingFang SC","Microsoft YaHei",sans-serif;color:#15364c;max-width:850px;margin:35px auto;padding:0 20px}h1{font-size:26px}h2{font-size:19px}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #d6e2eb;padding:8px;text-align:left}img{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}@media print{body{margin:0}img{max-height:90mm}tr{break-inside:avoid}}</style><h1>'+esc($("experiment-name").value.trim()||r.config.title)+'</h1><p>'+esc($("experiment-notes").value)+'</p><p>模型 '+esc(r.metrics.model_version||T.version)+'；导出时间 '+esc(new Date().toISOString())+'</p><p>均匀圆活塞和法向辐射压近似；振速为输入假设，未经过实物标定。合力仅覆盖有限平面。浏览器打印可保存为 PDF。</p><img alt="焦平面 RMS 声压" src="'+map+'"><table>'+rows+'</table>'+checks+'<h2>复现配置（SI 单位）</h2><pre>'+esc(K.toml(r.config))+'</pre><h2>实际误差样本</h2><pre>'+esc(api.serialize(r.sample))+'</pre></html>';
    api.download("pmut-experiment-report.html",html,"text/html");
  });
  return {onResult(){editing=null;$("library-save").textContent="保存当前实验";renderQuality();},refresh(){for(const id of ["sweep-plots","robust-plots"])if(!$(id).closest("[role=tabpanel]").hidden&&window.Plotly)for(const child of $(id).children)Plotly.Plots.resize(child).catch(()=>{});}};
}
