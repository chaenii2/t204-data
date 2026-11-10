/* T204 데이터 로더: relay(중계 파일 1개) / direct(각 API 직접 호출) + 연결 진단 */
(function(){
const CFG = window.T204_CONFIG || {mode:'embedded'};
const pad=n=>String(n).padStart(2,'0');
const kst=()=>{const d=new Date();return new Date(d.getTime()+(d.getTimezoneOffset()+540)*60000)};
const ymd=d=>`${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}`;
const DOW=['SUN','MON','TUE','WED','THU','FRI','SAT'];
const qs=o=>Object.entries(o).map(([k,v])=>`${k}=${k==='serviceKey'?v:encodeURIComponent(v)}`).join('&');
async function getJSON(url,timeout=12000){
  const ac=new AbortController(); const t=setTimeout(()=>ac.abort(),timeout);
  try{const r=await fetch(url,{cache:'no-store',signal:ac.signal}); if(!r.ok) throw new Error('HTTP '+r.status); return await r.json();}
  finally{clearTimeout(t)}
}

/* ---------- 공모주 카드: 날짜 기준으로 화면에서 계산 ---------- */
function toDate(s){const [y,m,d]=s.split('-').map(Number);return new Date(y,m-1,d)}
function ipoCards(list,today,evening){
  const day=86400000, t0=new Date(today.getFullYear(),today.getMonth(),today.getDate());
  const ref=new Date(t0.getTime()+(evening?day:0)); const out=[];
  [...list].sort((a,b)=>a.start.localeCompare(b.start)).forEach(o=>{
    const s=toDate(o.start), e=toDate(o.end);
    if(e<ref || (s-t0)/day>10) return;
    let badge;
    if(s<=t0 && t0<=e){ badge = +e===+t0?'오늘 마감':(evening && +e===+ref?'내일 마감':'청약 중'); }
    else { const n=Math.round((s-t0)/day); badge = n===1?'내일 시작':`D-${n}`; }
    const f=d=>`${pad(d.getMonth()+1)}.${pad(d.getDate())}`;
    out.push({badge,name:o.name,period:`${f(s)} ~ ${f(e)}`,price:o.price,broker:o.broker});
  });
  return out.slice(0,2);
}
function finalize(feed){
  const now=kst();
  feed.date=`${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`;
  feed.dow=DOW[now.getDay()];
  feed.sample=false;
  feed.location=feed.location||'테헤란로 204 · 역삼';
  feed.updated=feed.updated||{morning:'',evening:''};
  feed.sponsor=feed.sponsor||{morning:'',evening:''};
  if(Array.isArray(feed.ipo_list)) feed.ipo={morning:ipoCards(feed.ipo_list,now,false),evening:ipoCards(feed.ipo_list,now,true)};
  return feed;
}

/* ---------- relay: 중계 파일 하나 ---------- */
async function loadRelay(){ return finalize(await getJSON(CFG.feedUrl+'?t='+Date.now())); }

/* ---------- direct: 각 API 직접 호출 ---------- */
const SKY={'1':'맑음','3':'구름많음','4':'흐림'}, PTY={'1':'비','2':'비/눈','3':'눈','4':'소나기','5':'빗방울','6':'빗방울눈날림','7':'눈날림'};
const iconOf=(sky,pty)=>pty&&pty!=='0'?'rain':({'1':'clear','3':'partly','4':'cloudy'}[sky]||'partly');
async function dWeather(){
  const now=kst(); let base=new Date(now); base.setHours(2,0,0,0);
  if(now.getHours()*60+now.getMinutes()<135){base=new Date(base.getTime()-86400000);base.setHours(23)}
  const d=await getJSON(`https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst?`+qs({serviceKey:CFG.keys.DATA_GO_KR_KEY,pageNo:1,numOfRows:1000,dataType:'JSON',base_date:ymd(base),base_time:pad(base.getHours())+'00',nx:61,ny:125}));
  const items=d.response.body.items.item, today=ymd(now), v={};
  items.filter(i=>i.fcstDate===today).forEach(i=>{(v[i.fcstTime]=v[i.fcstTime]||{})[i.category]=i.fcstValue});
  const ts=Object.values(v).filter(x=>x.TMP).map(x=>+x.TMP);
  const tmn=+(Object.values(v).find(x=>x.TMN)||{}).TMN||Math.min(...ts), tmx=+(Object.values(v).find(x=>x.TMX)||{}).TMX||Math.max(...ts);
  const day=Object.keys(v).sort().filter(t=>t>='0600'&&t<='2100');
  const pop=Math.max(...day.map(t=>+(v[t].POP||0)));
  const ptys=day.map(t=>v[t].PTY||'0').filter(x=>x!=='0'), skies=day.map(t=>v[t].SKY||'1');
  const mode=a=>a.sort((x,y)=>a.filter(z=>z===y).length-a.filter(z=>z===x).length)[0];
  let text,sky; if(ptys.length){text=PTY[mode(ptys)]||'비';sky='rain'}else{const m=mode(skies);text=SKY[m]||'구름많음';sky=iconOf(m,'0')}
  const hourly=['0900','1200','1500','1800'].filter(h=>v[h]&&v[h].TMP).map(h=>({h:`${+h.slice(0,2)}시`,t:Math.round(+v[h].TMP),sky:iconOf(v[h].SKY,v[h].PTY)}));
  const gap=Math.round(tmx-tmn);
  const tip=pop>=60?`강수확률 ${pop}%, 우산을 꼭 챙기세요`:gap>=10?`일교차 ${gap}도, 겉옷을 챙기세요`:tmx>=30?'무더운 날씨, 물 자주 드세요':tmn<=-5?'한파 주의, 따뜻하게 입으세요':'활동하기 좋은 날씨예요';
  const w={sky,text,min:Math.round(tmn),max:Math.round(tmx),pop,tip,hourly};
  try{ // 지금 기온 (초단기실황)
    const b=new Date(now.getTime()-40*60000);
    const n=await getJSON(`https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst?`+qs({serviceKey:CFG.keys.DATA_GO_KR_KEY,pageNo:1,numOfRows:20,dataType:'JSON',base_date:ymd(b),base_time:pad(b.getHours())+'00',nx:61,ny:125}));
    const t=n.response.body.items.item.find(i=>i.category==='T1H'); if(t) w.now={t:Math.round(+t.obsrValue),at:`${pad(b.getHours())}:00`};
  }catch(e){}
  return w;
}
async function dDust(){
  const d=await getJSON(`https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty?`+qs({serviceKey:CFG.keys.DATA_GO_KR_KEY,returnType:'json',numOfRows:12,pageNo:1,stationName:'강남구',dataTerm:'DAILY',ver:'1.0'}));
  const it=d.response.body.items.find(i=>i.pm10Value&&i.pm10Value!=='-'&&i.pm10Grade);
  return it?({'1':'좋음','2':'보통','3':'나쁨','4':'매우나쁨'}[it.pm10Grade]||'보통'):'보통';
}
async function dFx(){
  const FX=[['USD','미국 달러','USD',''],['JPY(100)','일본 엔','JPY','100엔'],['EUR','유로','EUR',''],['CNH','중국 위안','CNY','']];
  const found=[];
  for(let b=0;b<12&&found.length<2;b++){
    const day=new Date(kst().getTime()-b*86400000);
    const d=await getJSON(`https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?`+qs({authkey:CFG.keys.KOREAEXIM_KEY,searchdate:ymd(day),data:'AP01'}));
    if(Array.isArray(d)&&d.length&&+d[0].result===1){const m={};d.forEach(r=>m[r.cur_unit]=+String(r.deal_bas_r).replace(/,/g,''));found.push([day,m])}
  }
  const [[d0,cur],[,prev]]=found;
  return {basis:`${pad(d0.getMonth()+1)}.${pad(d0.getDate())} 매매기준율 · 한국수출입은행`,items:FX.filter(f=>cur[f[0]]).map(([k,n,c,u])=>({name:n,code:c,unit:u,v:cur[k],d:+(cur[k]-prev[k]).toFixed(2)}))};
}
async function dIpo(){
  const now=kst(), bg=ymd(new Date(now.getTime()-75*86400000)), ed=ymd(now);
  const l=await getJSON(`https://opendart.fss.or.kr/api/list.json?`+qs({crtfc_key:CFG.keys.DART_KEY,bgn_de:bg,end_de:ed,pblntf_detail_ty:'C001',page_count:100}));
  const seen=new Set(), out=[];
  for(const r of (l.list||[])){
    if(r.corp_cls!=='E'||seen.has(r.corp_code)) continue; seen.add(r.corp_code);
    if(seen.size>14) break;
    try{
      const d=await getJSON(`https://opendart.fss.or.kr/api/estkRs.json?`+qs({crtfc_key:CFG.keys.DART_KEY,corp_code:r.corp_code,bgn_de:bg,end_de:ed}));
      if(d.status!=='000') continue;
      const g={}; d.group.forEach(x=>g[x.title]=x.list);
      const gen=(g['일반사항']||[{}]).slice(-1)[0]; const m=[...(gen.sbd||'').matchAll(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/g)];
      if(!m.length) continue;
      const iso=x=>`${x[1]}-${pad(x[2])}-${pad(x[3])}`;
      const price=((g['증권의종류']||[{}]).slice(-1)[0].slprc)||gen.exprc||'-';
      const lead=(g['인수인정보']||[]).find(x=>x.actsen==='대표');
      out.push({name:gen.corp_name||r.corp_name,start:iso(m[0]),end:iso(m[m.length-1]),price:price&&price!=='-'?price+'원':'공모가 확정 전',broker:lead?'대표주관 '+lead.actnmn:''});
    }catch(e){}
  }
  return out;
}
async function loadDirect(){
  const feed={source:'direct'}; const errs=[];
  const run=async(k,fn,def)=>{try{feed[k]=await fn()}catch(e){feed[k]=def;errs.push(k+': '+e.message)}};
  await Promise.all([run('weather',dWeather,null),run('_pm',dDust,null),run('fx',dFx,{basis:'',items:[]}),run('ipo_list',dIpo,[])]);
  if(feed.weather) feed.weather.pm=feed._pm||'보통';
  const n=kst(); feed.generated_at=`${n.getFullYear()}-${pad(n.getMonth()+1)}-${pad(n.getDate())} ${pad(n.getHours())}:${pad(n.getMinutes())}`;
  feed.errors=errs; return finalize(feed);
}

window.T204_IPO = ipoCards;
window.T204_LOAD = async function(){
  if(CFG.mode==='relay') return loadRelay();
  if(CFG.mode==='direct') return loadDirect();
  return null;
};

/* ---------- 연결 진단 화면 (#diag) ---------- */
window.T204_DIAG = async function(root){
  const now=kst(), b=new Date(now.getTime()-40*60000);
  const T=[];
  if(CFG.mode==='relay') T.push(['중계 데이터 파일', CFG.feedUrl]);
  else {
    const k=CFG.keys||{};
    T.push(['기상청 (apis.data.go.kr)',`https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst?`+qs({serviceKey:k.DATA_GO_KR_KEY,pageNo:1,numOfRows:20,dataType:'JSON',base_date:ymd(b),base_time:pad(b.getHours())+'00',nx:61,ny:125})]);
    T.push(['에어코리아 (apis.data.go.kr)',`https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty?`+qs({serviceKey:k.DATA_GO_KR_KEY,returnType:'json',numOfRows:1,pageNo:1,stationName:'강남구',dataTerm:'DAILY',ver:'1.0'})]);
    T.push(['수출입은행 (oapi.koreaexim.go.kr)',`https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?`+qs({authkey:k.KOREAEXIM_KEY,searchdate:ymd(now),data:'AP01'})]);
    T.push(['OpenDART (opendart.fss.or.kr)',`https://opendart.fss.or.kr/api/list.json?`+qs({crtfc_key:k.DART_KEY,pblntf_detail_ty:'C001',page_count:1})]);
  }
  const rows=T.map(([n])=>`<tr><td>${n}</td><td class="st">확인 중…</td></tr>`).join('');
  root.innerHTML=`<div style="padding:70px 60px;font-size:34px;line-height:1.5;color:#fff">
    <div style="font-size:30px;color:#ff6a3d;font-weight:700">T204 연결 진단 · ${CFG.mode==='relay'?'A/C 중계 방식':'B 직접 호출 방식'}</div>
    <div style="font-size:26px;color:#9fb0cc;margin:8px 0 30px">${ymd(now)} ${pad(now.getHours())}:${pad(now.getMinutes())} · ${navigator.userAgent.slice(0,90)}</div>
    <table style="width:100%;border-collapse:collapse">${rows}</table>
    <div style="font-size:26px;color:#9fb0cc;margin-top:40px;line-height:1.6">✅ 연결 성공 · ⛔CORS 서버엔 닿지만 보안 정책으로 차단 · ⛔네트워크 방화벽 등으로 연결 불가<br>이 화면을 캡처해서 중앙일보 담당자에게 보내 주세요.</div></div>
    <style>td{padding:22px 10px;border-bottom:2px solid rgba(255,255,255,.15);vertical-align:top} td.st{width:52%;font-weight:700}</style>`;
  const cells=[...root.querySelectorAll('td.st')];
  await Promise.all(T.map(async([n,url],i)=>{
    const c=cells[i];
    try{const d=await getJSON(url,10000); c.innerHTML='✅ 연결 성공<br><span style="font-size:24px;font-weight:400;color:#9fb0cc">'+JSON.stringify(d).slice(0,90).replace(/</g,'&lt;')+'</span>';}
    catch(e){
      let reach=false; try{await fetch(url,{mode:'no-cors',cache:'no-store'});reach=true}catch(_){}
      c.innerHTML = reach?'⛔ CORS 차단<br><span style="font-size:24px;font-weight:400;color:#9fb0cc">서버 응답은 오지만 브라우저 보안 정책으로 읽을 수 없음</span>':'⛔ 연결 불가<br><span style="font-size:24px;font-weight:400;color:#9fb0cc">'+String(e.message).slice(0,80)+'</span>';
    }
  }));
};
})();
