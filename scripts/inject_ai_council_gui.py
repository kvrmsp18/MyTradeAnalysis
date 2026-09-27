from pathlib import Path

path = Path('src/App.jsx')
text = path.read_text(encoding='utf-8')

text = text.replace("const SCRAP='/MyTradeAnalysis/data/scrap_analysis.json';", "const SCRAP='/MyTradeAnalysis/data/scrap_analysis.json';\nconst COUNCIL='/MyTradeAnalysis/data/ai_research_council.json';")
text = text.replace("  const [scrap,setScrap]=useState(null);\n  const [notice,setNotice]=useState('');", "  const [scrap,setScrap]=useState(null);\n  const [council,setCouncil]=useState(null);\n  const [notice,setNotice]=useState('');")
text = text.replace("const responses=await Promise.all([fetch(DATA+'?t='+Date.now()),fetch(EOD+'?t='+Date.now()),fetch(SCRAP+'?t='+Date.now())]);\n      const nextSnapshot=await responses[0].json();\n      const nextEod=await responses[1].json();\n      const nextScrap=await responses[2].json();", "const responses=await Promise.all([fetch(DATA+'?t='+Date.now()),fetch(EOD+'?t='+Date.now()),fetch(SCRAP+'?t='+Date.now()),fetch(COUNCIL+'?t='+Date.now())]);\n      const nextSnapshot=await responses[0].json();\n      const nextEod=await responses[1].json();\n      const nextScrap=await responses[2].json();\n      const nextCouncil=await responses[3].json();")
text = text.replace("      setScrap(nextScrap);\n    }catch(error){", "      setScrap(nextScrap);\n      setCouncil(nextCouncil);\n    }catch(error){")
text = text.replace("      setScrap({status:'NOT_RUN',stocks:[],stock_specific_rule_created:false,reason:'SCRAP data could not be loaded.'});", "      setScrap({status:'NOT_RUN',stocks:[],stock_specific_rule_created:false,reason:'SCRAP data could not be loaded.'});\n      setCouncil({status:'NOT_RUN',consensus:'NOT_RUN',openai:{status:'NOT_RUN'},anthropic:{status:'NOT_RUN'},reason:'AI council data could not be loaded.'});")
text = text.replace("return <Dashboard snapshot={snapshot} eod={eod} scrap={scrap} loading={loading} stop={stop} paper={paper} setTab={setTab} runCycle={runCycle} market={market}/>;", "return <Dashboard snapshot={snapshot} eod={eod} scrap={scrap} council={council} loading={loading} stop={stop} paper={paper} setTab={setTab} runCycle={runCycle} market={market}/>;")
text = text.replace("if(tab==='strategies')return <StrategyCouncil stock={filtered[0]||stocks[0]} live={market.live}/>;", "if(tab==='strategies')return <StrategyCouncil stock={filtered[0]||stocks[0]} live={market.live} council={council}/>;")
text = text.replace("if(tab==='health')return <Health snapshot={snapshot} eod={eod} paper={paper} scrap={scrap}/>;", "if(tab==='health')return <Health snapshot={snapshot} eod={eod} paper={paper} scrap={scrap} council={council}/>;")
text = text.replace("function Dashboard({snapshot,eod,scrap,loading,stop,paper,setTab,runCycle,market}){", "function Dashboard({snapshot,eod,scrap,council,loading,stop,paper,setTab,runCycle,market}){")
old = "<div className=\"aiBox\"><Brain size={22}/><div><b>Independent analysis → cross-critique → synthesis</b><p>Both models receive the same decision-time evidence. They cannot bypass deterministic capital, liquidity, risk, market-data or duplicate-order gates.</p></div></div>"
new = "<CouncilMini council={council}/><div className=\"aiBox\"><Brain size={22}/><div><b>Independent analysis → cross-critique → consensus</b><p>Both models receive the same decision-time evidence. AI remains advisory and cannot bypass deterministic capital, liquidity, risk, market-data or duplicate-order gates.</p></div></div>"
text = text.replace(old, new)
text = text.replace("<HealthMini label=\"OpenAI\" value=\"Staged / key not configured\"/><HealthMini label=\"Anthropic\" value=\"Staged / key not configured\"/>", "<HealthMini label=\"OpenAI\" value={councilModelLabel(council?.openai)}/><HealthMini label=\"Anthropic\" value={councilModelLabel(council?.anthropic)}/>")
text = text.replace("function StrategyCouncil({stock,live}){", "function StrategyCouncil({stock,live,council}){")
anchor = "function StrategyCouncil({stock,live,council}){const rows=live&&stock?frameworkSummary(stock):[];"
replacement = anchor + ""
text = text.replace(anchor, replacement)
old_end = "</section><section className=\"card\"><div className=\"callout\"><ShieldCheck size={18}/><span>These frameworks are research inputs. The final decision remains subject to the OpenAI + Anthropic council and deterministic execution/risk gates. A profitable stock cannot create a permanent special rule.</span></div></section></>}"
new_end = "</section><section className=\"card\"><CouncilMini council={council}/><div className=\"callout\"><ShieldCheck size={18}/><span>These frameworks are research inputs. The final decision remains subject to the OpenAI + Anthropic council and deterministic execution/risk gates. A profitable stock cannot create a permanent special rule.</span></div></section></>}"
text = text.replace(old_end, new_end)

text = text.replace("function Health({snapshot,eod,paper,scrap}){", "function Health({snapshot,eod,paper,scrap,council}){")
text = text.replace("['OpenAI','STAGED','Key not configured'],['Anthropic','STAGED','Key not configured'],", "['OpenAI',councilModelLabel(council?.openai),'Council result'],['Anthropic',councilModelLabel(council?.anthropic),'Council result'],")

insert_before = "function HealthMini({label,value}){return <div className=\"healthMini\"><span><i/> {label}</span><b>{value}</b></div>}"
helpers = """function councilModelLabel(model){\n  if(!model)return 'NOT RUN';\n  const status=String(model.status||'').toUpperCase();\n  if(status==='OK'||status==='COMPLETED'||status==='READY')return 'ANALYSED';\n  if(status==='ERROR'||status==='FAILED')return 'ERROR';\n  return status||'NOT RUN';\n}\nfunction councilConsensus(council){\n  const value=String(council?.consensus||council?.final_consensus||council?.decision||'NOT_RUN').toUpperCase();\n  if(value.includes('DISAGREE')||value.includes('HOLD'))return 'HOLD FOR REVIEW';\n  if(value.includes('SUPPORT'))return 'SUPPORTS REVIEW';\n  if(value.includes('WATCH'))return 'WATCH ONLY';\n  if(value.includes('NO_SUPPORT'))return 'NO SUPPORT';\n  return value==='NOT_RUN'?'NOT RUN':value;\n}\nfunction CouncilMini({council}){\n  const oa=councilModelLabel(council?.openai);\n  const cl=councilModelLabel(council?.anthropic);\n  const consensus=councilConsensus(council);\n  const tone=consensus==='SUPPORTS REVIEW'?'pass':consensus==='HOLD FOR REVIEW'?'review':'hold';\n  return <div className=\"councilMini\"><div><span>OpenAI</span><b>{oa}</b></div><div><span>Claude</span><b>{cl}</b></div><div><span>Consensus</span><strong className={'tag '+tone}>{consensus}</strong></div></div>\n}\n""" + insert_before
text = text.replace(insert_before, helpers)

if "COUNCIL='/MyTradeAnalysis/data/ai_research_council.json'" not in text:
    raise SystemExit('AI council data constant was not injected')
if "function CouncilMini" not in text:
    raise SystemExit('CouncilMini was not injected')
if "council={council}" not in text:
    raise SystemExit('Council prop wiring was not injected')

path.write_text(text, encoding='utf-8')
print('AI council GUI injection completed')
