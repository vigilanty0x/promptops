import difflib,re
def compare(baseline,candidate):
    def tokens(x): return re.findall(r"\w+|[^\w\s]",x.casefold())
    a,b=tokens(baseline),tokens(candidate)
    matcher=difflib.SequenceMatcher(a=a,b=b,autojunk=False)
    ops=[{"tag":tag,"baseline":a[i1:i2],"candidate":b[j1:j2]} for tag,i1,i2,j1,j2 in matcher.get_opcodes()]
    return {"equal":a==b,"similarity":matcher.ratio(),"operations":ops,"baseline_tokens":len(a),"candidate_tokens":len(b)}
def run(data): return compare(**data)

