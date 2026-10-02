#!/usr/bin/env python3
"""Provider-agnostic software-development review council."""
from pathlib import Path
import os, subprocess
from ai_clients import call_anthropic,call_openai,development_classification

REPORT=Path("artifacts/ai-development-council.md")
def cmd(*args): return subprocess.run(args,check=False,capture_output=True,text=True).stdout
def review_text(text):
    return development_classification(text) == "PASS"

def main():
    configured=[]
    if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"): configured.append("OpenAI")
    if os.getenv("ANTHROPIC_API_KEY") and os.getenv("ANTHROPIC_MODEL"): configured.append("Anthropic")
    if not configured:
        REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text("# AI Development Council\n\nBLOCKED - no AI provider is configured.\n",encoding="utf-8"); raise SystemExit(1)

    base=os.getenv("GITHUB_EVENT_BEFORE")
    head=os.getenv("GITHUB_SHA") or cmd("git","rev-parse","HEAD").strip()
    if not base or set(base)=={"0"}: base=cmd("git","rev-parse","HEAD^").strip()
    diff=cmd("git","diff",base,head,"--","."," :(exclude)data/**"," :(exclude)public/data/**"," :(exclude)package-lock.json")
    if not diff.strip(): diff=cmd("git","show","--format=",head)
    log=Path("artifacts/build.log").read_text(encoding="utf-8",errors="replace") if Path("artifacts/build.log").exists() else "No build log."
    evidence="BASE: "+base+"\nHEAD: "+head+"\n\nCHANGED CODE:\n"+diff[-80000:]+"\n\nBUILD LOG:\n"+log[-30000:]
    prompt=("You are a mandatory software-development reviewer for MyTradeAnalysis. "
            "Review the supplied code diff and build output for correctness, runtime behavior, security, "
            "paper-only safety, data integrity, AI integration and maintainability. Do not invent evidence. "
            "The final line must be exactly DEVELOPMENT_CLASSIFICATION: PASS or DEVELOPMENT_CLASSIFICATION: CHANGES_REQUIRED. "
            "Do not use either phrase elsewhere. This is software review, not trading advice.")
    ov,oe=call_openai(prompt,{"text":evidence},max_output_tokens=6000)
    av,ae=call_anthropic(prompt,{"text":evidence},max_output_tokens=6000)

    if not ov and not av:
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text("# AI Development Council\n\nBLOCKED - both configured providers unavailable.\n\nOpenAI: "+str(oe)+"\n\nAnthropic: "+str(ae),encoding="utf-8")
        raise SystemExit(1)

    if bool(ov)!=bool(av):
        working=ov or av; provider="OpenAI" if ov else "Anthropic"; classification=development_classification(working)
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text("# AI Development Council\n\nMode: DEGRADED_SINGLE_AI\nWorking provider: "+provider+
                           "\nUnavailable provider: "+("Anthropic" if ov else "OpenAI")+
                           "\n\n## Working review\n\n"+working+
                           "\n\nExplicit classification: "+str(classification)+
                           "\n\nUnavailable provider error: "+str(ae if ov else oe),encoding="utf-8")
        print(REPORT.read_text(encoding="utf-8"))
        if classification!="PASS": raise SystemExit("AI DEVELOPMENT COUNCIL: explicit PASS required")
        return 0

    critique=("Challenge this peer software review against the supplied evidence. Identify missed defects and unsupported claims. "
              "End with PEER_REVIEW: ACCEPT or PEER_REVIEW: CHALLENGE.")
    oc,oce=call_openai(critique+"\n\nANTHROPIC REVIEW:\n"+av,{"text":evidence},max_output_tokens=6000)
    ac,ace=call_anthropic(critique+"\n\nOPENAI REVIEW:\n"+ov,{"text":evidence},max_output_tokens=6000)
    synthesis_prompt=("Synthesize the two reviews and critiques. PASS only when no concrete unresolved correctness, build, "
                       "safety, data-integrity or integration defect remains. End with exactly "
                       "DEVELOPMENT_CLASSIFICATION: PASS or DEVELOPMENT_CLASSIFICATION: CHANGES_REQUIRED.")
    osyn,ose=call_openai(synthesis_prompt,{"evidence":evidence,"openai":ov,"anthropic":av,"openai_critique":oc,"anthropic_critique":ac},max_output_tokens=6000)
    asyn,ase=call_anthropic(synthesis_prompt,{"evidence":evidence,"openai":ov,"anthropic":av,"openai_critique":oc,"anthropic_critique":ac},max_output_tokens=6000)
    ocf,acf=development_classification(osyn),development_classification(asyn)
    if ocf and acf and ocf==acf: final=ocf
    elif ocf and not acf: final=ocf
    elif acf and not ocf: final=acf
    else: final="CHANGES_REQUIRED"

    report="# AI Development Council\n\nBASE: "+base+"\nHEAD: "+head+"\n\n"
    report+="## OpenAI review\n\n"+ov+"\n\n## Anthropic review\n\n"+av
    report+="\n\n## OpenAI critique\n\n"+oc+"\n\n## Anthropic critique\n\n"+ac
    report+="\n\n## OpenAI synthesis\n\n"+(osyn or "UNAVAILABLE")
    report+="\n\n## Anthropic synthesis\n\n"+(asyn or "UNAVAILABLE")
    report+="\n\nFINAL DEVELOPMENT CLASSIFICATION: "+final
    report+="\n\nLive broker execution remains disabled. Deterministic safety gates remain authoritative.\n"
    REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(report,encoding="utf-8"); print(report)
    if final!="PASS": raise SystemExit("AI DEVELOPMENT COUNCIL: CHANGES_REQUIRED")
if __name__=="__main__": main()
