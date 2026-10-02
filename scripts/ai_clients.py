"""Shared, provider-agnostic AI client helpers for MyTradeAnalysis."""
from __future__ import annotations
import json, os, re, time, urllib.error, urllib.request

CLASSIFICATIONS={"SUPPORTS_REVIEW","WATCH_ONLY","NO_SUPPORT"}

def extract_openai_text(payload):
    return "\n".join(
        c.get("text","") for item in payload.get("output",[])
        if isinstance(item,dict) for c in item.get("content",[])
        if isinstance(c,dict) and c.get("type") in ("output_text","text") and c.get("text")
    ).strip()

def extract_anthropic_text(payload):
    return "\n".join(
        item.get("text","") for item in payload.get("content",[])
        if isinstance(item,dict) and item.get("type")=="text" and item.get("text")
    ).strip()

def development_classification(text):
    match=re.search(r"(?im)^\s*DEVELOPMENT_CLASSIFICATION\s*:\s*(PASS|CHANGES_REQUIRED)\s*$", text or "")
    return match.group(1).upper() if match else None

def classify(text):
    # Accept Claude/OpenAI formatting such as:
    # CLASSIFICATION:, # CLASSIFICATION:, **CLASSIFICATION:**, or "- CLASSIFICATION:".
    match=re.search(
        r"(?im)^\s*(?:\*\*|[-#>]\s*|\*\s*)?CLASSIFICATION(?:\s*\*\*)?\s*:\s*(?:\*\*)?\s*"
        r"(SUPPORTS_REVIEW|WATCH_ONLY|NO_SUPPORT)\b", text or ""
    )
    return match.group(1).upper() if match else None

def request_json(url, headers, payload, provider, *, retries=3, timeout=90):
    body=json.dumps(payload).encode("utf-8")
    last_error=None
    for attempt in range(1,retries+1):
        req=urllib.request.Request(url,data=body,headers={**headers,"Content-Type":"application/json"},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail=exc.read().decode("utf-8",errors="replace")[:4000]
            last_error=f"{provider} HTTP {exc.code}: {detail}"
            retryable=exc.code==429 or 500<=exc.code<600
            if not retryable or attempt==retries: break
            retry_after=exc.headers.get("Retry-After")
            try: delay=max(1,min(60,int(float(retry_after)))) if retry_after else 10*attempt
            except (TypeError,ValueError): delay=10*attempt
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error=f"{provider} transport error: {exc}"
            if attempt==retries: break
            time.sleep(10*attempt)
    raise RuntimeError(last_error or f"{provider} request failed")

def call_openai(system_prompt, evidence, *, max_output_tokens=3000):
    key=os.getenv("OPENAI_API_KEY"); model=os.getenv("OPENAI_MODEL")
    if not key or not model: return "", "OpenAI not configured."
    payload={"model":model,"input":[
        {"role":"system","content":[{"type":"input_text","text":system_prompt}]},
        {"role":"user","content":[{"type":"input_text","text":"<evidence>\n"+json.dumps(evidence,sort_keys=True)+"\n</evidence>"}]}
    ],"max_output_tokens":max_output_tokens,"store":False}
    try:
        text=extract_openai_text(request_json("https://api.openai.com/v1/responses",{"Authorization":"Bearer "+key},payload,"OpenAI"))
        return (text,None) if text else ("","OpenAI returned no text.")
    except Exception as exc: return "",str(exc)

def call_anthropic(system_prompt, evidence, *, max_output_tokens=3000):
    key=os.getenv("ANTHROPIC_API_KEY"); model=os.getenv("ANTHROPIC_MODEL")
    if not key or not model: return "", "Anthropic not configured."
    payload={"model":model,"max_tokens":max_output_tokens,"system":system_prompt,
             "messages":[{"role":"user","content":"<evidence>\n"+json.dumps(evidence,sort_keys=True)+"\n</evidence>"}]}
    try:
        text=extract_anthropic_text(request_json("https://api.anthropic.com/v1/messages",{"x-api-key":key,"anthropic-version":"2023-06-01"},payload,"Anthropic"))
        return (text,None) if text else ("","Anthropic returned no text.")
    except Exception as exc: return "",str(exc)


def resolve_advisory(openai_text, anthropic_text):
    """Pure runtime policy helper used by tests and the research council."""
    oc, ac = classify(openai_text), classify(anthropic_text)
    available = [x for x in (("OpenAI", openai_text, oc), ("Anthropic", anthropic_text, ac)) if x[1]]
    if not available:
        return {"status":"AI_UNAVAILABLE","classification":None,"working_provider":None}
    if len(available)==1:
        name, _, cls = available[0]
        return {"status":"DEGRADED_ONE_AI","classification":cls,"working_provider":name}
    if oc and ac and oc==ac:
        return {"status":"COMPLETE","classification":oc,"working_provider":"OpenAI + Anthropic"}
    if oc and ac:
        return {"status":"DISAGREEMENT","classification":"HOLD_FOR_REVIEW","working_provider":None}
    return {"status":"DEGRADED_UNCLASSIFIED","classification":None,"working_provider":None}
