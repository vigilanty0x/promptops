import hashlib,json
def build(items,*,test_percent=20):
    if not 1<=len(items)<=10000 or not 1<=test_percent<=99: raise ValueError("bounded dataset required")
    seen=set(); rows=[]
    for item in items:
        if set(item)!={"input","expected"}: raise ValueError("invalid item")
        key=hashlib.sha256(json.dumps(item,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        if key in seen: continue
        seen.add(key); rows.append({"id":key,**item,"split":"test" if int(key[:8],16)%100<test_percent else "train"})
    rows.sort(key=lambda x:x["id"])
    return {"items":rows,"count":len(rows),"sha256":hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}
def run(data): return build(**data)

