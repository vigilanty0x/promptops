from collections import defaultdict
def decide(votes,*,quorum=2,threshold=0.6):
    if not 1<=len(votes)<=1000: raise ValueError("bounded votes required")
    totals=defaultdict(float); participating=0.0
    for vote in votes:
        choice=vote["choice"]; weight=float(vote.get("weight",1))
        if weight<=0 or weight>100: raise ValueError("invalid weight")
        if choice!="abstain": totals[choice]+=weight; participating+=weight
    if len(votes)<quorum or participating==0: return {"decision":"blocked","reason":"quorum"}
    ordered=sorted(totals.items(),key=lambda x:(-x[1],x[0]))
    if len(ordered)>1 and ordered[0][1]==ordered[1][1]: return {"decision":"blocked","reason":"split"}
    share=ordered[0][1]/participating
    return {"decision":"accepted" if share>=threshold else "blocked","choice":ordered[0][0],"share":share}
def run(data): return decide(**data)

