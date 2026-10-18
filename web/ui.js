/* Offline UI. Canvas fields and embedded Plotly geometry; no external resources. */
(() => {
  "use strict";
  const K=createPmutKernel(), T=createPmutTasks(K), $=id=>document.getElementById(id);
  let lab=null;
  let draft=K.clone(K.defaults),result=null,baseline=null,busy=false,generation=0,active=null,animation=null;
  const limits=new WeakMap(),fonts='"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif';
  const bindings={
    nx:["array","nx",1],ny:["array","ny",1],carrier:[null,"carrier_hz",1000],
    radius:["element","radius_m",.000001],pitch:["array","pitch_wavelengths",1],
    "physical-pitch":["array","pitch_m",.001],
    "error-phase":["array","phase_error_std_deg",1],"error-amplitude":["imperfections","amplitude_cv",1],
    "error-position":["imperfections","position_std_m",.000001],"error-failure":["imperfections","failure_probability",1],
    "phase-bits":["imperfections","phase_bits",1],"error-seed":[null,"seed",1],
    velocity:["element","velocity_peak_m_s",1],fx:["focus","x_m",.001],fy:["focus","y_m",.001],fz:["focus","z_m",.001],
    "mod-frequency":["modulation","frequency_hz",1],duty:["modulation","duty_cycle",1],depth:["modulation","depth",1],
    frames:["trajectory","frames",1],"path-duration":["trajectory","duration_s",1],
    attenuation:["medium","attenuation_np_m",1],reflection:[null,"reflection_factor",1]
  };
  const fmt=(value,digits=2)=>value===null||!Number.isFinite(value)?"—":Number(value).toLocaleString("en-US",{minimumFractionDigits:digits,maximumFractionDigits:digits});
  const plain=value=>Number(Number(value).toPrecision(12));
  function fill(c) {
    draft=K.clone(c);
    $("pitch-mode").value=c.array.pitch_mode;$("error-rng").value=c.imperfections.rng;
    for(const [id,[section,key,scale]] of Object.entries(bindings)) $(id).value=plain((section?c[section][key]:c[key])/scale);
    $("apodization").value=c.array.apodization;$("motion").value=c.trajectory.kind;$("modulation").value=c.modulation.kind;
    $("grid").value=c.grid.nx;
    $("path-size").value=plain((c.trajectory.kind==="line"?c.trajectory.line_length_m/2:c.trajectory.radius_m)*1000);
    for(const [id,axis] of [["fx","x"],["fy","y"],["fz","z"]]) {
      $(id).min=plain(c.grid[axis+"_min_m"]*1000);$(id).max=plain(c.grid[axis+"_max_m"]*1000);$(id).step=".1";
    }
    updateDependentControls();
  }
  function read() {
    const c=K.clone(draft);
    for(const [id,[section,key,scale]] of Object.entries(bindings)) {
      const value=$(id).valueAsNumber*scale;
      if(section)c[section][key]=value;else c[key]=value;
    }
    c.array.pitch_mode=$("pitch-mode").value;c.imperfections.rng=$("error-rng").value;
    c.array.apodization=$("apodization").value;c.trajectory.kind=$("motion").value;c.modulation.kind=$("modulation").value;
    c.grid.nx=$("grid").valueAsNumber;c.grid.ny=c.grid.nx;
    if(c.trajectory.kind==="circle") c.trajectory.radius_m=$("path-size").valueAsNumber*.001;
    if(c.trajectory.kind==="line") c.trajectory.line_length_m=$("path-size").valueAsNumber*.002;
    if(c.trajectory.kind!=="static") c.modulation.duration_s=c.trajectory.duration_s;
    else if(draft.trajectory.kind!=="static") c.modulation.duration_s=.05;
    c.title={"static":"空中静态触点","line":"往复直线触点","circle":"圆形移动触点"}[c.trajectory.kind];
    return K.validate(c);
  }
  function updateDependentControls() {
    $("pitch").disabled=$("pitch-mode").value==="physical";$("physical-pitch").disabled=$("pitch-mode").value!=="physical";
    const moving=$("motion").value!=="static";
    $("path-size").disabled=!moving;$("path-duration").disabled=!moving;$("frames").disabled=!moving;
    $("duty").disabled=$("modulation").value!=="burst";
    $("mod-frequency").disabled=$("modulation").value==="cw";$("depth").disabled=$("modulation").value==="cw";
  }
  function notice(text,kind="") {$("status").textContent=text;$("status").className="notice"+(kind?" "+kind:"");}
  function markDirty() {
    updateDependentControls();
    if(result) notice(busy?"参数已改变。当前计算仍使用开始时的参数，完成后可再次运行。":"参数已改变，图表仍是上一次结果。点击“运行仿真”更新。","stale");
  }
  function setBusy(value) {
    for(const el of document.querySelectorAll("[data-lab-run]"))el.disabled=value;
    busy=value;$("run").disabled=value;$("reset").disabled=value;$("import").disabled=value;
    $("progress-row").hidden=!value;$("run").textContent=value?"正在计算…":"运行仿真";
  }
  function cleanup() {
    if(active?.worker) active.worker.terminate();
    if(active?.url) URL.revokeObjectURL(active.url);
    active=null;
  }
  function compute(c,token,sample=null,diagnostic=false) {
    return new Promise((resolve,reject)=>{
      const progress=value=>{if(token===generation)$("progress").value=value;};
      active={reject};
      const fallback=()=>{
        if(active?.worker)active.worker.terminate();
        if(active?.url)URL.revokeObjectURL(active.url);
        active={reject};
        K.simulate(c,progress,()=>token!==generation,sample,diagnostic).then(resolve,reject);
      };
      try {
        if(typeof Worker==="undefined") {fallback();return;}
        const source="const K=("+createPmutKernel.toString()+")();self.onmessage=async e=>{try{const r=await K.simulate(e.data.config,p=>self.postMessage({kind:'progress',value:p}),()=>false,e.data.sample,e.data.diagnostic);self.postMessage({kind:'result',value:r});}catch(error){self.postMessage({kind:'error',value:error.message});}};";
        const url=URL.createObjectURL(new Blob([source],{type:"text/javascript"}));
        const worker=new Worker(url);active={reject,worker,url};let started=false;
        worker.onmessage=e=>{
          if(token!==generation)return;
          const message=e.data;
          if(message.kind==="progress"){started=true;progress(message.value);}
          else if(message.kind==="result")resolve(message.value);
          else reject(Error(message.value));
        };
        worker.onerror=event=>{event.preventDefault();if(!started)fallback();else reject(Error("后台计算中断，请减小计算规模后重试。"));};
        worker.postMessage({config:c,sample,diagnostic});
      } catch {fallback();}
    });
  }
  async function run() {
    if(busy)return;
    if(!$("config-form").reportValidity())return;
    let c;try{c=read();}catch(error){notice(error.message,"error");return;}
    stopAnimation();const token=++generation;
    setBusy(true);$("progress").value=0;notice("正在计算声场与刺激…");
    try {
      const next=await compute(c,token);
      if(token!==generation)return;
      result=next;draft=K.clone(c);$("frame").value=0;$("frame").max=next.trajectory.frames.length-1;
      for(const id of ["save-config","save-baseline","export-toml","export-metrics","export-data","export-csv"]) $(id).disabled=false;
      $("play").disabled=next.trajectory.frames.length===1;$("frame").disabled=next.trajectory.frames.length===1;
      render();lab?.onResult();
      let changed=false;
      try{changed=JSON.stringify(read())!==JSON.stringify(c);}catch{changed=true;}
      if(changed)notice("参数已改变，当前显示刚完成的结果。点击“运行仿真”更新。","stale");
      else notice("计算完成。可点击焦平面设定新的焦点，或切换到调制与移动。");
    } catch(error) {if(token===generation)notice(error.message,"error");}
    finally {if(token===generation){cleanup();setBusy(false);}}
  }
  $("cancel").addEventListener("click",()=>{
    generation++;const reject=active?.reject;cleanup();if(reject)reject(Error("计算已取消。"));setBusy(false);
    notice(result?"计算已取消，保留上一次结果。":"计算已取消，可调整参数后重新运行。");
  });
  $("config-form").addEventListener("submit",event=>{event.preventDefault();run();});
  $("config-form").addEventListener("input",markDirty);
  $("config-form").addEventListener("change",markDirty);
  $("motion").addEventListener("change",()=>{
    $("path-size").value=$("motion").value==="line"?7.5:5;updateDependentControls();
  });
  $("reset").addEventListener("click",()=>{fill(K.clone(K.defaults));run();});
  $("import").addEventListener("click",()=>$("config-file").click());
  $("config-file").addEventListener("change",async event=>{
    const file=event.target.files[0];if(!file)return;
    try {
      if(file.size>1024*1024)throw Error("配置文件应小于 1 MiB，请选择配置文件而非完整数据。");
      const text=await file.text();
      const parsed=file.name.toLowerCase().endsWith(".toml")?K.parseToml(text):JSON.parse(text);
      const c=K.validate(parsed.config||parsed);
      if(c.grid.nx!==c.grid.ny)throw Error("HTML 面板使用方形平面网格，请将 grid.nx 和 grid.ny 设为相同。");
      fill(c);notice("配置已导入。点击“运行仿真”查看结果。","stale");
    } catch(error){notice("导入失败："+error.message,"error");}
    finally{event.target.value="";}
  });
  function setup(canvas) {
    const width=Math.max(120,canvas.clientWidth),height=Math.max(100,canvas.clientHeight),dpr=Math.min(window.devicePixelRatio||1,2);
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
    const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
    ctx.font="12px "+fonts;ctx.fillStyle="#60788a";ctx.strokeStyle="#d6e2eb";
    return {ctx,width,height};
  }
  const colorStops=[[0,16,36,68],[.24,55,67,123],[.5,42,139,173],[.73,99,198,182],[1,255,229,133]];
  function color(t) {
    t=Math.min(1,Math.max(0,t));let a=colorStops[0],b=colorStops[1];
    for(let i=1;i<colorStops.length;i++)if(t<=colorStops[i][0]){a=colorStops[i-1];b=colorStops[i];break;}
    const f=(t-a[0])/(b[0]-a[0]);
    return [1,2,3].map(k=>Math.round(a[k]+(b[k]-a[k])*f));
  }
  const lut=Array.from({length:256},(_,i)=>color(i/255));
  const maximum=values=>{let value=0;for(const x of values)value=Math.max(value,x);return value;};
  function heatmap(canvas,values,x,y,options={}) {
    const {ctx,width,height}=setup(canvas),left=48,top=25,right=66,bottom=38;
    const xr=(x[x.length-1]-x[0])*1000,yr=(y[y.length-1]-y[0])*1000;
    const scale=Math.min((width-left-right)/xr,(height-top-bottom)/yr);
    const pw=xr*scale,ph=yr*scale,l=left+(width-left-right-pw)/2,t=top+(height-top-bottom-ph)/2;
    const min=options.min??0,max=options.max??maximum(values),denom=max-min||1;
    const tile=document.createElement("canvas");tile.width=x.length;tile.height=y.length;
    const tc=tile.getContext("2d"),pixels=tc.createImageData(x.length,y.length);
    for(let iy=0;iy<y.length;iy++)for(let ix=0;ix<x.length;ix++) {
      const at=iy*x.length+ix,dest=((y.length-1-iy)*x.length+ix)*4;
      const index=Math.min(255,Math.max(0,Math.round((values[at]-min)/denom*255)));
      const rgb=lut[index];pixels.data[dest]=rgb[0];pixels.data[dest+1]=rgb[1];pixels.data[dest+2]=rgb[2];pixels.data[dest+3]=255;
    }
    tc.putImageData(pixels,0,0);ctx.imageSmoothingEnabled=true;ctx.drawImage(tile,l,t,pw,ph);
    ctx.strokeStyle="#aabfce";ctx.strokeRect(l,t,pw,ph);
    const px=value=>l+(value-x[0])/(x[x.length-1]-x[0])*pw;
    const py=value=>t+ph-(value-y[0])/(y[y.length-1]-y[0])*ph;
    ctx.fillStyle="#60788a";ctx.font="11px "+fonts;ctx.textAlign="center";
    for(let i=0;i<=4;i++) {
      const xx=x[0]+(x[x.length-1]-x[0])*i/4;
      ctx.fillText(fmt(xx*1000,0),l+pw*i/4,t+ph+18);
      const yy=y[0]+(y[y.length-1]-y[0])*i/4;
      ctx.textAlign="right";ctx.fillText(fmt(yy*1000,0),l-8,t+ph-ph*i/4+4);ctx.textAlign="center";
    }
    ctx.fillText("x (mm)",l+pw/2,height-4);
    ctx.save();ctx.translate(12,t+ph/2);ctx.rotate(-Math.PI/2);ctx.fillText((options.yName||"y")+" (mm)",0,0);ctx.restore();
    const barX=width-43,barY=top+28,barH=Math.min(ph,200);
    for(let i=0;i<barH;i++){const rgb=color(1-i/barH);ctx.fillStyle="rgb("+rgb.join(",")+")";ctx.fillRect(barX,barY+i,11,1.5);}
    ctx.fillStyle="#60788a";ctx.textAlign="left";ctx.font="10px "+fonts;
    ctx.fillText(options.unit||"Pa",barX-5,barY-24);
    const decimals=Math.max(Math.abs(min),Math.abs(max))<1?3:Math.max(Math.abs(min),Math.abs(max))<10?1:0;
    ctx.fillText(fmt(max,decimals),barX-4,barY-8);ctx.fillText(fmt(min,decimals),barX-4,barY+barH+15);
    if(options.path?.length>1) {
      ctx.beginPath();options.path.forEach((p,i)=>i?ctx.lineTo(px(p[0]),py(p[1])):ctx.moveTo(px(p[0]),py(p[1])));
      ctx.strokeStyle="rgba(255,255,255,.75)";ctx.lineWidth=1.5;ctx.setLineDash([3,4]);ctx.stroke();ctx.setLineDash([]);
    }
    if(options.target) {
      const tx=px(options.target[0]),ty=py(options.target[1]);ctx.strokeStyle="#fff";ctx.lineWidth=1.6;
      ctx.beginPath();ctx.arc(tx,ty,6,0,2*Math.PI);ctx.moveTo(tx-9,ty);ctx.lineTo(tx+9,ty);ctx.moveTo(tx,ty-9);ctx.lineTo(tx,ty+9);ctx.stroke();
    }
    if(max===0&&min===0){ctx.fillStyle="white";ctx.textAlign="center";ctx.font="13px "+fonts;ctx.fillText("无有效声场",l+pw/2,t+ph/2);}
    limits.set(canvas,{l,t,pw,ph,x,y,values});
  }
  function lineChart(canvas,x,values,options={}) {
    const {ctx,width,height}=setup(canvas),l=50,r=18,t=24,b=40,pw=width-l-r,ph=height-t-b;
    const xmin=x[0],xmax=x[x.length-1]===xmin?xmin+1:x[x.length-1];
    const ymin=options.min??0,ymax=options.max??(maximum(values)*1.08||1);
    const px=v=>l+(v-xmin)/(xmax-xmin)*pw,py=v=>t+ph-(v-ymin)/(ymax-ymin)*ph;
    ctx.font="11px "+fonts;
    for(let i=0;i<=4;i++) {
      const yy=ymin+(ymax-ymin)*i/4,yt=py(yy);
      ctx.beginPath();ctx.moveTo(l,yt);ctx.lineTo(l+pw,yt);ctx.strokeStyle="#e3ebf0";ctx.stroke();
      ctx.fillStyle="#60788a";ctx.textAlign="right";ctx.fillText(fmt(yy,Math.abs(ymax)<1?2:0),l-8,yt+4);
      const xx=xmin+(xmax-xmin)*i/4;ctx.textAlign="center";ctx.fillText(fmt(xx,Math.abs(xmax)<1?2:0),px(xx),height-20);
    }
    ctx.beginPath();for(let i=0;i<x.length;i++){const yy=Math.min(ymax,Math.max(ymin,values[i]));i?ctx.lineTo(px(x[i]),py(yy)):ctx.moveTo(px(x[i]),py(yy));}
    ctx.strokeStyle="#146f84";ctx.lineWidth=1.8;ctx.stroke();
    if(options.threshold!==undefined) {
      ctx.strokeStyle="#dd7b22";ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(l,py(options.threshold));ctx.lineTo(l+pw,py(options.threshold));ctx.stroke();ctx.setLineDash([]);
    }
    ctx.textAlign="center";ctx.fillStyle="#60788a";ctx.fillText(options.xLabel||"",l+pw/2,height-2);
    ctx.textAlign="left";ctx.fillText(options.unit||"",l,t-10);
  }
  function arrayChart() {
    const canvas=$("array-chart"),{ctx,width,height}=setup(canvas),pos=result.positions,c=result.config;
    const w=K.weights(result.nominalPositions||K.positions(c),[c.focus.x_m,c.focus.y_m,c.focus.z_m],c,result.sample);
    const span=Math.max(c.array.nx,c.array.ny)*result.metrics.pitch_m,scale=Math.min(width-20,height-20)/span;
    pos.forEach((p,i)=>{
      const angle=Math.atan2(w.im[i],w.re[i]),hue=(angle/Math.PI*180+360)%360;
      ctx.fillStyle="hsl("+hue+",40%,47%)";ctx.beginPath();ctx.arc(width/2+p[0]*scale,height/2-p[1]*scale,Math.max(1,Math.min(3,scale*c.element.radius_m)),0,2*Math.PI);ctx.fill();
    });
  }

  // The same Scatter3d view as the Python demo; Plotly is embedded in the HTML.
  let geometryResult=null,geometryPending=false;
  const geometryCamera={
    eye:{x:1.95,y:1.95,z:1.4},center:{x:0,y:0,z:0},up:{x:0,y:0,z:1},projection:{type:"perspective"}
  };
  function renderGeometry() {
    if(!result||$("field-panel").hidden||geometryPending)return;
    const node=$("geometry-chart"),current=result,c=current.config;
    if(geometryResult===current) {
      if(typeof Plotly!=="undefined")Plotly.Plots.resize(node).catch(()=>{});
      return;
    }
    $("geometry-summary").textContent=current.positions.length+" 个阵元位于 z = 0 mm；"+
      (c.trajectory.kind==="static"
        ?"目标位置 ("+fmt(c.focus.x_m*1000,1)+", "+fmt(c.focus.y_m*1000,1)+", "+fmt(c.focus.z_m*1000,1)+") mm。"
        :{line:"往复直线",circle:"圆形"}[c.trajectory.kind]+"轨迹，"+current.trajectory.points.length+
          " 个采样点；目标高度 "+fmt(c.focus.z_m*1000,1)+" mm。");
    if(typeof Plotly==="undefined") {
      $("geometry-status").textContent="三维图未能加载，请重新打开完整 HTML 文件。";
      $("geometry-status").hidden=false;return;
    }
    const pos=current.positions,path=current.trajectory.points;
    const w=K.weights(current.nominalPositions||K.positions(c),[c.focus.x_m,c.focus.y_m,c.focus.z_m],c,current.sample);
    const coordinate=(points,axis)=>points.map(p=>p[axis]*1000);
    const traces=[
      {
        type:"scatter3d",mode:"markers",name:"阵元（相位）",
        x:coordinate(pos,0),y:coordinate(pos,1),z:coordinate(pos,2),
        text:pos.map((_p,i)=>"阵元 "+(i+1)),
        marker:{size:3.5,color:Array.from(w.re,(_r,i)=>Math.atan2(w.im[i],w.re[i])*180/Math.PI),
          cmin:-180,cmax:180,colorscale:"Twilight",opacity:1},
        hovertemplate:"%{text}<br>x %{x:.2f} mm<br>y %{y:.2f} mm<br>z %{z:.2f} mm<br>相位 %{marker.color:.1f}°<extra></extra>"
      },
      {
        type:"scatter3d",mode:path.length>1?"lines+markers":"markers",
        name:path.length>1?"目标轨迹":"目标位置",
        x:coordinate(path,0),y:coordinate(path,1),z:coordinate(path,2),
        customdata:Array.from(current.trajectory.times,t=>t*1000),
        marker:{size:path.length>1?3:6,color:"#dd7b22"},line:{color:"#dd7b22",width:5},
        hovertemplate:"目标<br>x %{x:.2f} mm<br>y %{y:.2f} mm<br>z %{z:.2f} mm<br>时刻 %{customdata:.0f} ms<extra></extra>"
      }
    ];
    // Equal physical scale, normalized by the longest axis so tall or narrow
    // configurations remain inside the initial camera view.
    const bounds=[0,1,2].map(axis=>{
      const values=coordinate(pos,axis).concat(coordinate(path,axis));
      return [Math.min(...values),Math.max(...values)];
    });
    const padding=Math.max(1,Math.max(...bounds.map(([lo,hi])=>hi-lo))*.06);
    const ranges=bounds.map(([lo,hi])=>[lo-padding,hi+padding]);
    const longest=Math.max(...ranges.map(([lo,hi])=>hi-lo));
    const aspect=Object.fromEntries(["x","y","z"].map((key,i)=>[key,1.8*(ranges[i][1]-ranges[i][0])/longest]));
    const axis=(title,index)=>({title:{text:title},range:ranges[index],
      showbackground:true,backgroundcolor:"#f3f7fb",
      gridcolor:"#d6e2eb",zerolinecolor:"#aabfce",showspikes:false,nticks:5});
    const layout={
      autosize:true,margin:{l:0,r:0,t:34,b:24},paper_bgcolor:"#ffffff",
      font:{family:fonts,color:"#15364c",size:12},showlegend:true,
      legend:{orientation:"h",x:0,y:1.06},
      modebar:{orientation:"v",bgcolor:"#ffffff",color:"#60788a",activecolor:"#146f84"},uirevision:"pmut-geometry-camera",
      scene:{xaxis:axis("x (mm)",0),yaxis:axis("y (mm)",1),zaxis:axis("z (mm)",2),
        aspectmode:"manual",aspectratio:aspect,dragmode:"orbit",camera:K.clone(geometryCamera)}
    };
    const options={responsive:true,displaylogo:false,displayModeBar:true,scrollZoom:true,
      modeBarButtons:[["toImage"],["zoom3d","pan3d","orbitRotation"],["resetCameraDefault3d"]],
      toImageButtonOptions:{format:"png",filename:"pmut-array-geometry",width:1200,height:900,scale:1}};
    geometryPending=true;$("geometry-status").hidden=true;
    for(const id of ["geometry-reset","geometry-top","geometry-side"])$(id).disabled=true;
    Promise.resolve().then(()=>Plotly.react(node,traces,layout,options)).then(()=>{
      geometryResult=current;
      for(const id of ["geometry-reset","geometry-top","geometry-side"])$(id).disabled=false;
    }).catch(()=>{
      $("geometry-status").textContent="三维图暂不可用，请检查浏览器是否支持 WebGL。其他计算和图表可继续使用。";
      $("geometry-status").hidden=false;
    }).finally(()=>{
      geometryPending=false;
      if(result!==current)renderGeometry();
    });
  }
  function setGeometryCamera(camera) {
    if(geometryResult&&!geometryPending&&typeof Plotly!=="undefined")Plotly.relayout($("geometry-chart"),{"scene.camera":K.clone(camera)});
  }
  $("geometry-reset").addEventListener("click",()=>setGeometryCamera(geometryCamera));
  $("geometry-top").addEventListener("click",()=>setGeometryCamera({
    eye:{x:0,y:0,z:2.2},center:{x:0,y:0,z:0},up:{x:0,y:1,z:0},projection:{type:"perspective"}
  }));
  $("geometry-side").addEventListener("click",()=>setGeometryCamera({
    eye:{x:0,y:-3,z:0},center:{x:0,y:0,z:0},up:{x:0,y:0,z:1},projection:{type:"perspective"}
  }));

  function reading(id,value,unit,digits=2) {
    $(id).replaceChildren(document.createTextNode(fmt(value,digits)));
    const small=document.createElement("small");small.textContent=unit;$(id).appendChild(small);
  }
  function renderComparison() {
    $("compare-empty").hidden=Boolean(baseline);$("comparison").hidden=!baseline;if(!baseline||!result)return;
    const rows=[
      ["阵列",r=>r.config.array.nx+" × "+r.config.array.ny],
      ["载波 kHz",r=>fmt(r.config.carrier_hz/1000,1)],
      ["最大 RMS 声压 Pa",r=>fmt(r.metrics.pressure_rms_max_pa)],
      ["最大辐射压 Pa",r=>fmt(r.metrics.radiation_pressure_max_pa,4)],
      ["区域合力 μN",r=>fmt(r.metrics.force_over_displayed_plane_n*1e6)],
      ["x 声压 −6 dB 宽度 mm",r=>r.metrics.pressure_x_minus6db.width_m===null?"不可用":fmt(r.metrics.pressure_x_minus6db.width_m*1000)],
      ["振速平方和 (m/s)²",r=>fmt(r.metrics.sum_squared_velocity_m2_s2)]
    ];
    $("comparison-body").replaceChildren();
    for(const [label,format] of rows) {
      const tr=document.createElement("tr");for(const text of [label,format(baseline),format(result)]){const td=document.createElement("td");td.textContent=text;tr.appendChild(td);}$("comparison-body").appendChild(tr);
    }
  }
  function renderMotion() {
    if(!result||$("motion-panel").hidden)return;
    if(result.archived){
      for(const id of ["motion-chart","wave-chart"]){const ctx=$(id).getContext("2d");ctx.clearRect(0,0,$(id).width,$(id).height);}
      $("wave-note").textContent="已打开静态快照；完整轨迹和波形未存入实验库。重新运行即可恢复。";return;
    }
    const at=Number($("frame").value),tr=result.trajectory;
    const peak=Math.max(...tr.frames.map(maximum));
    heatmap($("motion-chart"),tr.frames[at],result.axes.x,result.axes.y,{max:peak,unit:"Pa",path:tr.points,target:tr.points[at]});
    $("frame-time").textContent=fmt(tr.times[at]*1000,0)+" ms";
    lineChart($("wave-chart"),Array.from(result.wave.time,t=>t*1000),Array.from(result.wave.force,f=>f*1e6),{xLabel:"时间 (ms)",unit:"合力 (μN)"});
    $("wave-note").textContent="力随包络平方变化。平均平方包络 "+fmt(result.metrics.envelope_mean_square,3)+"；平均合力 "+fmt(result.metrics.plane_force_time_mean_n*1e6,3)+" μN。";
  }
  function render() {
    if(!result)return;
    const m=result.metrics,c=result.config,a=result.axes;
    reading("metric-pressure",m.pressure_rms_max_pa,"Pa");reading("metric-radiation",m.radiation_pressure_max_pa,"Pa",4);reading("metric-force",m.force_over_displayed_plane_n*1e6,"μN");
    if(m.pressure_x_minus6db.width_m===null)$("metric-width").textContent=m.pressure_x_minus6db.reason==="zero_signal"?"无信号":"超出视野";
    else reading("metric-width",m.pressure_x_minus6db.width_m*1000,"mm");
    $("geometry-note").textContent=c.array.nx+" × "+c.array.ny+" 阵元；间距 "+fmt(m.pitch_m*1000,3)+" mm；目标高度 "+fmt(c.focus.z_m*1000,1)+" mm。";
    $("run-info").textContent="浏览器计算 "+fmt(m.simulation_seconds,2)+" s；参数与结果可导出。";
    if(!$("field-panel").hidden) {
      const quantity=$("quantity").value;
      heatmap($("xy-chart"),quantity==="rms"?result.field.rms:result.field.radiation,a.x,a.y,{unit:quantity==="rms"?"Pa RMS":"Pa",target:[c.focus.x_m,c.focus.y_m]});
      const peak=maximum(result.field.xzRms);
      const db=Array.from(result.field.xzRms,v=>peak>0?20*Math.log10(Math.max(v/peak,.001)):-60);
      heatmap($("xz-chart"),db,a.x,a.z,{min:-60,max:0,unit:"dB",yName:"z",target:[c.focus.x_m,c.focus.z_m]});
      const px=result.field.profileX,profilePeak=maximum(px);
      lineChart($("profile-chart"),Array.from(a.x,v=>v*1000),px.map(v=>profilePeak>0?20*Math.log10(Math.max(v/profilePeak,.001)):-60),{min:-60,max:0,threshold:-6,xLabel:"x (mm)",unit:"相对声压 (dB)"});
      $("profile-note").textContent="橙线为声压 −6 dB。视野内 x 旁瓣："+(m.sidelobe_x_db===null?"未检出完整旁瓣":fmt(m.sidelobe_x_db,2)+" dB")+"。";
      arrayChart();renderGeometry();
    }
    renderMotion();renderComparison();lab?.refresh();
  }
  $("quantity").addEventListener("change",render);
  function stopAnimation() {if(animation!==null)cancelAnimationFrame(animation);animation=null;$("play").textContent="播放轨迹";}
  $("play").addEventListener("click",()=>{
    if(animation!==null){stopAnimation();return;}if(!result||result.archived||result.trajectory.frames.length<2)return;
    $("play").textContent="暂停";let previous=0;
    const tick=now=>{
      if(now-previous>=80) {
        let frame=Number($("frame").value)+1;if(frame>=result.trajectory.frames.length)frame=0;
        $("frame").value=frame;renderMotion();previous=now;
        if(frame===result.trajectory.frames.length-1){stopAnimation();return;}
      }
      animation=requestAnimationFrame(tick);
    };
    if(Number($("frame").value)===result.trajectory.frames.length-1)$("frame").value=0;
    animation=requestAnimationFrame(tick);
  });
  $("frame").addEventListener("input",()=>{stopAnimation();renderMotion();});
  const tabs=Array.from(document.querySelectorAll('[role="tab"]'));
  function selectTab(button) {
    stopAnimation();
    for(const tab of tabs){const selected=button===tab;tab.setAttribute("aria-selected",String(selected));tab.tabIndex=selected?0:-1;$(tab.getAttribute("aria-controls")).hidden=!selected;}
    render();
  }
  tabs.forEach((tab,i)=>{
    tab.addEventListener("click",()=>selectTab(tab));
    tab.addEventListener("keydown",event=>{
      let index=i;if(event.key==="ArrowRight")index=(i+1)%tabs.length;else if(event.key==="ArrowLeft")index=(i+tabs.length-1)%tabs.length;else if(event.key==="Home")index=0;else if(event.key==="End")index=tabs.length-1;else return;
      event.preventDefault();tabs[index].focus();selectTab(tabs[index]);
    });
  });
  $("save-baseline").addEventListener("click",()=>{
    if(!result)return;baseline={config:K.clone(result.config),metrics:K.clone(result.metrics)};renderComparison();
    $("save-baseline").textContent="用当前结果更新基准";
  });
  function hit(event) {
    const canvas=$("xy-chart"),r=limits.get(canvas);if(!r)return null;
    const box=canvas.getBoundingClientRect(),px=event.clientX-box.left-r.l,py=event.clientY-box.top-r.t;
    if(px<0||py<0||px>r.pw||py>r.ph)return null;
    const x=r.x[0]+px/r.pw*(r.x[r.x.length-1]-r.x[0]),y=r.y[r.y.length-1]-py/r.ph*(r.y[r.y.length-1]-r.y[0]);
    const ix=Math.round(px/r.pw*(r.x.length-1)),iy=Math.round((1-py/r.ph)*(r.y.length-1));
    return {x,y,value:r.values[iy*r.x.length+ix]};
  }
  $("xy-chart").addEventListener("pointermove",event=>{
    const p=hit(event);if(!p)return;
    $("pointer-readout").textContent="x "+fmt(p.x*1000,1)+" mm，y "+fmt(p.y*1000,1)+" mm；"+fmt(p.value,$("quantity").value==="rms"?2:4)+" Pa"+($("quantity").value==="rms"?" RMS":"")+"。";
  });
  $("xy-chart").addEventListener("pointerleave",()=>$("pointer-readout").textContent="点击图面设定焦点位置，再运行仿真。");
  $("xy-chart").addEventListener("click",event=>{
    const p=hit(event);if(!p)return;$("fx").value=(p.x*1000).toFixed(1);$("fy").value=(p.y*1000).toFixed(1);markDirty();
  });
  function download(name,text,type="application/json") {
    const url=URL.createObjectURL(new Blob([text],{type:type+";charset=utf-8"})),link=document.createElement("a");
    link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
  }
  const serialize=value=>JSON.stringify(value,(_key,v)=>ArrayBuffer.isView(v)?Array.from(v):v,2);
  $("save-config").addEventListener("click",()=>{if(result)download("pmut-config.json",serialize(result.config));});
  $("export-toml").addEventListener("click",()=>{if(result)download("pmut-config.toml",K.toml(result.config),"text/plain");});
  $("export-metrics").addEventListener("click",()=>{if(result)download("pmut-metrics.json",serialize(result.metrics));});
  $("export-data").addEventListener("click",()=>{
    if(result)download("pmut-data.json",serialize({format_version:1,created_at:new Date().toISOString(),complex_pressure:"field.re and field.im are peak pressure in Pa; flattened row-major (ny,nx)",...result}));
  });
  $("export-csv").addEventListener("click",()=>{
    if(!result)return;const rows=["x_m,y_m,pressure_rms_pa,radiation_pressure_pa"];
    for(let y=0;y<result.axes.y.length;y++)for(let x=0;x<result.axes.x.length;x++) {
      const i=y*result.axes.x.length+x;rows.push([result.axes.x[x],result.axes.y[y],result.field.rms[i],result.field.radiation[i]].join(","));
    }
    download("pmut-target-plane.csv",rows.join("\r\n"),"text/csv");
  });
  let resizePending=false;
  new ResizeObserver(()=>{if(!resizePending){resizePending=true;requestAnimationFrame(()=>{resizePending=false;render();});}}).observe($("workspace"));
  const narrow=window.matchMedia("(max-width:760px)");
  const updateWidth=()=>{$("parameters").open=!narrow.matches;};updateWidth();narrow.addEventListener("change",updateWidth);
  function ensureIdle(){if(busy)throw Error("请先等待当前计算完成或取消。");}
  function startJob(){
    ensureIdle();stopAnimation();const token=++generation;setBusy(true);$("progress").value=0;notice("正在运行实验任务，可随时取消。");
    return {
      compute:async(c,sample=null,diagnostic=false)=>{
        if(token!==generation)throw Error("已取消。");
        try{return await compute(c,token,sample,diagnostic);}finally{if(token===generation)cleanup();}
      },
      stop:()=>token!==generation,
      finish:()=>{if(token===generation){cleanup();setBusy(false);notice("实验任务结束，结果见对应页签。");}}
    };
  }
  function openRecord(snapshot){
    ensureIdle();stopAnimation();result=K.clone(snapshot);fill(result.config);
    for(const id of ["save-config","save-baseline","export-toml","export-metrics","export-csv"])$(id).disabled=false;
    $("export-data").disabled=true;$("play").disabled=true;$("frame").disabled=true;
    $("frame").value=0;$("frame").max=0;render();selectTab($("field-tab"));
  }
  lab=mountPmutLab({K,T,$,getResult:()=>result,read,fill,notice,download,serialize,heatmap,startJob,ensureIdle,openRecord});
  fill(K.clone(K.defaults));
  run();
})();
