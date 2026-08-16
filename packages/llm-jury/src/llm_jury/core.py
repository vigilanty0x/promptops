import statistics
def judge(scores,*,pass_score=0.7,max_spread=0.35):
    if not 2<=len(scores)<=100: raise ValueError("jury requires 2-100 scores")
    values=[float(x) for x in scores]
    if any(x<0 or x>1 for x in values): raise ValueError("scores must be 0..1")
    median=statistics.median(values); spread=max(values)-min(values)
    decision="blocked" if spread>max_spread else ("pass" if median>=pass_score else "fail")
    return {"decision":decision,"median":median,"spread":spread,"jurors":len(values)}
def run(data): return judge(**data)

