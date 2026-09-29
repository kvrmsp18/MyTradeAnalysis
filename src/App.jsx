import React,{useEffect,useMemo,useState} from 'react';
import {Activity,AlertTriangle,BarChart3,Bell,Brain,CandlestickChart,CircleDollarSign,Eye,FileText,Gauge,History,LayoutDashboard,Menu,Pause,Play,Search,Settings,ShieldCheck,Square,Target,TrendingUp,Wallet,X} from 'lucide-react';
import {frameworkSummary} from './strategyFrameworks';

const DATA='/MyTradeAnalysis/data/market_snapshot.json';
const EOD='/MyTradeAnalysis/data/eod_report.json';
const SCRAP='/MyTradeAnalysis/data/scrap_analysis.json';
const COUNCIL='/MyTradeAnalysis/data/ai_research_council.json';
const PAPER_STATE='/MyTradeAnalysis/data/paper_state.json';

const NAV=[
  ['dashboard','Dashboard',LayoutDashboard],['screener','Stock Screener',Search],['stock360','Stock 360',BarChart3],
  ['regime','Market Regime',TrendingUp],['scrap','SCRAP Analysis',Brain],['strategies','Strategy Council',Brain],['paper','Paper Trading',CircleDollarSign],
  ['live','Live Trading',Target],['journal','Trade Journal',FileText],['baskets','Thematic Baskets',CandlestickChart],
  ['postmortem','Post-Mortem',History],['supervisor','Supervisor',ShieldCheck],['health','System Health',Gauge],
  ['notifications','Notifications',Bell],['settings','Settings',Settings]
];

function marketState(snapshot){
  const now=new Date();
  const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(now);
  const get=k=>parts.find(p=>p.type===k)?.value;
  const weekday=get('weekday');
  const hour=Number(get('hour'));
  const minute=Number(get('minute'));
  const minutes=hour*60+minute;
  const session=weekday!=='Sat'&&weekday!=='Sun'&&minutes>=555&&minutes<930;
  const live=['LIVE_MARKET_DATA','LIVE_MARKET_DATA_NSE','LIVE_MARKET_DATA_NSE_PROXY','LIVE_MARKET_DATA_FALLBACK'].includes(snapshot?.status);
  const stamp=snapshot?.timestamp?new Date(snapshot.timestamp):null;
  const age=stamp&&!Number.isNaN(stamp.getTime())?(Date.now()-stamp.getTime())/60000:null;
  const fresh=age!==null&&age<=10;
  if(session&&live&&fresh){
    const fallback=snapshot?.status==='LIVE_MARKET_DATA_FALLBACK';
    return {label:fallback?'MARKET OPEN • LIVE DATA (YAHOO FALLBACK)':'MARKET OPEN • LIVE DATA',tone:fallback?'warn':'live',live:true};
  }
  if(session&&live&&!fresh)return {label:'MARKET OPEN • STALE DATA',tone:'warn',live:false};
  if(session)return {label:'MARKET OPEN • DATA UNAVAILABLE',tone:'warn',live:false};
  return {label:'MARKET CLOSED',tone:'closed',live:false};
}

export default function App(){
  const [tab,setTab]=useState('dashboard');
  const [menu,setMenu]=useState(false);
  const [search,setSearch]=useState('');
  const [stop,setStop]=useState(false);
  const [paper,setPaper]=useState(true);
  const [snapshot,setSnapshot]=useState(null);
  const [eod,setEod]=useState(null);
  const [scrap,setScrap]=useState(null);
  const [council,setCouncil]=useState(null);
  const [paperState,setPaperState]=useState(null);
  const [notice,setNotice]=useState('');
  const [loading,setLoading]=useState(true);

  async function load(){
    try{
      const responses=await Promise.all([fetch(DATA+'?t='+Date.now()),fetch(EOD+'?t='+Date.now()),fetch(SCRAP+'?t='+Date.now()),fetch(COUNCIL+'?t='+Date.now()),fetch(PAPER_STATE+'?t='+Date.now())]);
      const nextSnapshot=await responses[0].json();
      const nextEod=await responses[1].json();
      const nextScrap=await responses[2].json();
      const nextCouncil=await responses[3].json();
      const nextPaperState=await responses[4].json();
      setSnapshot(nextSnapshot);
      setEod(nextEod);
      setScrap(nextScrap);
      setCouncil(nextCouncil);
      setPaperState(nextPaperState);
    }catch(error){
      setSnapshot({status:'DATA_UNAVAILABLE',reason:'Market snapshot could not be loaded.',stocks:[]});
      setEod({status:'NOT_READY',profitable_moves:0,missed_opportunities:[],general_patterns:[]});
      setScrap({status:'NOT_RUN',stocks:[],stock_specific_rule_created:false,reason:'SCRAP data could not be loaded.'});
      setCouncil({status:'NOT_RUN',consensus:{status:'NOT_RUN',classification:'HOLD_FOR_REVIEW'}});
      setPaperState({cash:0,positions:{},realized_pnl:0,trade_count:0,funds_check:'UNAVAILABLE'});
    }finally{setLoading(false)}
  }

  useEffect(()=>{load();const timer=setInterval(load,30000);return()=>clearInterval(timer)},[]);

  const stocks=(snapshot&&snapshot.stocks)||[];
  const filtered=useMemo(()=>stocks.filter(stock=>{
    const q=search.toUpperCase();
    return String(stock.symbol||'').toUpperCase().includes(q)||String(stock.sector||'').toUpperCase().includes(q);
  }),[stocks,search]);
  const market=marketState(snapshot);

  function showNotice(text){setNotice(text);setTimeout(()=>setNotice(''),4500)}
  function runCycle(){
    if(stop){showNotice('Emergency stop is active. No paper cycle was started.');return}
    if(!market.live){
      showNotice('Market is closed or the latest snapshot is stale. The 5-minute paper cycle is scheduled automatically for the next market session.');
      return;
    }
    window.open('https://github.com/kvrmsp18/MyTradeAnalysis/actions/workflows/paper-cycle.yml','_blank','noopener,noreferrer');
    showNotice('Manual cycle opened in GitHub Actions. Select “Run workflow” on main. Scheduled 5-minute paper cycles continue automatically.');
  }

  function renderPage(){
    if(tab==='dashboard')return <Dashboard snapshot={snapshot} eod={eod} scrap={scrap} council={council} paperState={paperState} loading={loading} stop={stop} paper={paper} setTab={setTab} runCycle={runCycle} market={market}/>;
    if(tab==='screener')return <Screener stocks={filtered} scrap={scrap} status={snapshot&&snapshot.status} search={search} setSearch={setSearch}/>;
    if(tab==='stock360')return <Stock360 stock={filtered[0]||stocks[0]} scrap={scrap} status={snapshot&&snapshot.status}/>;
    if(tab==='regime')return <Regime live={market.live} snapshot={snapshot}/>;
    if(tab==='scrap')return <Scrap live={market.live} count={stocks.length} scrap={scrap}/>;
    if(tab==='strategies')return <StrategyCouncil stock={filtered[0]||stocks[0]} live={market.live}/>;
    if(tab==='paper')return <Paper stop={stop} paperState={paperState} showNotice={showNotice}/>;
    if(tab==='live')return <Locked title="Live Trading" text="Live broker execution is locked during paper validation."/>;
    if(tab==='journal')return <EmptyPage title="Trade Journal" text="Decision-time evidence and paper fills will appear here after the paper execution engine is connected."/>;
    if(tab==='baskets')return <Baskets/>;
    if(tab==='postmortem')return <PostMortem report={eod}/>;
    if(tab==='supervisor')return <Supervisor live={market.live} paper={paper}/>;
    if(tab==='health')return <Health snapshot={snapshot} eod={eod} paper={paper} scrap={scrap} council={council}/>;
    if(tab==='notifications')return <EmptyPage title="Notifications" text="Telegram notification integration will be connected after the core paper engine is stable."/>;
    return <SettingsPage paper={paper} setPaper={setPaper}/>;
  }

  return <div className="app">
    {menu&&<div className="mobileBackdrop" onClick={()=>setMenu(false)}/>} 
    <aside className={menu?'sidebar open':'sidebar'}>
      <div className="brand"><div className="logo">↗</div><div><b>NSE BSE Intraday AI</b><span>Trading Platform</span></div></div>
      <div className="nav">{NAV.map(item=>{const Icon=item[2];return <button key={item[0]} className={tab===item[0]?'navBtn active':'navBtn'} onClick={()=>{setTab(item[0]);setMenu(false)}}><Icon size={17}/>{item[1]}</button>})}</div>
      <div className="sideCard"><div className="miniLabel">TRADING MODE</div><div className="modePill"><span/> PAPER TRADING</div><p>Live execution is disabled during validation.</p></div>
    </aside>
    <main className="main">
      <header className="top">
        <button className="menu" onClick={()=>setMenu(true)}><Menu/></button>
        <div className="brandMobile"><b>NSE BSE Intraday AI</b><span>Trading Platform</span></div>
        <div className="globalSearch"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search stocks (e.g. RELIANCE, TCS, INFY)..."/></div>
        <div className="topRight">
          <div className="modeSwitch"><button className={paper?'selected':''} onClick={()=>setPaper(true)}><span/>Paper Trading</button><button onClick={()=>showNotice('Live Trading is locked until paper validation is complete.')}>● Live Trading</button></div>
          <div className="connections"><span className={market.live?'ok':'muted'}>●</span>Dhan <span className="muted">●</span>Telegram <span className="muted">●</span>OpenAI <span className="muted">●</span>Anthropic</div>
          <button className="iconBtn" onClick={()=>setTab('settings')}><Settings size={17}/></button>
        </div>
      </header>
      <div className="content">
        <div className="pageTop"><div className="crumb"><span>MyTradeAnalysis</span><i>/</i><b>{(NAV.find(item=>item[0]===tab)||[])[1]}</b></div><div className={'marketStatus '+market.tone}><span className="statusDot"/>{market.label}<button className="stopBtn" onClick={()=>setStop(!stop)}><Square size={12}/>{stop?'STOPPED':'Stop Bot'}</button></div></div>
        {notice&&<div className="notice">{notice}<X size={15} onClick={()=>setNotice('')}/></div>}
        {renderPage()}
      </div>
    </main>
  </div>;
}

function Dashboard({snapshot,eod,scrap,council,paperState,loading,stop,paper,setTab,runCycle,market}){
  const stocks=(snapshot&&snapshot.stocks)||[];
  const live=market.live;
  const scrapRows=(scrap&&scrap.stocks)||[];
  const scrapMap=useMemo(()=>new Map(scrapRows.map(row=>[row.symbol,row])),[scrapRows]);
  const top=[...stocks].sort((a,b)=>(Number(scrapMap.get(b.symbol)?.score)||0)-(Number(scrapMap.get(a.symbol)?.score)||0)||(Number(b.change)||0)-(Number(a.change)||0)).slice(0,5);
  const index=(snapshot&&snapshot.indices)||{};
  const regime=snapshot&&snapshot.regime&&snapshot.regime.label?snapshot.regime.label:'UNAVAILABLE';
  return <>
    <section className="dashTitle"><div><h1>Dashboard</h1><p>Live market overview and trading bot status</p></div><div className="date">{snapshot&&snapshot.timestamp?new Date(snapshot.timestamp).toLocaleString():'Waiting for market feed'}</div></section>
    <div className="dashboardCards">
      <MarketMetric title="NIFTY 50" value={index.nifty50||'—'} sub={index.nifty50_change||'—'}/><MarketMetric title="BANKNIFTY" value={index.banknifty||'—'} sub={index.banknifty_change||'—'}/>
      <MarketMetric title="Market Regime" value={regime} sub={live?`Source: ${snapshot?.source||'validated feed'}`:'Awaiting data'} icon={TrendingUp}/><MarketMetric title="Paper Cash" value={paperState?`₹${Number(paperState.cash||0).toLocaleString('en-IN')}`:'—'} sub={paperState?.funds_check==='PASS'?'Broker funds gate passed internally':'Funds check unavailable'} icon={Wallet}/><MarketMetric title="Today's P&L" value={paperState?`₹${Number(paperState.realized_pnl||0).toFixed(2)}`:'—'} sub={`${paperState?.trade_count||0} simulated trade events`} icon={BarChart3}/><MarketMetric title="Open Positions" value={paperState?Object.keys(paperState.positions||{}).length:'—'} sub="Paper positions" icon={FileText}/>
    </div>
    <div className="dashGrid">
      <section className="card"><div className="cardHead"><div><h3>Live Market Overview</h3><span>{market.label}</span></div><div className="tabs"><button className="active">NIFTY 50</button><button>BANKNIFTY</button><button>SENSEX</button></div></div><div className="bigChart"><div className="gridLines"/><div className="line"/><div className="chartLabel">{live?'Validated live series will populate here':'Waiting for a fresh validated market feed'}</div><div className="axis"><span>25,500</span><span>25,400</span><span>25,300</span><span>25,200</span></div></div></section>
      <section className="card"><div className="cardHead"><div><h3>Bot Status</h3><span>Deterministic execution state</span></div><span className="running">{stop?'STOPPED':'● Running'}</span></div><div className="statusList"><StatusRow name="Trading Mode" value="Paper Trading" blue/><StatusRow name="Market Hours" value={market.label} green={market.live} warn={!market.live}/><StatusRow name="Last Analysis" value={snapshot&&snapshot.timestamp?new Date(snapshot.timestamp).toLocaleTimeString():'—'}/><StatusRow name="Next Scan" value="5 min cadence"/><StatusRow name="Active Trades" value="0"/><StatusRow name="Daily Trades Limit" value="0 / 20"/><StatusRow name="Daily Loss Limit" value="₹0 / ₹5,000" red/><StatusRow name="Daily Profit Target" value="₹0 / ₹3,000" green={false}/><StatusRow name="Risk Status" value={live?'Normal':'WAITING FOR DATA'} green={live} warn={!live}/><StatusRow name="Data Source" value={snapshot?.source||'—'} warn={snapshot?.status==='LIVE_MARKET_DATA_FALLBACK'}/></div><div className="buttonRow"><button className="primary" onClick={runCycle}><Play size={15}/> Run Cycle Now</button><button className="secondary"><Pause size={14}/> Bot {stop?'Stopped':'Running'}</button></div></section>
    </div>
    <div className="dashGrid lower">
      <section className="card"><div className="cardHead"><div><h3>AI Market Analysis</h3><span>OpenAI + Anthropic research council</span></div><span className="aiBadge">{council?.status||'Council'}</span></div><div className="aiBox"><Brain size={22}/><div><b>Independent analysis → cross-critique → synthesis</b><p>OpenAI: {council?.independent_classifications?.openai||'NOT RUN'} · Anthropic: {council?.independent_classifications?.anthropic||'NOT RUN'} · Consensus: {council?.consensus?.classification||'HOLD_FOR_REVIEW'}.</p></div></div><div className="sectorList">{['Banking','IT','Auto','Pharma','FMCG'].map((name,i)=><div key={name}><span>{name}</span><div className="bar"><i style={{width:(86-i*13)+'%'}}/></div><b>—</b></div>)}</div></section>
      <section className="card"><div className="cardHead"><div><h3>Top Trading Candidates</h3><span>SCRAP-ranked observation set; no order instruction</span></div><button className="ghost" onClick={()=>setTab('screener')}>View All Candidates →</button></div>{loading?<div className="empty">Loading…</div>:top.length?<div className="candidateTable"><div className="thead"><span>#</span><span>Symbol</span><span>Price</span><span>Change</span><span>SCRAP</span><span>Setup</span><span>Action</span></div>{top.map((stock,i)=>{const row=scrapMap.get(stock.symbol)||{};return <div className="trow" key={stock.symbol}><span>{i+1}</span><b>{stock.symbol}</b><span>₹{Number(stock.price).toFixed(2)}</span><span className={Number(stock.change)>=0?'up':'down'}>{Number(stock.change)>=0?'+':''}{Number(stock.change).toFixed(2)}%</span><span>{Number.isFinite(Number(row.score))?row.score:'—'}</span><span>{row.status==='OK'?(row.action||'OBSERVE'):'Pending'}</span><span className={'tag '+(row.action==='REVIEW'?'pass':'hold')}>{row.action||'OBSERVE'}</span></div>})}</div>:<div className="empty"><AlertTriangle size={18}/>{(snapshot&&snapshot.reason)||'No market data available.'}</div>}</section>
    </div>
    <div className="dashGrid lower"><section className="card"><div className="cardHead"><div><h3>Strategy Council</h3><span>Five documented frameworks used as research factors, never stock-specific rules</span></div><button className="ghost" onClick={()=>setTab('strategies')}>Open Council →</button></div><StrategySummary stock={top[0]} live={live}/></section><section className="card"><div className="cardHead"><div><h3>System Health</h3><span>Connection and safety state</span></div><button className="ghost" onClick={()=>setTab('health')}>View Details →</button></div><HealthMini label="Market Data" value={snapshot?.source||'Waiting / unavailable'}/><HealthMini label="Telegram Notifications" value="Not configured"/><HealthMini label="OpenAI" value={council?.config?.openai?.api_key_configured?'Configured':'Not configured'}/><HealthMini label="Anthropic" value={council?.config?.anthropic?.api_key_configured?'Configured':'Not configured'}/><HealthMini label="Bot Engine" value={stop?'Stopped':'Running (Paper)'}/></section></div>
    <section className="eodStrip"><div><b>EOD Learning</b><span>Universe-wide missed-opportunity review</span></div><div className="eodStats"><b>{eod&&eod.profitable_moves||0}</b><span>profitable moves</span><b>{eod&&eod.missed_opportunities?eod.missed_opportunities.length:0}</b><span>misses</span><b>0</b><span>stock-specific rules</span></div><button className="ghost" onClick={()=>setTab('postmortem')}>View Audit →</button></section>
  </>;
}
function StrategySummary({stock,live}){if(!live||!stock)return <div className="empty"><Brain size={18}/> Strategy evidence is unavailable until a fresh market snapshot is available. Fundamental fields will never be invented.</div>;return <div className="strategyMini">{frameworkSummary(stock).map(item=><div key={item.id}><div><b>{item.name}</b><span>{item.focus}</span></div><strong className={item.status==='PASS'?'greenText':item.status==='PARTIAL'?'warnText':'mutedText'}>{item.status}</strong><small>{item.passed}/{item.total} checks • {item.evidenceCompleteness}% evidence</small></div>)}</div>}
function StrategyCouncil({stock,live}){const rows=live&&stock?frameworkSummary(stock):[];return <><PageTitle eyebrow="RESEARCH COUNCIL" title="Investment Strategy Council" text="Buffett, Jhunjhunwala, Lynch, 100 Baggers and CANSLIM are generalized research factors. They do not create stock-specific exceptions or bypass risk gates."/><section className="card"><div className="cardHead"><div><h3>Framework evidence</h3><span>{live&&stock?`Candidate: ${stock.symbol}`:'Waiting for a fresh validated market snapshot'}</span></div><span className="tag hold">NO HARD-CODED SCORES</span></div>{rows.length?<div className="strategyGrid">{rows.map(item=><div className="strategyCard" key={item.id}><div className="strategyTitle"><Brain size={19}/><div><b>{item.name}</b><span>{item.focus}</span></div><strong className={item.status==='PASS'?'greenText':item.status==='PARTIAL'?'warnText':'mutedText'}>{item.status}</strong></div><div className="strategyProgress"><i style={{width:item.evidenceCompleteness+'%'}}/></div><div className="strategyFacts"><span>Passed <b>{item.passed}</b></span><span>Evidence <b>{item.available}/{item.total}</b></span></div><div className="strategyChecks">{item.checks.map(check=><span key={check.name} className={check.state==='PASS'?'pass':check.state==='REVIEW'?'review':'missing'}>{check.name}: {check.state}</span>)}</div></div>)}</div>:<div className="empty"><AlertTriangle size={18}/> No strategy score is shown because the required source evidence is not available. This prevents fabricated fundamentals or misleading scores.</div>}</section><section className="card"><div className="callout"><ShieldCheck size={18}/><span>These frameworks are research inputs. The final decision remains subject to the OpenAI + Anthropic council and deterministic execution/risk gates. A profitable stock cannot create a permanent special rule.</span></div></section></>}
function MarketMetric({title,value,sub,icon:Icon}){return <div className="marketMetric"><div className="metricTop"><span>{title}</span>{Icon&&<Icon size={19}/>}</div><strong>{value}</strong><small>{sub}</small><div className="miniSpark"/></div>}
function StatusRow({name,value,blue,green,red,warn}){let cls=blue?'pillBlue':green?'greenText':red?'redText':warn?'warnText':'';return <div><span>{name}</span><b className={cls}>{value}</b></div>}
function Event({time,text}){return <div className="event"><span className="time">{time}</span><span>{text}</span></div>}
function HealthMini({label,value}){return <div className="healthMini"><span><i/> {label}</span><b>{value}</b></div>}

function PageTitle({eyebrow,title,text}){return <section className="dashTitle"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{text}</p></div></section>}
function Screener({stocks,scrap,status,search,setSearch}){const rows=(scrap&&scrap.stocks)||[];const map=new Map(rows.map(row=>[row.symbol,row]));return <><PageTitle eyebrow="RESEARCH" title="Stock Screener" text="Dynamic universe observation and SCRAP ranking. No hard-coded stock preference."/><div className="filterRow"><div className="searchBox"><Search size={17}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search symbol or sector..."/></div><button className="ghost">Filters</button><button className="ghost">Sort: SCRAP</button></div><section className="card"><div className="candidateTable wide"><div className="thead"><span>SYMBOL</span><span>SECTOR</span><span>PRICE</span><span>CHANGE</span><span>SCRAP</span><span>ACTION</span><span>STATUS</span></div>{!['LIVE_MARKET_DATA','LIVE_MARKET_DATA_NSE','LIVE_MARKET_DATA_NSE_PROXY','LIVE_MARKET_DATA_FALLBACK'].includes(status)?<div className="empty"><AlertTriangle size={18}/> Market data unavailable. Ranking is paused.</div>:stocks.map(stock=>{const row=map.get(stock.symbol)||{};return <div className="trow" key={stock.symbol}><b>{stock.symbol}</b><span>{stock.sector||'NSE Equity'}</span><span>₹{Number(stock.price).toFixed(2)}</span><span className={Number(stock.change)>=0?'up':'down'}>{Number(stock.change)>=0?'+':''}{Number(stock.change).toFixed(2)}%</span><span>{Number.isFinite(Number(row.score))?row.score:'—'}</span><span className={'tag '+(row.action==='REVIEW'?'pass':'hold')}>{row.action||'PENDING'}</span><span>{row.status||'WAITING'}</span></div>})}</div></section></>}
function Stock360({stock,scrap,status}){const row=(scrap&&scrap.stocks||[]).find(item=>item.symbol===stock?.symbol);if(!stock||!['LIVE_MARKET_DATA','LIVE_MARKET_DATA_NSE','LIVE_MARKET_DATA_NSE_PROXY','LIVE_MARKET_DATA_FALLBACK'].includes(status))return <EmptyPage title="Stock 360" text="A live market snapshot is required before a stock profile can be shown."/>;return <><PageTitle eyebrow="STOCK 360" title={stock.symbol} text="Complete evidence view. Calculated indicators appear only when their source data and formulas are available."/><div className="dashboardCards"><MarketMetric title="Price" value={'₹'+Number(stock.price).toFixed(2)} sub={(Number(stock.change)>=0?'+':'')+Number(stock.change).toFixed(2)+'% today'}/><MarketMetric title="SCRAP Score" value={row?.score??'—'} sub={row?.action||'Waiting for SCRAP'} icon={TrendingUp}/><MarketMetric title="ATR %" value={row?.indicators?.atr_pct!=null?row.indicators.atr_pct+'%':'—'} sub="Protection context" icon={ShieldCheck}/><MarketMetric title="Volume Ratio" value={row?.indicators?.volume_ratio_20!=null?row.indicators.volume_ratio_20+'x':'—'} sub="20-period average" icon={BarChart3}/></div><div className="dashGrid"><section className="card"><h3>OHLC Snapshot</h3><Facts values={[["Open",stock.open],["High",stock.high],["Low",stock.low],["Previous close",stock.prev_close]]}/></section><section className="card"><h3>SCRAP Technical Evidence</h3><Facts values={[["EMA 9",row?.indicators?.ema9],["EMA 20",row?.indicators?.ema20],["EMA 50",row?.indicators?.ema50],["RSI 14",row?.indicators?.rsi14],["ATR 14",row?.indicators?.atr14],["20D High",row?.indicators?.high20],["20D Low",row?.indicators?.low20],["Candle count",row?.candle_count]]}/></section></div><section className="card"><div className="cardHead"><div><h3>SCRAP Components</h3><span>Decision-time deterministic evidence</span></div><span className={'tag '+(row?.status==='OK'?'pass':'hold')}>{row?.status||'NOT RUN'}</span></div><div className="scrapComponents">{[['Structure','structure'],['Confirmation','confirmation'],['Relative Strength','relative_strength'],['Actionability','actionability'],['Protection','protection']].map(([label,key])=><div key={key}><span>{label}</span><b>{row?.components?.[key]??'—'}</b></div>)}</div><div className="callout"><ShieldCheck size={18}/><span>SCRAP is a research layer only. It cannot place orders, create stock-specific rules, or bypass the deterministic risk gates.</span></div></section></>}
function Facts({values}){return <div className="facts">{values.map(pair=><React.Fragment key={pair[0]}><span>{pair[0]}</span><b>{pair[1]??'—'}</b></React.Fragment>)}</div>}
function Regime({live,snapshot}){const regime=snapshot?.regime?.label||'UNAVAILABLE';return <><PageTitle eyebrow="MARKET CONTEXT" title="Market Regime" text="Regime is context for analysis, not a trade instruction."/><div className="dashboardCards"><MarketMetric title="Current Regime" value={regime} sub={live?'Validated snapshot context':'Awaiting validated data'} icon={TrendingUp}/><MarketMetric title="Confidence" value={snapshot?.regime?.confidence??'—'} sub="Source-dependent" icon={Gauge}/><MarketMetric title="Breadth" value={snapshot?.regime?.breadth??'—'} sub="Universe breadth" icon={BarChart3}/><MarketMetric title="Volatility" value={snapshot?.regime?.volatility??'—'} sub="Validated metric" icon={Activity}/></div><section className="card"><div className="aiBox"><Eye size={20}/><div><b>Regime safeguards</b><p>Regime can restrict or widen candidate analysis but cannot force a trade or override capital, liquidity, risk, or execution gates.</p></div></div></section></>}
function Scrap({live,count,scrap}){const rows=(scrap&&scrap.stocks)||[];const ok=rows.filter(row=>row.status==='OK');const review=ok.filter(row=>row.action==='REVIEW').length;const watch=ok.filter(row=>row.action==='WATCH').length;const avg=ok.length?Math.round(ok.reduce((sum,row)=>sum+Number(row.score||0),0)/ok.length*10)/10:null;return <><PageTitle eyebrow="SCRAP ANALYSIS" title="SCRAP Technical Analysis" text="Deterministic Structure, Confirmation, Relative Strength, Actionability and Protection evidence from Dhan historical candles."/><div className="dashboardCards"><MarketMetric title="SCRAP Status" value={scrap?.status||'NOT RUN'} sub={live?'Decision-time technical layer':'Waiting for fresh market data'} icon={Brain}/><MarketMetric title="Symbols Analysed" value={ok.length+'/'+count} sub="Validated technical rows" icon={BarChart3}/><MarketMetric title="Review Candidates" value={review} sub="Score ≥ 70" icon={Target}/><MarketMetric title="Average Score" value={avg??'—'} sub={watch+' watch candidates'} icon={Gauge}/></div><section className="card"><div className="cardHead"><div><h3>Technical Research Queue</h3><span>Same generalized calculation for every symbol</span></div><span className={'tag '+(live&&scrap?.status==='LIVE_TECHNICAL_DATA'?'pass':'hold')}>{live&&scrap?.status==='LIVE_TECHNICAL_DATA'?'READY':'WAITING'}</span></div>{rows.length?<div className="scrapTable"><div className="scrapHead"><span>SYMBOL</span><span>SCORE</span><span>STRUCTURE</span><span>CONFIRM</span><span>RELATIVE</span><span>ACTION</span><span>DATA</span></div>{rows.map(row=><div className="scrapRow" key={row.symbol}><b>{row.symbol}</b><strong>{row.score??'—'}</strong><span>{row.components?.structure??'—'}</span><span>{row.components?.confirmation??'—'}</span><span>{row.components?.relative_strength??'—'}</span><span className={'tag '+(row.action==='REVIEW'?'pass':'hold')}>{row.action||'—'}</span><span>{row.candle_count??0} candles</span></div>)}</div>:<div className="empty"><AlertTriangle size={18}/>{scrap?.reason||'SCRAP has not produced a technical dataset yet.'}</div>}</section><section className="card"><div className="cardHead"><div><h3>Protection & Integrity</h3><span>Safety constraints remain outside the technical score</span></div><span className="tag pass">STOCK-AGNOSTIC</span></div><div className="researchGrid scrapIntegrity"><Info title="No fabricated candles" text="Only Dhan historical candle responses are used."/><Info title="Decision-time only" text="No future candles are used in the calculation."/><Info title="No special rules" text="Every symbol uses the same formulas."/><Info title="No order authority" text="SCRAP cannot execute a broker order."/></div></section></>}
function Info({title,text}){return <div><b>{title}</b><span>{text}</span></div>}
function Paper({stop,paperState,showNotice}){const positions=paperState?.positions||{};return <><PageTitle eyebrow="EXECUTION" title="Paper Trading" text="Simulated execution only. No broker order is submitted from this application."/><div className="dashboardCards"><MarketMetric title="Mode" value="PAPER" sub="Live execution disabled" icon={CircleDollarSign}/><MarketMetric title="Paper Cash" value={paperState?`₹${Number(paperState.cash||0).toLocaleString('en-IN')}`:'—'} sub={paperState?.funds_check==='PASS'?'Funds gate passed internally':'Funds gate unavailable'} icon={Wallet}/><MarketMetric title="Realized P&L" value={paperState?`₹${Number(paperState.realized_pnl||0).toFixed(2)}`:'—'} sub={`${paperState?.trade_count||0} paper events`} icon={Activity}/><MarketMetric title="Positions" value={Object.keys(positions).length} sub="Open paper positions" icon={FileText}/></div><section className="card"><div className="cardHead"><h3>Execution Console</h3><span>{stop?'EMERGENCY STOP ACTIVE':'SAFE PAPER MODE'}</span></div><div className="callout green"><ShieldCheck size={18}/><span>Funds are checked internally before a paper entry. No share-price ceiling is used; insufficient capital simply produces an auditable skip.</span></div>{Object.keys(positions).length?<div className="positionList">{Object.entries(positions).map(([symbol,pos])=><div className="healthRow" key={symbol}><div><b>{symbol}</b><span>{pos.quantity} share(s) @ ₹{Number(pos.entry_price).toFixed(2)}</span></div><b>Target ₹{Number(pos.target_price).toFixed(2)}</b></div>)}</div>:<div className="empty">No open paper positions yet. The scheduled engine will evaluate candidates during market hours.</div>}<button className="primary" onClick={()=>showNotice('Use the scheduled 5-minute paper engine or open GitHub Actions for a manual cycle. This browser cannot directly authenticate to GitHub Actions.')}>How a Paper Cycle Runs</button></section></>}
function Baskets(){return <><PageTitle eyebrow="THEMATIC BASKETS" title="Thematic Baskets" text="Themes are informational and cannot force a stock into the candidate set."/><div className="researchGrid baskets">{['Banking','IT','Auto','Pharma','FMCG','Energy'].map(name=><div key={name}><b>{name}</b><span>Awaiting validated sector data</span><em>—</em></div>)}</div></>}
function PostMortem({report}){const misses=report&&report.missed_opportunities||[];return <><PageTitle eyebrow="POST-MORTEM" title="EOD Reverse Engineering" text="Find profitable opportunities the bot missed and identify general causes using decision-time evidence."/><div className="dashboardCards"><MarketMetric title="Profitable Moves" value={report&&report.profitable_moves||0} sub="Eligible universe" icon={TrendingUp}/><MarketMetric title="Misses" value={misses.length} sub="Require evidence" icon={AlertTriangle}/><MarketMetric title="General Patterns" value={report&&report.general_patterns?report.general_patterns.length:0} sub="Cross-symbol evidence" icon={Brain}/><MarketMetric title="Stock Rules" value="0" sub="Hard requirement" icon={ShieldCheck}/></div><section className="card"><div className="cardHead"><h3>Miss Analysis</h3><span className="tag pass">STOCK-AGNOSTIC</span></div>{misses.length?misses.map((m,i)=><div className="miss" key={i}><div><b>{m.symbol}</b><span>{m.reason||'Decision-time review'}</span></div><strong>{m.outcome||'—'}</strong><span>{m.classification||'Pending classification'}</span></div>):<div className="empty"><History size={18}/>{report&&report.message||'No completed EOD report is available yet.'}</div>}<div className="callout"><Brain size={18}/><span>A single profitable stock can never create a special rule. Any optimization must generalize across symbols and sessions and pass validation.</span></div></section></>}
function Supervisor({live,paper}){const rows=[['Market data',live,'Dhan snapshot'],['Paper mode',paper,'Required'],['Live orders',false,'Hard locked'],['AI council',true,'OpenAI + Anthropic staged'],['Stock-specific rules',false,'Prohibited']];return <><PageTitle eyebrow="SUPERVISOR" title="Bot Supervisor" text="Central orchestration state and safety gates."/><div className="supervisorGrid">{rows.map(row=><div className="superCard" key={row[0]}><span>{row[0]}</span><b className={row[1]?'greenText':'redText'}>{row[1]?'PASS':'BLOCKED'}</b><small>{row[2]}</small></div>)}</div></>}
function Health({snapshot,eod,paper,scrap,council}){const live=snapshot&&['LIVE_MARKET_DATA','LIVE_MARKET_DATA_NSE','LIVE_MARKET_DATA_NSE_PROXY','LIVE_MARKET_DATA_FALLBACK'].includes(snapshot.status);const scrapReady=scrap&&scrap.status==='LIVE_TECHNICAL_DATA';const rows=[['Market data',live?'READY':'WAITING',snapshot?.source||'Market snapshot'],['SCRAP technical layer',scrapReady?'READY':'WAITING','Deterministic indicators'],['Telegram','NOT CONFIGURED','Optional notifications'],['OpenAI',council?.config?.openai?.api_key_configured?'CONFIGURED':'NOT CONFIGURED',council?.status||'Council'],['Anthropic',council?.config?.anthropic?.api_key_configured?'CONFIGURED':'NOT CONFIGURED',council?.status||'Council'],['Paper engine',paper?'READY':'BLOCKED','Simulation only'],['EOD ledger',eod&&eod.status==='READY'?'READY':'WAITING','Decision-time evidence'],['Live orders','DISABLED','Safety gate']];return <><PageTitle eyebrow="OPERATIONS" title="System Health" text="Truthful state of the paper-trading platform."/><section className="card">{rows.map(row=><div className="healthRow" key={row[0]}><div><b>{row[0]}</b><span>{row[2]}</span></div><span className={row[1]==='READY'?'health ready':'health blocked'}><i/>{row[1]}</span></div>)}</section></>}
function SettingsPage({paper,setPaper}){return <><PageTitle eyebrow="CONFIGURATION" title="Settings" text="Safety-first configuration for paper validation."/><section className="settingsGrid"><Setting title="Paper Trading" text="Required for current development phase" control={<button className={paper?'toggle on':'toggle'} onClick={()=>setPaper(!paper)}><i/></button>}/><Setting title="Live Trading" text="Locked until paper validation is complete" control={<button className="toggle disabled"><i/></button>}/><Setting title="OpenAI Research Council" text="Independent analysis + cross-review" control={<span className="tag hold">STAGED</span>}/><Setting title="Anthropic Research Council" text="Independent analysis + cross-review" control={<span className="tag hold">STAGED</span>}/><Setting title="Dhan API Key" text="Not required for the current access-token stage" control={<span className="tag hold">OPTIONAL</span>}/></section></>}
function Setting({title,text,control}){return <div className="setting"><div><b>{title}</b><span>{text}</span></div>{control}</div>}
function Locked({title,text}){return <><PageTitle eyebrow="LIVE EXECUTION" title={title} text={text}/><section className="locked"><ShieldCheck size={42}/><h3>LIVE TRADING DISABLED</h3><p>Dhan credentials do not enable live orders by themselves. Paper validation is required first.</p></section></>}
function EmptyPage({title,text}){return <><PageTitle eyebrow="PENDING INTEGRATION" title={title} text={text}/><section className="card"><div className="empty"><AlertTriangle size={18}/>{text}</div></section></>}
