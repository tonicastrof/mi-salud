import { useState, useMemo, useCallback, useEffect } from "react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, XAxis, YAxis,
  Tooltip, ResponsiveContainer, Cell, ReferenceLine
} from "recharts";

/* ═══════════════════════════════════════════
   CONFIG — cambia esta URL por tu deploy
   ═══════════════════════════════════════════ */
const API_URL = ""; // ← pon aquí tu URL de Vercel, ej: "https://mi-salud.vercel.app"
// Si está vacío, usa datos demo. Cuando despliegues, pon tu URL real.

/* ═══════════════════════════════════════════
   THEME SYSTEM
   ═══════════════════════════════════════════ */
const themes = {
  light: {
    bg:"#f0f1f5",card:"#ffffff",cardBorder:"rgba(0,0,0,0.06)",text:"#111827",sub:"#6b7280",muted:"#9ca3af",
    headerBg:"linear-gradient(135deg,#111827,#1e293b)",headerText:"#ffffff",headerSub:"rgba(255,255,255,0.45)",
    tabBg:"rgba(255,255,255,0.08)",tabActive:"rgba(255,255,255,0.16)",tabText:"rgba(255,255,255,0.35)",tabActiveText:"#ffffff",
    quickBg:"#ffffff",phaseBg:"#f3f4f6",barInactive:"#c7dbf5",filterBg:"#e5e7eb",filterActiveBg:"#111827",
    syncBtnBg:"rgba(255,255,255,0.12)",mapBg:"#0f172a",
    badgeGreen:{bg:"#dcfce7",fg:"#166534"},badgeYellow:{bg:"#fef3c7",fg:"#92400e"},badgeRed:{bg:"#fee2e2",fg:"#dc2626"},
    tooltip:{bg:"#fff",shadow:"0 4px 20px rgba(0,0,0,0.1)"},
  },
  dark: {
    bg:"#0a0a0f",card:"#16161e",cardBorder:"rgba(255,255,255,0.06)",text:"#f1f5f9",sub:"#94a3b8",muted:"#64748b",
    headerBg:"linear-gradient(135deg,#0f0f17,#141422)",headerText:"#f1f5f9",headerSub:"rgba(241,245,249,0.35)",
    tabBg:"rgba(255,255,255,0.04)",tabActive:"rgba(255,255,255,0.1)",tabText:"rgba(255,255,255,0.3)",tabActiveText:"#f1f5f9",
    quickBg:"#16161e",phaseBg:"#1e1e2a",barInactive:"#1e3a5f",filterBg:"#1e1e2a",filterActiveBg:"#f1f5f9",
    syncBtnBg:"rgba(255,255,255,0.06)",mapBg:"#0c0c14",
    badgeGreen:{bg:"rgba(16,185,129,0.15)",fg:"#6ee7b7"},badgeYellow:{bg:"rgba(245,158,11,0.15)",fg:"#fcd34d"},badgeRed:{bg:"rgba(239,68,68,0.15)",fg:"#fca5a5"},
    tooltip:{bg:"#1e1e2a",shadow:"0 4px 20px rgba(0,0,0,0.4)"},
  },
};
const A = {run:"#e85d4a",ride:"#2d9cdb",hike:"#27ae60",sleep:"#7c5cfc",hr:"#ef4444",battery:"#10b981",stress:"#f59e0b",vo2:"#06b6d4",steps:"#3b82f6",fitness:"#8b5cf6",fatigue:"#f97316",form:"#10b981"};
const sportColor = {Run:A.run,Ride:A.ride,Hike:A.hike};

/* ═══════════════════════════════════════════
   DATOS DEMO (se usan si no hay API conectada)
   ═══════════════════════════════════════════ */
const DEMO = {
  profile: { name: "Toni Castro", weight: 60, ftp: 250 },
  daily: { steps:9847, calories_total:2180, resting_hr:52, active_minutes:47, avg_spo2:97, avg_respiration:14, body_battery_high:67 },
  sleep: { score:82, total_formatted:"6h 27m", deep_min:72, light_min:198, rem_min:95, awake_min:22, start_time:"23:12", end_time:"6:39" },
  hrv: { last_night_avg:68, weekly_avg:65 },
  steps_week: [{day:"Lun",steps:8420},{day:"Mar",steps:12350},{day:"Mié",steps:6780},{day:"Jue",steps:9100},{day:"Vie",steps:11200},{day:"Sáb",steps:14500},{day:"Dom",steps:5400}],
  hrv_week: [{d:"Lun",hrv:62,rhr:53},{d:"Mar",hrv:58,rhr:54},{d:"Mié",hrv:71,rhr:51},{d:"Jue",hrv:65,rhr:52},{d:"Vie",hrv:55,rhr:55},{d:"Sáb",hrv:74,rhr:50},{d:"Dom",hrv:68,rhr:52}],
  heart_rate: { hourly: Array.from({length:24},(_,i)=>({hour:`${i}:00`,hr:Math.round(i<6?52+Math.random()*8:i<9?65+Math.random()*15:i<18?70+Math.random()*25:60+Math.random()*10)})) },
  body_battery: Array.from({length:24},(_,i)=>({time:`${i}:00`,battery:Math.round(i<6?85+Math.random()*10:Math.max(15,90-i*3.5+Math.random()*10))})),
  activities: [
    {id:"1",name:"Night Run",sport:"Run",date:"17 Ago",distance:10.2,time:"48:01",elevation:152,calories:563,effort:80,pace:"4:42",icon:"🏃",avg_hr:152,polyline:"cvndGlajs@@a@DS^kAJuAEOMM]Gs@EeC[k@SSOSIaBGq@]kA{@gCw@YE}@_@iD?_@Ik@UaAu@QGaA@_AMg@HSE{@e@g@M[]o@[k@k@WMeAOo@B}B}@s@_@e@_@",
      laps:[{km:1,pace:"4:37",hr:125,elev:3},{km:2,pace:"4:33",hr:142,elev:6},{km:3,pace:"4:24",hr:139,elev:3},{km:4,pace:"4:43",hr:155,elev:33},{km:5,pace:"4:38",hr:145,elev:13},{km:6,pace:"4:58",hr:156,elev:29},{km:7,pace:"4:38",hr:158,elev:12},{km:8,pace:"5:00",hr:165,elev:38},{km:9,pace:"4:49",hr:164,elev:15},{km:10,pace:"4:39",hr:162,elev:12}],
      bestEfforts:[{name:"400m",time:"1:43"},{name:"1K",time:"4:25"},{name:"1 milla",time:"7:09"},{name:"5K",time:"22:57"},{name:"10K",time:"47:00"}]},
    {id:"2",name:"Alto de Peñacorada",sport:"Hike",date:"12 Ago",distance:15.3,time:"4:20:35",elevation:1097,calories:1482,effort:71,icon:"⛰️",polyline:"elgdGhyf^UbAD\\If@c@RqFcCt@m@t@iDVgECs@z@wJUiAFeDNgAAwFOaA^g@Xr@j@n@vBdAE@?QLHUIQgAc@eASqBAsFZ"},
    {id:"3",name:"Pico Gilbo",sport:"Hike",date:"11 Ago",distance:10.0,time:"2:38:58",elevation:622,calories:854,effort:35,icon:"⛰️",polyline:"anheGpbr]e@ElF`F`@h@dA~@Xb@`BlAd@z@tA|@DTT\\v@\\Rd@XFrAlA`@h@x@Nr@h@n@v@j@b@Zj@r@j@Zb@"},
    {id:"4",name:"Valporquero–Vegacervera",sport:"Hike",date:"10 Ago",distance:18.6,time:"4:24:34",elevation:810,calories:1059,effort:47,icon:"⛰️",polyline:"ur{dGtu|`@m@rGuAtBVtAeAtCK~CLpAAvFVrCb@jAxAQBRo@rBStDa@`@wBYQR_@`CCdLWzBgAfCGhAL~Ia@lFd@lCH~Bu@tE"},
    {id:"5",name:"Foz Picarós–Las Xanas",sport:"Hike",date:"9 Ago",distance:17.4,time:"4:10:48",elevation:856,calories:839,effort:39,icon:"⛰️",polyline:"e{`gGlusc@^kDyB_ByFaBdBVbDhA~IhArMxEtN|EbDRa@Kl@_@~@aB\\}AhBkAz@iC{@Yo@aAGuANo@BiBQJQt@sAl@b@"},
    {id:"6",name:"Evening Ride",sport:"Ride",date:"6 Ago",distance:50.2,time:"2:00:01",elevation:905,calories:1323,effort:168,avg_speed:"25.1 km/h",icon:"🚴",polyline:"cundGnljs@nBxCgFnJSfGeDtKsAnC[vCwCpDuCrAcF`IiA~[B~Ar@|CnFrEnFpL`Fl]m@pGmCtHcBjByKxG"},
    {id:"7",name:"Night Run",sport:"Run",date:"3 Ago",distance:6.4,time:"30:26",elevation:78,calories:343,effort:37,pace:"4:45",icon:"🏃",polyline:"kxndGxejs@HGr@uAJe@Fq@b@yA?a@Dq@EKQOIE_AE{AWk@Gq@SWSKGi@Cc@?a@IyByAi@Se@Ic@Q]IqAe@a@CYBq@@"},
    {id:"8",name:"Bicicleta mañana",sport:"Ride",date:"1 Ago",distance:78.8,time:"3:16:23",elevation:1400,calories:1847,effort:159,avg_speed:"24.1 km/h",icon:"🚴",polyline:"aaddGlkgu@}B][uBmJqAQeCyo@_MmOkKcHyBiRxE{JvGuAWeCgDsIwCmGO}S|EeRdKeYh]i^tQs@jBQlGmHxH"},
    {id:"9",name:"Volvendo aos poucos 🦵🐢",sport:"Run",date:"30 Jul",distance:5.0,time:"23:36",elevation:50,calories:282,effort:43,pace:"4:43",icon:"🏃",polyline:"{wndGdgjs@CCNk@HWJk@Vy@@m@h@cB?YFo@CQQSUGoCQu@Ka@MMGUSWI}@?a@KeC{A{E}AyBFgAKm@Wk@e@UQSGo@"},
    {id:"10",name:"Evening Ride",sport:"Ride",date:"29 Jul",distance:50.1,time:"1:57:22",elevation:899,calories:1320,effort:170,avg_speed:"25.6 km/h",icon:"🚴",polyline:"awndG`kjs@hBlCv@ZBb@uE~J[~FqFjOo@tDmCdDgCfAcFbIwA`]J~Ax@nCfFhEdFpL~Ez\\k@tGkCxHqBrB"},
  ],
  readiness: { score:73, breakdown:{sleep:{value:82},hrv:{value:68},body_battery:{value:67},load:{value:80}} },
  fitness: { current:{ctl:35,atl:22,tsb:13}, timeline:[] },
  acwr: { ratio:0.95 },
  race_predictions: [{distance:"5K",time:"18:25",pace:"3:41/km"},{distance:"10K",time:"38:20",pace:"3:50/km"},{distance:"Media Maratón",time:"1:24:30",pace:"4:00/km"},{distance:"Maratón",time:"2:57:00",pace:"4:12/km"}],
  vo2max_estimated: 48,
};

/* ═══════════════════════════════════════════
   POLYLINE DECODER
   ═══════════════════════════════════════════ */
function decodePolyline(str){const pts=[];let i=0,lat=0,lng=0;while(i<str.length){let b,s=0,r=0;do{b=str.charCodeAt(i++)-63;r|=(b&0x1f)<<s;s+=5}while(b>=0x20);lat+=(r&1)?~(r>>1):(r>>1);s=0;r=0;do{b=str.charCodeAt(i++)-63;r|=(b&0x1f)<<s;s+=5}while(b>=0x20);lng+=(r&1)?~(r>>1):(r>>1);pts.push([lat/1e5,lng/1e5])}return pts}
function RouteMap({polyline,color,height=180,theme:t}){
  const svg=useMemo(()=>{if(!polyline)return null;const pts=decodePolyline(polyline);if(pts.length<2)return null;const lats=pts.map(p=>p[0]),lngs=pts.map(p=>p[1]);const mnLa=Math.min(...lats),mxLa=Math.max(...lats),mnLn=Math.min(...lngs),mxLn=Math.max(...lngs);const w=mxLn-mnLn||.001,h2=mxLa-mnLa||.001;const sc=Math.min(260/w,(height-30)/h2);const mp=pts.map(p=>[(p[1]-mnLn)*sc+20,(mxLa-p[0])*sc+15]);const d=mp.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');return{d,vw:w*sc+40,vh:h2*sc+30,s:mp[0],e:mp[mp.length-1]}},[polyline,height]);
  if(!svg)return null;
  return(<div style={{background:t.mapBg,borderRadius:12,padding:10,display:"flex",justifyContent:"center"}}><svg viewBox={`0 0 ${svg.vw} ${svg.vh}`} width="100%" height={height} style={{maxWidth:400}}><path d={svg.d} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" opacity={0.3}/><path d={svg.d} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round"/><circle cx={svg.s[0]} cy={svg.s[1]} r={5} fill="#22c55e"/><circle cx={svg.e[0]} cy={svg.e[1]} r={5} fill="#ef4444"/></svg></div>);
}

/* ═══════════════════════════════════════════
   UI COMPONENTS
   ═══════════════════════════════════════════ */
function Ring({value,max,size=88,stroke=7,color,children}){const r=(size-stroke)/2,c=2*Math.PI*r,o=c-(value/max)*c;return(<div style={{position:"relative",width:size,height:size}}><svg width={size} height={size} style={{transform:"rotate(-90deg)"}}><circle cx={size/2} cy={size/2} r={r} fill="none" stroke="currentColor" opacity={0.08} strokeWidth={stroke}/><circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeDasharray={c} strokeDashoffset={o} strokeLinecap="round" style={{transition:"stroke-dashoffset 0.8s"}}/></svg><div style={{position:"absolute",inset:0,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center"}}>{children}</div></div>)}
function Card({title,accent,children,t,style:s={}}){return(<div style={{background:t.card,borderRadius:14,padding:"16px 18px",border:`1px solid ${t.cardBorder}`,position:"relative",overflow:"hidden",display:"flex",flexDirection:"column",gap:12,transition:"background 0.3s, border 0.3s",...s}}>{accent&&<div style={{position:"absolute",top:0,left:0,right:0,height:3,background:accent}}/>}<span style={{fontSize:11,fontWeight:700,color:t.sub,textTransform:"uppercase",letterSpacing:"0.06em"}}>{title}</span>{children}</div>)}
function Stat({label,value,t}){return<div><div style={{fontSize:13,fontWeight:700,color:t.text}}>{value}</div><div style={{fontSize:10,color:t.sub}}>{label}</div></div>}
function ThemeIcon({dark}){return dark?<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>}
function SyncIcon({spinning}){return<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{animation:spinning?"spin 1s linear infinite":"none"}}><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/><style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style></svg>}

/* ═══════════════════════════════════════════
   ACTIVITY DETAIL MODAL
   ═══════════════════════════════════════════ */
function ActivityDetail({activity:a,onClose,t}){
  const color=sportColor[a.sport]||A.steps;
  return(<div style={{position:"fixed",inset:0,zIndex:100,background:"rgba(0,0,0,0.5)",display:"flex",justifyContent:"center",alignItems:"flex-end",backdropFilter:"blur(4px)"}} onClick={onClose}>
    <div style={{width:"100%",maxWidth:560,maxHeight:"92vh",background:t.bg,borderRadius:"20px 20px 0 0",overflow:"auto",WebkitOverflowScrolling:"touch"}} onClick={e=>e.stopPropagation()}>
      <div style={{background:color,padding:"16px 20px",borderRadius:"20px 20px 0 0",color:"#fff",position:"sticky",top:0,zIndex:2}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"start"}}>
          <div><div style={{fontSize:18,fontWeight:700}}>{a.icon} {a.name}</div><div style={{fontSize:12,opacity:0.8,marginTop:2}}>{a.date||a.date_formatted} · {a.sport}</div></div>
          <button onClick={onClose} style={{background:"rgba(255,255,255,0.2)",border:"none",borderRadius:"50%",width:32,height:32,color:"#fff",fontSize:18,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center"}}>✕</button>
        </div>
        <div style={{display:"flex",gap:16,marginTop:14,flexWrap:"wrap"}}>
          {[{l:"Distancia",v:`${a.distance} km`},{l:"Tiempo",v:a.time},{l:"Desnivel",v:`↑${a.elevation}m`},a.pace?{l:"Ritmo",v:`${a.pace}/km`}:a.avg_speed?{l:"Vel.",v:a.avg_speed}:null,{l:"Cal",v:`${a.calories}`}].filter(Boolean).map((s,i)=>(<div key={i}><div style={{fontSize:18,fontWeight:700}}>{s.v}</div><div style={{fontSize:10,opacity:0.7}}>{s.l}</div></div>))}
        </div>
      </div>
      <div style={{padding:"16px 16px 32px"}}>
        {a.polyline&&<div style={{marginBottom:16}}><RouteMap polyline={a.polyline} color={color} height={200} theme={t}/></div>}
        {a.laps&&a.laps.length>0&&<Card title="Splits por km" accent={color} t={t} style={{marginBottom:14}}>
          {a.laps.map((l,i)=>{const ps=a.laps.map(x=>parseInt(x.pace)*60+parseInt(x.pace.split(":")[1]));const mn=Math.min(...ps),mx=Math.max(...ps),cv=parseInt(l.pace)*60+parseInt(l.pace.split(":")[1]);const pct=mx===mn?100:100-((cv-mn)/(mx-mn))*100;
            return(<div key={i} style={{display:"flex",alignItems:"center",gap:4,padding:"5px 0",borderBottom:i<a.laps.length-1?`1px solid ${t.cardBorder}`:"none"}}>
              <span style={{width:24,fontSize:11,fontWeight:700,color:t.text}}>{l.km}</span>
              <div style={{flex:1,display:"flex",alignItems:"center",gap:6}}><div style={{width:50,height:7,background:t.phaseBg,borderRadius:4,overflow:"hidden"}}><div style={{width:`${pct}%`,height:"100%",background:color,borderRadius:4}}/></div>
              <span style={{fontSize:12,fontWeight:600,color:t.text}}>{l.pace}/km</span></div>
              <span style={{width:40,fontSize:11,color:l.hr>160?A.hr:t.sub,fontWeight:l.hr>160?700:400,textAlign:"right"}}>♥{l.hr}</span>
              <span style={{width:40,fontSize:10,color:t.sub,textAlign:"right"}}>↑{l.elev}m</span>
            </div>)})}
        </Card>}
        {a.bestEfforts&&a.bestEfforts.length>0&&<Card title="Mejores esfuerzos" accent={color} t={t}>
          {a.bestEfforts.map((b,i)=>(<div key={i} style={{display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:i<a.bestEfforts.length-1?`1px solid ${t.cardBorder}`:"none"}}><span style={{fontSize:12,fontWeight:600,color:t.text}}>{b.name}</span><span style={{fontSize:13,fontWeight:700,color}}>{b.time}</span></div>))}
        </Card>}
      </div>
    </div>
  </div>);
}

/* ═══════════════════════════════════════════
   SYNC OVERLAY
   ═══════════════════════════════════════════ */
function SyncOverlay({steps,t}){
  return(<div style={{position:"fixed",inset:0,zIndex:200,background:"rgba(0,0,0,0.6)",display:"flex",alignItems:"center",justifyContent:"center",backdropFilter:"blur(6px)"}}>
    <div style={{background:t.card,borderRadius:20,padding:"32px 40px",textAlign:"center",maxWidth:320,width:"90%",border:`1px solid ${t.cardBorder}`}}>
      <div style={{fontSize:40,marginBottom:12}}>
        <SyncIcon spinning={true}/>
      </div>
      <div style={{fontSize:16,fontWeight:700,color:t.text,marginBottom:16}}>Sincronizando</div>
      {steps.map((s,i)=>(
        <div key={i} style={{display:"flex",alignItems:"center",gap:10,marginBottom:8,opacity:s.status==="pending"?0.3:1,transition:"opacity 0.3s"}}>
          <span style={{fontSize:16}}>{s.status==="done"?"✅":s.status==="loading"?"⏳":s.status==="error"?"❌":"⬜"}</span>
          <span style={{fontSize:13,color:t.text,fontWeight:s.status==="loading"?700:400}}>{s.label}</span>
        </div>
      ))}
    </div>
  </div>);
}

/* ═══════════════════════════════════════════
   MAIN DASHBOARD
   ═══════════════════════════════════════════ */
export default function Dashboard(){
  const [dark,setDark]=useState(true);
  const [tab,setTab]=useState("resumen");
  const [sel,setSel]=useState(null);
  const [filter,setFilter]=useState("Todas");

  // Data state
  const [data,setData]=useState(DEMO);
  const [lastSync,setLastSync]=useState(null);
  const [loading,setLoading]=useState(false);
  const [syncSteps,setSyncSteps]=useState([]);
  const [showSyncOverlay,setShowSyncOverlay]=useState(false);

  const t=dark?themes.dark:themes.light;
  const tt={borderRadius:8,border:"none",boxShadow:t.tooltip.shadow,fontSize:11,padding:"6px 10px",backgroundColor:t.tooltip.bg,color:t.text};

  // Helper values from data
  const d = data.daily || {};
  const sleep = data.sleep || {};
  const hrv = data.hrv || {};
  const acts = data.activities || [];
  const readiness = data.readiness?.score || 0;
  const rd = data.readiness?.breakdown || {};
  const fit = data.fitness?.current || {};
  const races = data.race_predictions || [];
  const vo2 = data.vo2max_estimated || 0;
  const stepsWeek = data.steps_week || [];
  const hrvWeek = (data.hrv_week || []).map(h=>({d:h.d||h.day,hrv:h.hrv,rhr:h.rhr}));
  const hrHourly = (data.heart_rate?.hourly || []).map(h=>({h:h.hour,hr:h.hr}));
  const bbData = (data.body_battery || []).map(b=>({h:b.time,v:b.battery}));
  const filtered = filter==="Todas"?acts:acts.filter(a=>a.sport===filter);
  const totalKm = acts.reduce((s,a)=>s+(a.distance||0),0);
  const totalElev = acts.reduce((s,a)=>s+(a.elevation||0),0);

  /* ─── LOAD DATA FROM API ─── */
  const loadDashboard = useCallback(async()=>{
    if(!API_URL) return; // modo demo
    try{
      const res = await fetch(`${API_URL}/api/dashboard`);
      const json = await res.json();
      if(json.has_data){
        setData(json);
        setLastSync(json.meta?.garmin_synced || json.meta?.strava_synced);
      }
    }catch(e){console.error("Error cargando dashboard:",e)}
  },[]);

  // Cargar datos al montar
  useEffect(()=>{loadDashboard()},[loadDashboard]);

  /* ─── SYNC: descarga datos reales ─── */
  const handleSync = useCallback(async()=>{
    const steps = [
      {id:"garmin",label:"Descargando datos de Garmin...",status:"pending"},
      {id:"strava",label:"Descargando datos de Strava...",status:"pending"},
      {id:"calc",label:"Calculando métricas...",status:"pending"},
    ];
    setSyncSteps([...steps]);
    setShowSyncOverlay(true);

    if(!API_URL){
      // MODO DEMO: simular sync
      for(let i=0;i<steps.length;i++){
        steps[i].status="loading";setSyncSteps([...steps]);
        await new Promise(r=>setTimeout(r,1000+Math.random()*500));
        steps[i].status="done";setSyncSteps([...steps]);
      }
      await new Promise(r=>setTimeout(r,600));
      setShowSyncOverlay(false);
      setLastSync(new Date().toISOString());
      return;
    }

    // MODO REAL: llamar API
    try{
      // 1. Garmin
      steps[0].status="loading";setSyncSteps([...steps]);
      const g = await fetch(`${API_URL}/api/sync-garmin`).then(r=>r.json());
      steps[0].status=g.status==="ok"?"done":"error";setSyncSteps([...steps]);

      // 2. Strava
      steps[1].status="loading";setSyncSteps([...steps]);
      const s = await fetch(`${API_URL}/api/sync-strava`).then(r=>r.json());
      steps[1].status=s.status==="ok"?"done":"error";setSyncSteps([...steps]);

      // 3. Calculate
      steps[2].status="loading";setSyncSteps([...steps]);
      const c = await fetch(`${API_URL}/api/calculate`).then(r=>r.json());
      steps[2].status=c.status==="ok"?"done":"error";setSyncSteps([...steps]);

      // 4. Reload dashboard
      await new Promise(r=>setTimeout(r,500));
      await loadDashboard();
    }catch(e){
      console.error("Sync error:",e);
    }
    await new Promise(r=>setTimeout(r,600));
    setShowSyncOverlay(false);
  },[loadDashboard]);

  const timeSince = (iso)=>{
    if(!iso) return null;
    const mins = Math.round((Date.now()-new Date(iso).getTime())/60000);
    if(mins<1) return "ahora";if(mins<60) return `hace ${mins} min`;
    return `hace ${Math.round(mins/60)}h`;
  };

  const tabs=[{id:"resumen",label:"Resumen"},{id:"rendimiento",label:"Rendimiento"},{id:"actividades",label:"Actividades"}];

  return(
    <div style={{minHeight:"100vh",background:t.bg,fontFamily:"'Inter',-apple-system,BlinkMacSystemFont,sans-serif",transition:"background 0.3s",color:t.text}}>
      {/* HEADER */}
      <header style={{background:t.headerBg,padding:"16px 20px 14px",color:t.headerText,position:"sticky",top:0,zIndex:10,transition:"background 0.3s"}}>
        <div style={{maxWidth:560,margin:"0 auto"}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
            <div>
              <div style={{fontSize:10,color:t.headerSub,fontWeight:700,textTransform:"uppercase",letterSpacing:"0.1em"}}>Mi Salud</div>
              <div style={{fontSize:19,fontWeight:700}}>Hola, {data.profile?.name?.split(" ")[0]||"Toni"}</div>
              {lastSync&&<div style={{fontSize:10,color:t.headerSub,marginTop:2}}>Sync: {timeSince(lastSync)}</div>}
            </div>
            <div style={{display:"flex",alignItems:"center",gap:8}}>
              <button onClick={handleSync} style={{display:"flex",alignItems:"center",gap:6,padding:"7px 14px",border:"none",borderRadius:10,cursor:"pointer",background:t.syncBtnBg,color:t.headerText,fontSize:12,fontWeight:600,transition:"all 0.2s"}}>
                <SyncIcon spinning={false}/> Sync
              </button>
              <button onClick={()=>setDark(!dark)} style={{display:"flex",alignItems:"center",justifyContent:"center",width:36,height:36,border:"none",borderRadius:10,cursor:"pointer",background:t.syncBtnBg,color:t.headerText,transition:"all 0.2s"}}>
                <ThemeIcon dark={dark}/>
              </button>
            </div>
          </div>
          <div style={{display:"flex",gap:3,background:t.tabBg,borderRadius:10,padding:3}}>
            {tabs.map(tb=>(<button key={tb.id} onClick={()=>setTab(tb.id)} style={{flex:1,padding:"7px 0",fontSize:11,fontWeight:600,border:"none",borderRadius:8,cursor:"pointer",background:tab===tb.id?t.tabActive:"transparent",color:tab===tb.id?t.tabActiveText:t.tabText,transition:"all 0.2s"}}>{tb.label}</button>))}
          </div>
        </div>
      </header>

      <main style={{maxWidth:560,margin:"0 auto",padding:"14px 12px 40px"}}>

        {/* ─── RESUMEN ─── */}
        {tab==="resumen"&&<>
          <div style={{display:"flex",justifyContent:"space-around",flexWrap:"wrap",gap:6,marginBottom:14}}>
            {[{l:"Body Battery",v:d.body_battery_high||67,m:100,c:A.battery,u:"%"},{l:"Sueño",v:sleep.score||0,m:100,c:A.sleep,u:"pts"},{l:"Readiness",v:readiness,m:100,c:readiness>=70?A.battery:A.stress,u:""},{l:"VO₂ Max",v:vo2,m:60,c:A.vo2,u:"ml/kg"}].map((m,i)=>(
              <div key={i} style={{display:"flex",flexDirection:"column",alignItems:"center",gap:4}}>
                <Ring value={m.v} max={m.m} color={m.c}><span style={{fontSize:20,fontWeight:700,color:t.text}}>{m.v}</span><span style={{fontSize:9,color:t.sub,marginTop:-2}}>{m.u}</span></Ring>
                <span style={{fontSize:10,fontWeight:600,color:t.sub}}>{m.l}</span>
              </div>))}
          </div>

          <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:8,marginBottom:14}}>
            {[{i:"👣",v:(d.steps||0).toLocaleString(),u:"pasos"},{i:"🔥",v:(d.calories_total||0).toLocaleString(),u:"kcal"},{i:"❤️",v:d.resting_hr||"—",u:"bpm rep."},{i:"⚡",v:d.active_minutes||"—",u:"min act."}].map((s,i)=>(
              <div key={i} style={{background:t.quickBg,borderRadius:10,padding:"8px 4px",border:`1px solid ${t.cardBorder}`,textAlign:"center",transition:"background 0.3s"}}>
                <div style={{fontSize:15}}>{s.i}</div><div style={{fontSize:16,fontWeight:700,color:t.text}}>{s.v}</div><div style={{fontSize:9,color:t.muted}}>{s.u}</div>
              </div>))}
          </div>

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8,marginBottom:14}}>
            {[{icon:"💓",label:"HRV",value:hrv.last_night_avg||"—",unit:"ms"},{icon:"🫁",label:"SpO₂",value:d.avg_spo2||"—",unit:"%"},{icon:"🌬️",label:"Resp.",value:d.avg_respiration||"—",unit:"rpm"}].map((s,i)=>(
              <div key={i} style={{background:t.quickBg,borderRadius:10,padding:"10px 8px",border:`1px solid ${t.cardBorder}`,textAlign:"center",transition:"background 0.3s"}}>
                <div style={{fontSize:16}}>{s.icon}</div><div style={{fontSize:20,fontWeight:700,color:t.text}}>{s.value}</div>
                <div style={{fontSize:9,color:t.muted}}>{s.unit}</div><div style={{fontSize:10,fontWeight:600,color:t.sub,marginTop:2}}>{s.label}</div>
              </div>))}
          </div>

          <Card title="Sueño" accent={A.sleep} t={t} style={{marginBottom:14}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
              <span style={{fontSize:24,fontWeight:700,color:t.text}}>{sleep.total_formatted||"—"}</span>
              <span style={{fontSize:11,color:t.sub}}>{sleep.start_time&&sleep.end_time?`${String(sleep.start_time).slice(-5)} → ${String(sleep.end_time).slice(-5)}`:""} · Score {sleep.score||"—"}</span>
            </div>
            {(sleep.deep_min||sleep.light_min)&&<>
              <div style={{display:"flex",borderRadius:6,overflow:"hidden",height:12}}>
                {[{w:sleep.awake_min,c:"#f97066"},{w:sleep.rem_min,c:"#a78bfa"},{w:sleep.light_min,c:"#60a5fa"},{w:sleep.deep_min,c:"#1e3a5f"}].map((p,i)=><div key={i} style={{flex:p.w,background:p.c}}/>)}
              </div>
              <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
                {[{l:"Despierto",c:"#f97066",m:sleep.awake_min},{l:"REM",c:"#a78bfa",m:sleep.rem_min},{l:"Ligero",c:"#60a5fa",m:sleep.light_min},{l:"Profundo",c:"#1e3a5f",m:sleep.deep_min}].map((p,i)=>(
                  <div key={i} style={{display:"flex",alignItems:"center",gap:4}}><div style={{width:6,height:6,borderRadius:"50%",background:p.c}}/><span style={{fontSize:10,color:t.sub}}>{p.l}</span><span style={{fontSize:10,fontWeight:700,color:t.text}}>{Math.floor(p.m/60)}h{p.m%60}m</span></div>))}
              </div>
            </>}
          </Card>

          {hrvWeek.length>0&&<Card title="HRV + FC Reposo" accent={A.fitness} t={t} style={{marginBottom:14}}>
            <ResponsiveContainer width="100%" height={90}>
              <LineChart data={hrvWeek} margin={{top:5,right:5,left:-25,bottom:0}}>
                <XAxis dataKey="d" axisLine={false} tickLine={false} tick={{fontSize:10,fill:t.sub}}/><YAxis hide domain={[40,80]}/><Tooltip contentStyle={tt}/>
                <Line type="monotone" dataKey="hrv" stroke={A.fitness} strokeWidth={2.5} dot={{fill:A.fitness,r:3}} name="HRV"/><Line type="monotone" dataKey="rhr" stroke={A.hr} strokeWidth={1.5} strokeDasharray="4 3" dot={{fill:A.hr,r:2}} name="FC rep"/>
              </LineChart>
            </ResponsiveContainer>
          </Card>}

          {stepsWeek.length>0&&<Card title="Pasos — Semana" accent={A.steps} t={t} style={{marginBottom:14}}>
            <ResponsiveContainer width="100%" height={90}>
              <BarChart data={stepsWeek} barSize={26} margin={{top:0,right:0,left:-25,bottom:0}}>
                <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{fontSize:10,fill:t.sub}}/><YAxis hide/>
                <Tooltip contentStyle={tt} formatter={v=>[`${v.toLocaleString()}`,"pasos"]}/>
                <Bar dataKey="steps" radius={[4,4,0,0]}>{stepsWeek.map((e,i)=><Cell key={i} fill={e.steps>=10000?A.steps:t.barInactive}/>)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>}

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:14}}>
            {bbData.length>0&&<Card title="Body Battery" accent={A.battery} t={t}>
              <ResponsiveContainer width="100%" height={70}>
                <AreaChart data={bbData} margin={{top:0,right:0,left:-25,bottom:0}}>
                  <defs><linearGradient id="bb" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={A.battery} stopOpacity={0.3}/><stop offset="100%" stopColor={A.battery} stopOpacity={0}/></linearGradient></defs>
                  <XAxis dataKey="h" hide/><YAxis hide domain={[0,100]}/><Tooltip contentStyle={tt} formatter={v=>[`${Math.round(v)}%`,""]}/>
                  <Area type="monotone" dataKey="v" stroke={A.battery} strokeWidth={2} fill="url(#bb)"/></AreaChart>
              </ResponsiveContainer>
            </Card>}
            {hrHourly.length>0&&<Card title="FC — Hoy" accent={A.hr} t={t}>
              <ResponsiveContainer width="100%" height={70}>
                <AreaChart data={hrHourly} margin={{top:0,right:0,left:-25,bottom:0}}>
                  <defs><linearGradient id="hg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={A.hr} stopOpacity={0.2}/><stop offset="100%" stopColor={A.hr} stopOpacity={0}/></linearGradient></defs>
                  <XAxis dataKey="h" hide/><YAxis hide domain={[40,110]}/><Tooltip contentStyle={tt} formatter={v=>[`${v} bpm`,""]}/>
                  <Area type="monotone" dataKey="hr" stroke={A.hr} strokeWidth={2} fill="url(#hg)"/></AreaChart>
              </ResponsiveContainer>
            </Card>}
          </div>

          <Card title="Últimas actividades" t={t}>
            {acts.slice(0,3).map((a,i)=>(<div key={i} onClick={()=>setSel(a)} style={{display:"flex",alignItems:"center",gap:10,padding:"7px 0",cursor:"pointer",borderBottom:i<2?`1px solid ${t.cardBorder}`:"none"}}>
              <div style={{width:34,height:34,borderRadius:8,background:(sportColor[a.sport]||A.steps)+"15",display:"flex",alignItems:"center",justifyContent:"center",fontSize:15}}>{a.icon||"🏋️"}</div>
              <div style={{flex:1}}><div style={{fontSize:12,fontWeight:600,color:t.text}}>{a.name}</div><div style={{fontSize:10,color:t.sub}}>{a.date||a.date_formatted}·{a.distance}km</div></div>
              <span style={{fontSize:16,color:t.muted}}>›</span>
            </div>))}
            <button onClick={()=>setTab("actividades")} style={{width:"100%",padding:"7px",marginTop:6,border:"none",borderRadius:8,background:t.phaseBg,color:t.sub,fontSize:11,fontWeight:600,cursor:"pointer",transition:"background 0.3s"}}>Ver todas →</button>
          </Card>
        </>}

        {/* ─── RENDIMIENTO ─── */}
        {tab==="rendimiento"&&<>
          <Card title="Fitness · Fatiga · Forma" accent={A.fitness} t={t} style={{marginBottom:14}}>
            <div style={{display:"flex",justifyContent:"space-around",marginBottom:8}}>
              <div style={{textAlign:"center"}}><div style={{fontSize:22,fontWeight:700,color:A.fitness}}>{fit.ctl||"—"}</div><div style={{fontSize:10,color:t.sub}}>Fitness</div></div>
              <div style={{textAlign:"center"}}><div style={{fontSize:22,fontWeight:700,color:A.fatigue}}>{fit.atl||"—"}</div><div style={{fontSize:10,color:t.sub}}>Fatiga</div></div>
              <div style={{textAlign:"center"}}><div style={{fontSize:22,fontWeight:700,color:(fit.tsb||0)>=0?A.form:A.hr}}>{fit.tsb>0?"+":""}{fit.tsb||"—"}</div><div style={{fontSize:10,color:t.sub}}>Forma</div></div>
            </div>
            <div style={{fontSize:11,color:t.sub,textAlign:"center"}}>{(fit.tsb||0)>5?"🟢 Descansado — listo para competir":(fit.tsb||0)>-5?"🟡 Equilibrado":"🔴 Fatigado — considera descanso"}</div>
          </Card>

          {races.length>0&&<Card title="Predicción de Carreras" accent={A.vo2} t={t} style={{marginBottom:14}}>
            <div style={{fontSize:11,color:t.sub,marginBottom:4}}>VO₂ Max {vo2} ml/kg/min</div>
            {races.map((r,i)=>(<div key={i} style={{display:"flex",alignItems:"center",padding:"8px 0",borderBottom:i<races.length-1?`1px solid ${t.cardBorder}`:"none"}}>
              <span style={{width:55,fontSize:13,fontWeight:700,color:t.text}}>{r.distance||r.dist}</span>
              <div style={{flex:1,marginRight:8}}><div style={{height:6,background:t.phaseBg,borderRadius:3,overflow:"hidden"}}><div style={{width:`${[40,55,75,100][i]||50}%`,height:"100%",background:`linear-gradient(90deg,${A.vo2},${A.fitness})`,borderRadius:3}}/></div></div>
              <span style={{width:65,fontSize:14,fontWeight:700,color:t.text,textAlign:"right"}}>{r.time}</span>
              <span style={{width:55,fontSize:10,color:t.sub,textAlign:"right"}}>{r.pace}</span>
            </div>))}
          </Card>}

          <Card title="Training Readiness" accent={readiness>=70?A.battery:A.stress} t={t} style={{marginBottom:14}}>
            <div style={{textAlign:"center",marginBottom:8}}>
              <Ring value={readiness} max={100} size={100} stroke={9} color={readiness>=70?A.battery:A.stress}>
                <span style={{fontSize:28,fontWeight:700,color:t.text}}>{readiness}</span><span style={{fontSize:9,color:t.sub}}>/ 100</span>
              </Ring>
            </div>
            {[{l:"Sueño",v:rd.sleep?.value||0,c:A.sleep},{l:"HRV",v:rd.hrv?.value||0,c:A.fitness},{l:"Body Battery",v:rd.body_battery?.value||0,c:A.battery},{l:"Carga",v:rd.load?.value||0,c:A.fatigue}].map((f,i)=>(
              <div key={i} style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
                <span style={{width:85,fontSize:11,fontWeight:600,color:t.text}}>{f.l}</span>
                <div style={{flex:1,height:8,background:t.phaseBg,borderRadius:4,overflow:"hidden"}}><div style={{width:`${f.v}%`,height:"100%",background:f.c,borderRadius:4}}/></div>
                <span style={{width:28,fontSize:11,fontWeight:700,color:t.text,textAlign:"right"}}>{f.v}</span>
              </div>))}
          </Card>

          <Card title="Volumen — 3 semanas" t={t}>
            <div style={{display:"flex",justifyContent:"space-around"}}>
              <div style={{textAlign:"center"}}><div style={{fontSize:20,fontWeight:700,color:t.text}}>{totalKm.toFixed(0)}</div><div style={{fontSize:10,color:t.sub}}>km</div></div>
              <div style={{textAlign:"center"}}><div style={{fontSize:20,fontWeight:700,color:t.text}}>{totalElev.toLocaleString()}</div><div style={{fontSize:10,color:t.sub}}>m desnivel</div></div>
              <div style={{textAlign:"center"}}><div style={{fontSize:20,fontWeight:700,color:t.text}}>{acts.length}</div><div style={{fontSize:10,color:t.sub}}>actividades</div></div>
            </div>
          </Card>
        </>}

        {/* ─── ACTIVIDADES ─── */}
        {tab==="actividades"&&<>
          <div style={{display:"flex",gap:6,marginBottom:14,flexWrap:"wrap"}}>
            {["Todas","Run","Ride","Hike"].map(f=>(<button key={f} onClick={()=>setFilter(f)} style={{padding:"5px 14px",borderRadius:20,fontSize:11,fontWeight:600,border:"none",cursor:"pointer",transition:"all 0.2s",
              background:filter===f?(f==="Todas"?t.filterActiveBg:sportColor[f]):(f==="Todas"?t.filterBg:(sportColor[f]||A.steps)+"15"),
              color:filter===f?"#fff":(f==="Todas"?t.sub:(sportColor[f]||A.steps))
            }}>{f==="Todas"?"Todas":f==="Run"?"🏃 Correr":f==="Ride"?"🚴 Bici":"⛰️ Senderismo"}</button>))}
          </div>
          {filtered.map((a,i)=>(<div key={i} onClick={()=>setSel(a)} style={{background:t.card,borderRadius:12,padding:"14px 16px",marginBottom:10,border:`1px solid ${t.cardBorder}`,borderLeft:`3px solid ${sportColor[a.sport]||A.steps}`,cursor:"pointer",transition:"background 0.3s"}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"start",marginBottom:8}}>
              <div><div style={{fontSize:14,fontWeight:700,color:t.text}}>{a.icon||"🏋️"} {a.name}</div><div style={{fontSize:11,color:t.sub,marginTop:2}}>{a.date||a.date_formatted}</div></div>
              <div style={{display:"flex",alignItems:"center",gap:6}}>
                <div style={{padding:"3px 10px",borderRadius:12,fontSize:11,fontWeight:700,
                  background:(a.effort||0)>100?t.badgeRed.bg:(a.effort||0)>50?t.badgeYellow.bg:t.badgeGreen.bg,
                  color:(a.effort||0)>100?t.badgeRed.fg:(a.effort||0)>50?t.badgeYellow.fg:t.badgeGreen.fg}}>RE {a.effort||0}</div>
                <span style={{fontSize:18,color:t.muted}}>›</span></div>
            </div>
            <div style={{display:"flex",gap:16,flexWrap:"wrap"}}>
              <Stat label="Distancia" value={`${a.distance} km`} t={t}/><Stat label="Tiempo" value={a.time} t={t}/><Stat label="Desnivel" value={`↑${a.elevation}m`} t={t}/>
              {a.pace&&<Stat label="Ritmo" value={`${a.pace}/km`} t={t}/>}{a.avg_speed&&<Stat label="Vel." value={a.avg_speed} t={t}/>}
            </div>
          </div>))}
          {filtered.length===0&&<div style={{textAlign:"center",padding:40,color:t.muted}}>No hay actividades de este tipo</div>}
        </>}

        {/* No data message */}
        {!acts.length&&tab==="resumen"&&!API_URL&&(
          <div style={{background:t.card,borderRadius:14,padding:24,border:`1px solid ${t.cardBorder}`,textAlign:"center",marginTop:16}}>
            <div style={{fontSize:32,marginBottom:8}}>☝️</div>
            <div style={{fontSize:14,fontWeight:700,color:t.text,marginBottom:4}}>Pulsa "Sync" para descargar tus datos</div>
            <div style={{fontSize:12,color:t.sub}}>Conectará con Garmin y Strava para traer tus métricas reales</div>
          </div>
        )}
      </main>

      {sel&&<ActivityDetail activity={sel} onClose={()=>setSel(null)} t={t}/>}
      {showSyncOverlay&&<SyncOverlay steps={syncSteps} t={t}/>}
      <div style={{textAlign:"center",padding:"0 0 20px",fontSize:10,color:t.muted}}>Garmin + Strava · {data.profile?.name||"Mi Salud"}</div>
    </div>
  );
}
