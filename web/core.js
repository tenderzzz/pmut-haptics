/* Browser physics kernel. SI units; exp(+i omega t). No DOM or dependencies. */
function createPmutKernel() {
  "use strict";
  const defaults = {
    schema_version:2, title: "空中静态触点", carrier_hz: 109400, reflection_factor: 2, seed: 42,
    medium: {sound_speed_m_s:343, density_kg_m3:1.2, attenuation_np_m:0},
    element: {radius_m:.000415, velocity_peak_m_s:1},
    array: {nx:12, ny:12, pitch_wavelengths:.5, apodization:"uniform", phase_error_std_deg:0, pitch_mode:"wavelength", pitch_m:.0015676416819012796},
    imperfections:{amplitude_cv:0,position_std_m:0,failure_probability:0,phase_bits:0,rng:"portable-v1"},
    focus: {x_m:0, y_m:0, z_m:.05},
    grid: {x_min_m:-.02,x_max_m:.02,y_min_m:-.02,y_max_m:.02,z_min_m:.01,z_max_m:.08,nx:81,ny:81,nz:101},
    modulation: {kind:"burst",frequency_hz:100,duty_cycle:.5,depth:1,duration_s:.05,sample_rate_hz:20000},
    trajectory: {kind:"static",radius_m:.005,line_length_m:.015,duration_s:1,frames:41,loops:1},
    engine: {chunk_points:2048,max_transfer_mb:128}
  };
  const clone = value => JSON.parse(JSON.stringify(value));
  function merge(base, supplied, path) {
    if (!supplied || typeof supplied !== "object" || Array.isArray(supplied)) throw Error(path+" 必须是参数对象。");
    const out = clone(base);
    for (const key of Object.keys(supplied)) {
      if (!Object.hasOwn(base,key)) throw Error("未知参数："+path+key);
      const value = supplied[key], original = base[key];
      if (typeof original === "object") out[key]=merge(original,value,path+key+".");
      else {
        if (typeof value !== typeof original || (typeof value==="number" && !Number.isFinite(value)))
          throw Error(path+key+" 的类型或数值不正确。");
        out[key]=value;
      }
    }
    return out;
  }
  function validate(input,diagnostic=false) {
    const legacy=!Object.hasOwn(input,"schema_version");
    const c=merge(defaults,input,"");
    if(legacy){c.schema_version=1;if(!input.imperfections)c.imperfections.rng="legacy";}
    const a=c.array,g=c.grid,m=c.modulation,t=c.trajectory;
    const positive=[c.carrier_hz,c.medium.sound_speed_m_s,c.medium.density_kg_m3,
      c.element.radius_m,a.pitch_wavelengths,c.focus.z_m,m.frequency_hz,m.duration_s,
      m.sample_rate_hz,t.duration_s,c.engine.max_transfer_mb];
    if (positive.some(v=>v<=0)) throw Error("频率、尺寸、介质和时间参数必须为正数。");
    if(c.carrier_hz<20000||c.carrier_hz>600000) throw Error("HTML 版载波范围为 20–600 kHz。");
    if(c.element.velocity_peak_m_s<0||c.element.velocity_peak_m_s>10) throw Error("振速须为 0–10 m/s。");
    if(c.medium.attenuation_np_m<0) throw Error("衰减系数不能为负数。");
    const e=c.imperfections;
    if(![1,2].includes(c.schema_version))throw Error("不支持的配置版本。");
    if(!["wavelength","physical"].includes(a.pitch_mode)||a.pitch_m<=0)throw Error("物理间距须为正数。");
    if(a.phase_error_std_deg<0||e.amplitude_cv<0||e.amplitude_cv>2||e.position_std_m<0||
       e.failure_probability<0||e.failure_probability>1||!Number.isInteger(e.phase_bits)||e.phase_bits<0||e.phase_bits>16)
      throw Error("误差参数无效：幅度 CV 0–2、失效比例 0–1、相位位数 0–16。");
    if(!["legacy","portable-v1"].includes(e.rng))throw Error("未知的随机算法版本。");
    if(e.rng==="legacy"&&a.phase_error_std_deg!==0)throw Error("旧版随机相位请用 Python 复现；在误差设置中选择 portable-v1 可新建试验。");
    if(!Number.isSafeInteger(c.seed)||c.seed<0) throw Error("种子须为非负整数。");
    for(const value of [a.nx,a.ny,g.nx,g.ny,g.nz,t.frames,t.loops,c.engine.chunk_points])
      if(!Number.isSafeInteger(value)) throw Error("阵元数、网格数、帧数与周期数必须是整数。");
    if(a.nx<1||a.ny<1||a.nx>32||a.ny>32) throw Error("HTML 版每个方向支持 1–32 个阵元。");
    if(pitch(c)*c.carrier_hz/c.medium.sound_speed_m_s>1+1e-12) throw Error("HTML 版间距最多为 1 个波长。");
    if(pitch(c)<2*c.element.radius_m*(1-1e-12))
      throw Error("阵元直径大于间距。请减小半径、降低频率或增大间距。");
    if(!["uniform","hann"].includes(a.apodization)) throw Error("幅度分布仅支持 uniform / hann。");
    if(c.reflection_factor<1||c.reflection_factor>2) throw Error("反射系数须在 1–2 之间。");
    if(Math.min(g.nx,g.ny,g.nz)<3||Math.max(g.nx,g.ny,g.nz)>(diagnostic?601:151)) throw Error("HTML 版每轴网格须为 3–151 点。");
    if(!(g.x_min_m<g.x_max_m&&g.y_min_m<g.y_max_m&&g.z_min_m>0&&g.z_min_m<g.z_max_m))
      throw Error("坐标范围必须递增，且 z 必须为正数。");
    if(c.focus.x_m<g.x_min_m||c.focus.x_m>g.x_max_m||c.focus.y_m<g.y_min_m||c.focus.y_m>g.y_max_m||
       c.focus.z_m<g.z_min_m||c.focus.z_m>g.z_max_m) throw Error("焦点必须位于显示区域内。");
    if(!["cw","burst","sinusoidal"].includes(m.kind)||!["static","line","circle"].includes(t.kind))
      throw Error("不支持的调制方式或运动路径。");
    if(m.duty_cycle<=0||m.duty_cycle>1||m.depth<0||m.depth>1) throw Error("占空比须在 (0,1]，调制深度须在 [0,1]。");
    if(m.sample_rate_hz<20*m.frequency_hz||m.duration_s*m.sample_rate_hz>200000)
      throw Error("包络至少每周期 20 点，HTML 版波形最多 20 万点。");
    if(t.frames<3||t.frames>121||t.loops<1||t.radius_m<0||t.line_length_m<0)
      throw Error("轨迹需 3–121 帧、正整数周期数和非负尺寸。");
    if(t.kind!=="static") {
      if(t.frames<12*t.loops+1) throw Error("每个路径周期至少需要 12 个时间间隔。");
      const rx=t.kind==="circle"?t.radius_m:t.line_length_m/2, ry=t.kind==="circle"?t.radius_m:0;
      if(c.focus.x_m-rx<g.x_min_m||c.focus.x_m+rx>g.x_max_m||c.focus.y_m-ry<g.y_min_m||c.focus.y_m+ry>g.y_max_m)
        throw Error("整条轨迹须在目标平面内。请减小轨迹尺寸或移动中心。");
    }
    if(c.element.radius_m*c.carrier_hz/c.medium.sound_speed_m_s>.5)
      throw Error("HTML 快速核要求阵元半径不超过半波长。");
    const T=t.kind==="static"?1:t.frames;
    if(g.nx*g.ny*a.nx*a.ny*T>350000000) throw Error("计算规模过大，请减小阵列、网格或轨迹帧数。");
    if(c.engine.chunk_points<1||c.engine.chunk_points>65536) throw Error("分块参数须在 1–65536 之间。");
    return c;
  }
  function linspace(start,end,count) {
    return Float64Array.from({length:count},(_,i)=>start+(end-start)*i/(count-1));
  }
  // For validated a <= lambda/2, |ka sin(theta)| <= pi.
  // 2 J1(x)/x = sum_m (-x*x/4)^m / (m! (m+1)!).
  function jinc(x) {
    let term=1,sum=1;
    for(let m=1;m<=32;m++) {
      term*=(-x*x/4)/(m*(m+1)); sum+=term;
      if(Math.abs(term)<2e-17) break;
    }
    return sum;
  }
  const pitch=c=>c.array.pitch_mode==="physical"?c.array.pitch_m:c.array.pitch_wavelengths*c.medium.sound_speed_m_s/c.carrier_hz;
  function positions(c) {
    const spacing=pitch(c), out=[];
    for(let y=0;y<c.array.ny;y++) for(let x=0;x<c.array.nx;x++)
      out.push([(x-(c.array.nx-1)/2)*spacing,(y-(c.array.ny-1)/2)*spacing,0]);
    return out;
  }
  function random(seed) {
    let state=(seed>>>0)||0x6d2b79f5;
    const uniform=()=>{state^=state<<13;state^=state>>>17;state^=state<<5;state>>>=0;return (state+.5)/4294967296;};
    return {uniform,normal:()=>Math.sqrt(-2*Math.log(uniform()))*Math.cos(2*Math.PI*uniform())};
  }
  function sample(c) {
    const rng=random(c.seed),e=c.imperfections,n=c.array.nx*c.array.ny,sigma=Math.sqrt(Math.log1p(e.amplitude_cv**2));
    const out={version:e.rng,seed:c.seed,phase_rad:[],amplitude_gain:[],offsets_m:[],active:[]};
    if(e.rng==="legacy"&&c.array.phase_error_std_deg)throw Error("旧版随机相位需 Python 复现。");
    for(let i=0;i<n;i++){
      out.phase_rad.push(rng.normal()*c.array.phase_error_std_deg*Math.PI/180);
      out.amplitude_gain.push(Math.exp(sigma*rng.normal()-sigma*sigma/2));
      out.offsets_m.push([rng.normal()*e.position_std_m,rng.normal()*e.position_std_m,0]);
      out.active.push(Number(rng.uniform()>=e.failure_probability));
    }
    return out;
  }
  function actualPositions(nominal,s,c){
    const n=nominal.length;
    for(const k of ["phase_rad","amplitude_gain","active"])
      if(!Array.isArray(s[k])||s[k].length!==n||s[k].some(v=>!Number.isFinite(v)))throw Error("误差样本不完整。");
    if(!Array.isArray(s.offsets_m)||s.offsets_m.length!==n||s.offsets_m.some(v=>!Array.isArray(v)||v.length!==3||v.some(x=>!Number.isFinite(x))||v[2]!==0))
      throw Error("仅支持有限的平面位置误差。");
    if(s.amplitude_gain.some(v=>v<0)||s.active.some(v=>v!==0&&v!==1))throw Error("幅度或失效掩码无效。");
    const pos=nominal.map((p,i)=>p.map((v,j)=>v+s.offsets_m[i][j]));
    for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)
      if(Math.hypot(pos[i][0]-pos[j][0],pos[i][1]-pos[j][1])<2*c.element.radius_m*(1-1e-12))
        throw Error("无效样本：位置偏差造成阵元重叠。");
    return pos;
  }
  function weights(pos,target,c,errors=sample(c)) {
    const k=2*Math.PI*c.carrier_hz/c.medium.sound_speed_m_s, n=pos.length;
    const d=pos.map(p=>Math.hypot(p[0]-target[0],p[1]-target[1],target[2]));
    const min=Math.min(...d), amps=new Float64Array(n);
    const hann=(i,n)=>n<3?1:.5*(1-Math.cos(2*Math.PI*i/(n-1)));
    let norm=0;
    for(let i=0;i<n;i++) {
      amps[i]=c.array.apodization==="hann"?hann(i%c.array.nx,c.array.nx)*hann(Math.floor(i/c.array.nx),c.array.ny):1;
      norm+=amps[i]*amps[i];
    }
    const factor=c.element.velocity_peak_m_s*Math.sqrt(n/norm);
    const re=new Float64Array(n),im=new Float64Array(n);
    for(let i=0;i<n;i++) {
      let phase=k*(d[i]-min);
      if(c.imperfections.phase_bits){const step=2*Math.PI/2**c.imperfections.phase_bits;phase=Math.floor(phase/step+.5)*step;}
      phase+=errors.phase_rad[i];
      const amplitude=amps[i]*factor*errors.amplitude_gain[i]*errors.active[i];
      re[i]=amplitude*Math.cos(phase); im[i]=amplitude*Math.sin(phase);
    }
    return {re,im};
  }
  function transfer(x,y,z,pos,c,re,im) {
    const rho=c.medium.density_kg_m3,speed=c.medium.sound_speed_m_s;
    const k=2*Math.PI*c.carrier_hz/speed,a=c.element.radius_m,coef=rho*speed*k*a*a/2;
    for(let n=0;n<pos.length;n++) {
      const dx=x-pos[n][0],dy=y-pos[n][1],r=Math.hypot(dx,dy,z);
      const mag=coef*jinc(k*a*Math.hypot(dx,dy)/r)*Math.exp(-c.medium.attenuation_np_m*r)/r;
      re[n]=mag*Math.sin(k*r); im[n]=mag*Math.cos(k*r);
    }
  }
  function dot(re,im,w) {
    let pr=0,pi=0;
    for(let i=0;i<re.length;i++) {pr+=re[i]*w.re[i]-im[i]*w.im[i]; pi+=re[i]*w.im[i]+im[i]*w.re[i];}
    return [pr,pi];
  }
  function width(axis,values,fraction=Math.pow(10,-6/20)) {
    let peak=0;
    for(let i=1;i<values.length;i++) if(values[i]>values[peak]) peak=i;
    const empty={width_m:null,clipped:false,reason:"zero_signal",left_m:null,right_m:null,peak_index:peak};
    if(values[peak]<=0) return empty;
    const threshold=values[peak]*fraction;
    let l=peak,r=peak;
    while(l>0&&values[l-1]>=threshold) l--;
    while(r<values.length-1&&values[r+1]>=threshold) r++;
    const cross=(i,j)=>axis[i]+(threshold-values[i])*(axis[j]-axis[i])/(values[j]-values[i]);
    const left=l===0?null:cross(l-1,l),right=r===values.length-1?null:cross(r,r+1);
    const clipped=left===null||right===null;
    return {width_m:clipped?null:right-left,clipped,reason:clipped?"boundary":"ok",left_m:left,right_m:right,peak_index:peak};
  }
  function extrema(values,sign) {
    const indices=[];
    for(let i=1;i<values.length-1;i++) {
      if(sign*values[i]<=sign*values[i-1]) continue;
      let end=i;
      while(end+1<values.length&&values[end+1]===values[i]) end++;
      if(end+1<values.length&&sign*values[end+1]<sign*values[i]) indices.push(Math.floor((i+end)/2));
      i=end;
    }
    return indices;
  }
  function sidelobe(values) {
    let peak=0;
    for(let i=1;i<values.length;i++) if(values[i]>values[peak]) peak=i;
    if(values[peak]<=0) return null;
    const mins=extrema(values,-1),left=mins.filter(i=>i<peak),right=mins.filter(i=>i>peak);
    if(!left.length||!right.length) return null;
    const outside=extrema(values,1).filter(i=>i<left[left.length-1]||i>right[0]);
    return outside.length?20*Math.log10(Math.max(...outside.map(i=>values[i]))/values[peak]):null;
  }
  function planeForce(values,x,y) {
    let sum=0;
    for(let iy=0;iy<y.length;iy++) {
      const wy=iy===0?(y[1]-y[0])/2:iy===y.length-1?(y[iy]-y[iy-1])/2:(y[iy+1]-y[iy-1])/2;
      for(let ix=0;ix<x.length;ix++) {
        const wx=ix===0?(x[1]-x[0])/2:ix===x.length-1?(x[ix]-x[ix-1])/2:(x[ix+1]-x[ix-1])/2;
        sum+=values[iy*x.length+ix]*wx*wy;
      }
    }
    return sum;
  }
  function envelope(t,m) {
    if(m.kind==="cw") return 1;
    let phase=((t*m.frequency_hz)%1+1)%1;
    if(m.kind==="burst") {
      if(Math.abs(phase-1)<1e-12) phase=0;
      if(Math.abs(phase-m.duty_cycle)<1e-12) phase=m.duty_cycle;
      return 1-m.depth+m.depth*(phase<m.duty_cycle?1:0);
    }
    return 1-m.depth+m.depth*(1+Math.sin(2*Math.PI*phase))/2;
  }
  function path(c) {
    const t=c.trajectory,center=[c.focus.x_m,c.focus.y_m,c.focus.z_m];
    if(t.kind==="static") return {times:Float64Array.of(0),points:[center]};
    const times=linspace(0,t.duration_s,t.frames);
    const points=Array.from(times,time=>{
      const phase=2*Math.PI*t.loops*time/t.duration_s,p=center.slice();
      if(t.kind==="circle") {p[0]+=t.radius_m*Math.cos(phase);p[1]+=t.radius_m*Math.sin(phase);}
      else p[0]+=t.line_length_m/2*Math.sin(phase);
      return p;
    });
    return {times,points};
  }
  const pause=()=>new Promise(resolve=>setTimeout(resolve,0));
  async function simulate(input,onProgress=()=>{},shouldStop=()=>false,suppliedSample=null,diagnostic=false) {
    const c=validate(input,diagnostic),start=typeof performance!=="undefined"?performance.now():Date.now();
    const errors=suppliedSample||sample(c),nominal=positions(c),pos=actualPositions(nominal,errors,c);
    const g=c.grid,center=[c.focus.x_m,c.focus.y_m,c.focus.z_m];
    const base=weights(nominal,center,c,errors),motion=path(c), allWeights=motion.points.map(p=>weights(nominal,p,c,errors));
    const x=linspace(g.x_min_m,g.x_max_m,g.nx),y=linspace(g.y_min_m,g.y_max_m,g.ny),z=linspace(g.z_min_m,g.z_max_m,g.nz);
    const size=g.nx*g.ny,re=new Float64Array(size),im=new Float64Array(size);
    const rms=new Float64Array(size),radiation=new Float64Array(size);
    const frames=motion.points.map(()=>new Float64Array(size));
    const hr=new Float64Array(pos.length),hi=new Float64Array(pos.length);
    const radiationFactor=c.reflection_factor/(2*c.medium.density_kg_m3*c.medium.sound_speed_m_s**2);
    const total=g.ny+g.nz;
    for(let iy=0;iy<g.ny;iy++) {
      for(let ix=0;ix<g.nx;ix++) {
        const at=iy*g.nx+ix;
        transfer(x[ix],y[iy],c.focus.z_m,pos,c,hr,hi);
        const p=dot(hr,hi,base);
        re[at]=p[0];im[at]=p[1];rms[at]=Math.hypot(...p)/Math.SQRT2;
        radiation[at]=(p[0]*p[0]+p[1]*p[1])*radiationFactor;
        for(let f=0;f<frames.length;f++) {
          const pf=frames.length===1?p:dot(hr,hi,allWeights[f]);
          frames[f][at]=(pf[0]*pf[0]+pf[1]*pf[1])*radiationFactor;
        }
      }
      if(iy%4===0) {onProgress((iy+1)/total);await pause();if(shouldStop()) throw Error("计算已取消。");}
    }
    const xzRms=new Float64Array(g.nx*g.nz);
    for(let iz=0;iz<g.nz;iz++) {
      for(let ix=0;ix<g.nx;ix++) {
        transfer(x[ix],c.focus.y_m,z[iz],pos,c,hr,hi);
        xzRms[iz*g.nx+ix]=Math.hypot(...dot(hr,hi,base))/Math.SQRT2;
      }
      if(iz%8===0) {onProgress((g.ny+iz+1)/total);await pause();if(shouldStop()) throw Error("计算已取消。");}
    }
    let peakIndex=0;
    for(let i=1;i<size;i++) if(rms[i]>rms[peakIndex]) peakIndex=i;
    const iy=Math.floor(peakIndex/g.nx),ix=peakIndex%g.nx,peak=rms[peakIndex];
    const px=Array.from({length:g.nx},(_,i)=>rms[iy*g.nx+i]);
    const py=Array.from({length:g.ny},(_,i)=>rms[i*g.nx+ix]);
    const rx=px.map(v=>v*v*2*radiationFactor),ry=py.map(v=>v*v*2*radiationFactor);
    const forces=frames.map(f=>planeForce(f,x,y));
    const focusRadiation=motion.points.map((p,i)=>{
      transfer(...p,pos,c,hr,hi);
      const field=dot(hr,hi,allWeights[i]);
      return (field[0]**2+field[1]**2)*radiationFactor;
    });
    const mean=new Float64Array(size);
    for(let i=0;i<size;i++) {
      if(frames.length===1) mean[i]=frames[0][i];
      else for(let f=1;f<frames.length;f++) mean[i]+=(frames[f-1][i]+frames[f][i])*.5/(frames.length-1);
    }
    const count=Math.ceil(c.modulation.duration_s*c.modulation.sample_rate_hz);
    const wave={time:new Float64Array(count),envelope:new Float64Array(count),force:new Float64Array(count),focusRadiation:new Float64Array(count)};
    let sumSquare=0,sumForce=0,peakFocus=0;
    for(let i=0;i<count;i++) {
      const time=i/c.modulation.sample_rate_hz,env=envelope(time,c.modulation);
      let force=forces[0],focus=focusRadiation[0];
      if(frames.length>1) {
        const at=(time%c.trajectory.duration_s)/c.trajectory.duration_s*(frames.length-1);
        const low=Math.floor(at),high=Math.min(low+1,frames.length-1),ratio=at-low;
        force=forces[low]*(1-ratio)+forces[high]*ratio;
        focus=focusRadiation[low]*(1-ratio)+focusRadiation[high]*ratio;
      }
      wave.time[i]=time;wave.envelope[i]=env;wave.force[i]=force*env*env;wave.focusRadiation[i]=focus*env*env;
      sumSquare+=env*env;sumForce+=wave.force[i];peakFocus=Math.max(peakFocus,wave.focusRadiation[i]);
    }
    const metrics={
      model_version:"2.0",sample_rng:errors.version,sample_seed:errors.seed,
      target_pressure_rms_pa:(()=>{transfer(...center,pos,c,hr,hi);return Math.hypot(...dot(hr,hi,base))/Math.SQRT2;})(),
      pressure_peak_pa:peak*Math.SQRT2,pressure_rms_max_pa:peak,
      spl_db_re_20uPa:peak>0?20*Math.log10(peak/20e-6):null,
      intensity_max_w_m2:peak*peak/(c.medium.density_kg_m3*c.medium.sound_speed_m_s),
      radiation_pressure_max_pa:radiation[peakIndex],force_over_displayed_plane_n:planeForce(radiation,x,y),
      peak_x_m:peak>0?x[ix]:null,peak_y_m:peak>0?y[iy]:null,
      target_lateral_error_m:peak>0?Math.hypot(x[ix]-c.focus.x_m,y[iy]-c.focus.y_m):null,
      pressure_x_minus6db:width(x,px),pressure_y_minus6db:width(y,py),
      radiation_x_fwhm:width(x,rx,.5),radiation_y_fwhm:width(y,ry,.5),
      sidelobe_x_db:sidelobe(px),sidelobe_y_db:sidelobe(py),
      plane_area_m2:(x[x.length-1]-x[0])*(y[y.length-1]-y[0]),
      element_count:pos.length,pitch_m:pitch(c),
      wavelength_m:c.medium.sound_speed_m_s/c.carrier_hz,
      sum_squared_velocity_m2_s2:Array.from(base.re,(v,i)=>v*v+base.im[i]*base.im[i]).reduce((a,b)=>a+b,0),
      envelope_mean_square:sumSquare/count,plane_force_time_mean_n:sumForce/count,
      commanded_focus_radiation_time_peak_pa:peakFocus,
      simulation_seconds:((typeof performance!=="undefined"?performance.now():Date.now())-start)/1000,
      amplitude_basis:"assumed peak surface velocity; not voltage calibrated",
      motion_map_basis:"carrier averaged, unmodulated; separate waveform applies envelope squared",
      runtime:"standalone HTML; JavaScript Float64"
    };
    onProgress(1);
    return {config:c,sample:errors,nominalPositions:nominal,metrics,axes:{x,y,z},positions:pos,field:{re,im,rms,radiation,xzRms,profileX:px,profileY:py},
      trajectory:{...motion,frames,forces,mean,focusRadiation},wave};
  }
  function toml(c) {
    const lines=[];
    for(const [key,value] of Object.entries(c)) if(typeof value!=="object") lines.push(key+" = "+JSON.stringify(value));
    for(const [key,value] of Object.entries(c)) if(typeof value==="object") {
      lines.push("","["+key+"]");
      for(const [name,item] of Object.entries(value)) lines.push(name+" = "+JSON.stringify(item));
    }
    return lines.join("\n")+"\n";
  }
  function parseToml(text) {
    const data={},tables=new Set();let current=data;
    for(const original of text.split(/\r?\n/)) {
      let quoted=false,escaped=false,line="";
      for(const char of original) {
        if(char==="#"&&!quoted) break;
        line+=char;
        if(char==='"'&&!escaped) quoted=!quoted;
        escaped=char==="\\"&&!escaped;
        if(char!=="\\") escaped=false;
      }
      line=line.trim();if(!line) continue;
      if(/^\[[A-Za-z_]+\]$/.test(line)) {
        const name=line.slice(1,-1);
        if(!Object.hasOwn(defaults,name)||typeof defaults[name]!=="object"||tables.has(name)) throw Error("无效或重复的配置段："+name);
        tables.add(name);current={};data[name]=current;continue;
      }
      const match=line.match(/^([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.+)$/);
      if(!match||Object.hasOwn(current,match[1])) throw Error("无法读取此 TOML 行："+line);
      const raw=match[2];let value;
      if(raw.startsWith('"')) {try {value=JSON.parse(raw);}catch{throw Error("配置字符串格式错误。");}}
      else if(/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw)) value=Number(raw);
      else throw Error("HTML 导入支持本项目导出的数值和字符串 TOML。");
      Object.defineProperty(current,match[1],{value,enumerable:true,configurable:true,writable:true});
    }
    return validate(data);
  }
  return {defaults,clone,validate,pitch,random,sample,actualPositions,jinc,positions,weights,width,sidelobe,planeForce,envelope,path,simulate,toml,parseToml};
}
if(typeof module!=="undefined"&&module.exports) module.exports={createPmutKernel};
