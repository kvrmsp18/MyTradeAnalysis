#!/usr/bin/env python3
"""Validate Dhan authentication without printing credentials."""
from __future__ import annotations
import json, os, urllib.request, urllib.error

def main():
    token=(os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
    client=(os.getenv("DHAN_CLIENT_ID") or "").strip()
    if not token or not client:
        print("DHAN_AUTH_STATUS=NOT_CONFIGURED")
        return 0
    req=urllib.request.Request(
        "https://api.dhan.co/v2/fundlimit",
        headers={"access-token":token,"client-id":client,"Accept":"application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            body=r.read().decode("utf-8","replace")
            print(f"DHAN_AUTH_STATUS=HTTP_{r.status}")
            try:
                data=json.loads(body)
                if isinstance(data,dict):
                    print("DHAN_RESPONSE_KEYS="+",".join(sorted(str(k) for k in data.keys())))
            except Exception:
                pass
    except urllib.error.HTTPError as exc:
        print(f"DHAN_AUTH_STATUS=HTTP_{exc.code}")
        body=exc.read().decode("utf-8","replace").strip()
        if body:
            try:
                data=json.loads(body)
                if isinstance(data,dict):
                    safe={k:v for k,v in data.items() if "token" not in str(k).lower() and "secret" not in str(k).lower()}
                    print("DHAN_ERROR_RESPONSE="+json.dumps(safe, separators=(",",":"))[:1000])
                else:
                    print("DHAN_ERROR_RESPONSE=NON_OBJECT")
            except Exception:
                print("DHAN_ERROR_RESPONSE=NON_JSON")
    except Exception as exc:
        print("DHAN_AUTH_STATUS=ERROR")
        print("DHAN_ERROR_TYPE="+type(exc).__name__)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
