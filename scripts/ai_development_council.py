#!/usr/bin/env python3
from pathlib import Path
import json, os, subprocess, urllib.request

REPORT=Path('artifacts/ai-development-council.md')

def cmd(*args):
    return subprocess.run(args,check=False,capture_output=True,text=True).stdout

def post(url,headers,payload):
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={**headers,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=90) as r:
        return json.loads(r.read().decode())

def oa(prompt):
    x=post('https://api.openai.com/v1/responses',{'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},{'model':os.environ['OPENAI_MODEL'],'input':prompt,'store':False})
    return '\n'.join(p.get('text','') for i in x.get('output',[]) for p in i.get('content',[]) if p.get('type')=='output_text').strip()

def an(prompt):
    x=post('https://api.anthropic.com/v1/messages',{'x-api-key':os.environ['ANTHROPIC_API_KEY'],'anthropic-version':'2023-06-01'},{'model':os.environ['ANTHROPIC_MODEL'],'max_tokens':3000,'messages':[{'role':'user','content':prompt}]})
    return '\n'.join(p.get('text','') for p in x.get('content',[]) if p.get('type')=='text').strip()

def main():
    required=['OPENAI_API_KEY','ANTHROPIC_API_KEY','OPENAI_MODEL','ANTHROPIC_MODEL']
    missing=[x for x in required if not os.environ.get(x)]
    if missing: raise SystemExit('AI DEVELOPMENT COUNCIL BLOCKED: missing '+', '.join(missing))
    diff=cmd('git','diff','HEAD^','HEAD') or cmd('git','show','--format=','HEAD')
    log=Path('artifacts/build.log').read_text(encoding='utf-8',errors='replace') if Path('artifacts/build.log').exists() else 'No build log.'
    evidence='COMMIT: '+cmd('git','rev-parse','HEAD')+'\n\nCHANGED CODE:\n'+diff[-60000:]+'\n\nBUILD LOG:\n'+log[-30000:]
    prompt='''You are a mandatory software-development reviewer for MyTradeAnalysis. Review the supplied code diff and build output for correctness, runtime behavior, security, paper-only safety, data integrity, AI integration, and maintainability. Do not invent evidence. Start with DEVELOPMENT_CLASSIFICATION: PASS or DEVELOPMENT_CLASSIFICATION: CHANGES_REQUIRED. Then list concrete defects, root causes, complete-file changes required, and tests required. This is software review, not trading advice.\n\n'''+evidence
    openai=oa(prompt)
    anthropic=an(prompt)
    critique='''Compare the peer software review against the same evidence. Identify missed defects, unsupported claims, and unsafe assumptions. Start with PEER_REVIEW: ACCEPT or PEER_REVIEW: CHALLENGE.\n\n'''+evidence
    oa_peer=oa(critique+'\n\nANTHROPIC REVIEW:\n'+anthropic)
    an_peer=an(critique+'\n\nOPENAI REVIEW:\n'+openai)
    synthesis=oa('''Chair the MyTradeAnalysis development council. Synthesize both independent reviews and critiques. PASS only if no concrete unresolved correctness, build, safety, data-integrity, or integration defect remains. Otherwise CHANGES_REQUIRED. Do not claim code was changed or tested unless evidence proves it.\n\nEVIDENCE:\n'''+evidence+'\n\nOPENAI:\n'+openai+'\n\nANTHROPIC:\n'+anthropic+'\n\nOPENAI CRITIQUE:\n'+oa_peer+'\n\nANTHROPIC CRITIQUE:\n'+an_peer)
    report='# AI Development Council\n\nCommit: `'+cmd('git','rev-parse','HEAD').strip()+'`\n\n## Participants\nOpenAI: completed\nAnthropic: completed\nCross-critique: completed\n\n## OpenAI\n\n'+openai+'\n\n## Anthropic\n\n'+anthropic+'\n\n## OpenAI critique\n\n'+oa_peer+'\n\n## Anthropic critique\n\n'+an_peer+'\n\n## Council synthesis\n\n'+synthesis+'\n\nLive broker execution remains disabled. Deterministic safety gates remain authoritative.\n'
    REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(report,encoding='utf-8'); print(report)

if __name__=='__main__': main()