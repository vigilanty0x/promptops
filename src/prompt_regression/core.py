import json
def compare(cases):
    if not 1<=len(cases)<=10000: raise ValueError("bounded cases required")
    results=[]
    for case in cases:
        mode=case.get("mode","exact"); old,new=case["baseline"],case["candidate"]
        if mode=="exact": before=old==case["expected"]; after=new==case["expected"]
        elif mode=="contains": before=case["expected"] in old; after=case["expected"] in new
        elif mode=="json": before=json.loads(old)==case["expected"]; after=json.loads(new)==case["expected"]
        else: raise ValueError("unknown mode")
        status="regression" if before and not after else ("improvement" if after and not before else "unchanged")
        results.append({"id":case["id"],"status":status})
    return {"results":results,"regressions":sum(r["status"]=="regression" for r in results)}
def run(data): return compare(**data)

