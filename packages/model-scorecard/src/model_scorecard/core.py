def score(models,*,max_latency_ms=5000,max_cost=1):
    if not 1<=len(models)<=1000: raise ValueError("bounded models required")
    rows=[]
    for model in models:
        runs=model["runs"]
        if not runs: raise ValueError("runs required")
        pass_rate=sum(bool(r["passed"]) for r in runs)/len(runs)
        latency=sum(r["latency_ms"] for r in runs)/len(runs); cost=sum(r["cost"] for r in runs)
        eligible=latency<=max_latency_ms and cost<=max_cost
        rows.append({"model":model["model"],"pass_rate":pass_rate,"latency_ms":latency,"cost":cost,"eligible":eligible})
    rows.sort(key=lambda r:(not r["eligible"],-r["pass_rate"],r["cost"],r["latency_ms"],r["model"]))
    return {"scorecards":rows,"winner":rows[0]["model"] if rows[0]["eligible"] else None}
def run(data): return score(**data)

