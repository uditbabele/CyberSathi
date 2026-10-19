
from collections import defaultdict
from datetime import timezone
import hashlib, json
import networkx as nx
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session
from .models import Transaction, Complaint

def utc_iso(dt):
    if dt.tzinfo is None: return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()

def tx_records(db: Session, start=None, end=None):
    q = db.query(Transaction)
    if start: q = q.filter(Transaction.timestamp >= pd.to_datetime(start, utc=True).to_pydatetime())
    if end: q = q.filter(Transaction.timestamp <= pd.to_datetime(end, utc=True).to_pydatetime())
    rows = q.order_by(Transaction.timestamp.asc()).all()
    return [{"transaction_id":r.transaction_id,"source":r.source,"target":r.target,
             "amount":float(r.amount),"timestamp":utc_iso(r.timestamp),"channel":r.channel or "",
             "source_hash":r.source_hash} for r in rows]

def graph_from_records(rows):
    g=nx.DiGraph()
    for r in rows:
        s,t=r["source"],r["target"]
        tx={k:r.get(k) for k in ["transaction_id","amount","timestamp","channel","source_hash"]}
        if g.has_edge(s,t):
            e=g[s][t]; e["amount"]+=float(r["amount"]); e["count"]+=1; e["transactions"].append(tx)
            e["latest"]=max(e["latest"],r["timestamp"])
        else:
            g.add_edge(s,t,amount=float(r["amount"]),count=1,transactions=[tx],
                       earliest=r["timestamp"],latest=r["timestamp"])
    return g

def graph_payload(db, start=None, end=None):
    rows=tx_records(db,start,end); g=graph_from_records(rows)
    complaints=db.query(Complaint).all()
    linked={c.account_id for c in complaints if c.account_id}
    nodes=[]
    for n in g.nodes:
        inc=sum(d["amount"] for _,_,d in g.in_edges(n,data=True))
        out=sum(d["amount"] for _,_,d in g.out_edges(n,data=True))
        nodes.append({"data":{"id":n,"label":n,"in_amount":round(inc,2),"out_amount":round(out,2),
                              "degree":g.degree(n),"has_complaint":n in linked}})
    edges=[]
    for s,t,d in g.edges(data=True):
        edges.append({"data":{"id":s+"__"+t,"source":s,"target":t,"amount":round(d["amount"],2),
            "count":d["count"],"transactions":d["transactions"],"earliest":d["earliest"],"latest":d["latest"]}})
    return {"nodes":nodes,"edges":edges}

def investigate_account(db, account_id, max_hops=4, start=None, end=None):
    rows=tx_records(db,start,end); g=graph_from_records(rows)
    if account_id not in g: return None
    paths=[]
    for target in g.nodes:
        if target==account_id: continue
        try:
            for path in nx.all_simple_paths(g,account_id,target,cutoff=max_hops):
                steps=[]
                for a,b in zip(path,path[1:]):
                    edge=g[a][b]
                    steps.append({"source":a,"target":b,"amount":round(edge["amount"],2),
                                  "transactions":[x["transaction_id"] for x in edge["transactions"]],
                                  "transactions_detail":edge["transactions"]})
                paths.append({"path":path,"hops":len(path)-1,"steps":steps})
                if len(paths)>=150: break
        except (nx.NetworkXNoPath,nx.NodeNotFound): pass
        if len(paths)>=150: break
    cp=db.query(Complaint).filter(Complaint.account_id==account_id).all()
    incoming=sum(float(r["amount"]) for r in rows if r["target"]==account_id)
    outgoing=sum(float(r["amount"]) for r in rows if r["source"]==account_id)
    return {"account_id":account_id,"incoming_total":round(incoming,2),"outgoing_total":round(outgoing,2),
            "paths":paths,"linked_complaints":[{"complaint_id":c.complaint_id,"category":c.category,
            "description":c.description,"created_at":utc_iso(c.created_at),"status":c.status} for c in cp],
            "note":"Recorded paths support investigation only; they do not prove wrongdoing."}

def temporal_patterns(db, start=None, end=None):
    rows=tx_records(db,start,end)
    if not rows: return {"patterns":[],"message":"No transactions in selected time window."}
    by_account=defaultdict(list)
    for r in rows:
        by_account[r["source"]].append(r)
        by_account[r["target"]].append(r)
    patterns=[]
    g=graph_from_records(rows)
    for account in g.nodes:
        incoming=[r for r in rows if r["target"]==account]
        outgoing=[r for r in rows if r["source"]==account]
        if not incoming or not outgoing: continue
        last_in=max(pd.to_datetime(r["timestamp"],utc=True) for r in incoming)
        first_out=min(pd.to_datetime(r["timestamp"],utc=True) for r in outgoing)
        elapsed=(first_out-last_in).total_seconds()/60
        in_sum=sum(r["amount"] for r in incoming); out_sum=sum(r["amount"] for r in outgoing)
        ratio=min(in_sum,out_sum)/max(in_sum,out_sum,1)
        if 0 <= elapsed <= 60 and ratio >= 0.45:
            patterns.append({"account_id":account,"pattern":"rapid_pass_through",
                "minutes_between_last_in_and_first_out":round(elapsed,2),
                "incoming_amount":round(in_sum,2),"outgoing_amount":round(out_sum,2),
                "amount_similarity":round(ratio,3),
                "evidence_transaction_ids":sorted({r["transaction_id"] for r in incoming+outgoing}),
                "explanation":"An incoming transfer is followed by an outgoing transfer within 60 minutes and aggregate amounts are similar."})
        if g.in_degree(account)>=2 and g.out_degree(account)>=2:
            evidence=[r["transaction_id"] for r in incoming+outgoing]
            patterns.append({"account_id":account,"pattern":"fan_in_fan_out",
                "incoming_counterparties":g.in_degree(account),"outgoing_counterparties":g.out_degree(account),
                "incoming_amount":round(in_sum,2),"outgoing_amount":round(out_sum,2),
                "evidence_transaction_ids":sorted(set(evidence)),
                "explanation":"The account has multiple distinct recorded senders and recipients in this graph."})
    patterns.sort(key=lambda p:(p["pattern"],p["account_id"]))
    return {"patterns":patterns,"message":"Patterns are leads for human review, not findings of guilt."}

def complaint_matches(db, min_similarity=0.12):
    complaints=db.query(Complaint).order_by(Complaint.created_at.desc()).all()
    txs=db.query(Transaction).order_by(Transaction.timestamp.desc()).limit(5000).all()
    if not complaints or not txs: return {"matches":[],"method":"exact account link + TF-IDF text similarity"}
    docs=[f"{c.category} {c.description} {c.account_id}" for c in complaints]
    txdocs=[f"{t.source} {t.target} {t.channel} transaction {t.transaction_id} amount {t.amount}" for t in txs]
    try:
        vec=TfidfVectorizer(ngram_range=(1,2),stop_words="english")
        matrix=vec.fit_transform(docs+txdocs)
        sims=cosine_similarity(matrix[:len(docs)],matrix[len(docs):])
    except ValueError:
        sims=np.zeros((len(docs),len(txs)))
    matches=[]
    for i,c in enumerate(complaints):
        for j,t in enumerate(txs):
            exact=c.account_id in (t.source,t.target)
            score=float(sims[i,j])
            if exact or score>=min_similarity:
                matches.append({"complaint_id":c.complaint_id,"transaction_id":t.transaction_id,
                    "account_id":c.account_id,"transaction_accounts":[t.source,t.target],
                    "exact_account_match":exact,"text_similarity":round(score,3),
                    "match_reason":"Exact account reference" if exact else "Text similarity candidate",
                    "human_review_required":True})
    matches.sort(key=lambda x:(not x["exact_account_match"],-x["text_similarity"]))
    return {"matches":matches[:500],"method":"exact account link + TF-IDF text similarity",
            "note":"Text similarity is a candidate generator, not proof that a complaint refers to a transaction."}

def feature_rows(db):
    rows=tx_records(db)
    g=graph_from_records(rows)
    cp=db.query(Complaint).all()
    complaint_counts={}
    for c in cp: complaint_counts[c.account_id]=complaint_counts.get(c.account_id,0)+1
    max_amt=max([r["amount"] for r in rows],default=1)
    features=[]
    for n in g.nodes:
        incoming=[r for r in rows if r["target"]==n]; outgoing=[r for r in rows if r["source"]==n]
        inc=sum(r["amount"] for r in incoming); out=sum(r["amount"] for r in outgoing)
        degree=g.degree(n); ratio=min(inc,out)/max(inc,out,1)
        rapid=0
        if incoming and outgoing:
            li=max(pd.to_datetime(r["timestamp"],utc=True) for r in incoming)
            fo=min(pd.to_datetime(r["timestamp"],utc=True) for r in outgoing)
            rapid=int(0 <= (fo-li).total_seconds() <= 3600)
        features.append({"account_id":n,"incoming":inc,"outgoing":out,"degree":degree,
            "amount_similarity":ratio,"complaints":complaint_counts.get(n,0),"rapid":rapid,
            "flow_scale":min((inc+out)/(2*max_amt),1)})
    return features

def anomaly_scores(db):
    feats=feature_rows(db)
    if not feats: return []
    cols=["incoming","outgoing","degree","amount_similarity","complaints","rapid","flow_scale"]
    X=np.array([[float(f[k]) for k in cols] for f in feats],dtype=float)
    # Small datasets make unsupervised estimates unstable; still mark that limitation in response.
    if len(feats)<5:
        return [{"account_id":f["account_id"],"anomaly_score":None,"anomaly_band":"insufficient_data",
                 "features":{k:f[k] for k in cols},
                 "note":"At least five accounts are required for this demo Isolation Forest run."} for f in feats]
    model=IsolationForest(n_estimators=150,contamination="auto",random_state=42)
    model.fit(X)
    raw=-model.decision_function(X)
    lo,hi=float(raw.min()),float(raw.max())
    for i,f in enumerate(feats):
        score=50 if hi==lo else round(100*(float(raw[i])-lo)/(hi-lo),1)
        f["anomaly_score"]=score
        f["anomaly_band"]="higher_relative_anomaly" if model.predict(X[i:i+1])[0]==-1 else "lower_relative_anomaly"
        f["note"]="Unsupervised relative anomaly; not a fraud probability."
    return sorted(feats,key=lambda f:f.get("anomaly_score",0),reverse=True)

def review_priorities(db):
    feats=feature_rows(db)
    if not feats: return []
    max_amount=max([max(f["incoming"],f["outgoing"]) for f in feats],default=1) or 1
    out=[]
    for f in feats:
        flow=min((f["incoming"]+f["outgoing"])/(2*max_amount),1)
        network=min(f["degree"]/5,1); complaints=min(f["complaints"]/2,1)
        score=round(100*(.35*f["amount_similarity"]+.25*flow+.25*network+.15*complaints))
        reasons=[]
        if f["degree"]>=3: reasons.append({"signal":"multiple_connections","explanation":"Several recorded transaction connections."})
        if f["incoming"]>0 and f["outgoing"]>0 and f["amount_similarity"]>=.65: reasons.append({"signal":"pass_through_pattern","explanation":"Incoming and outgoing totals are similar."})
        if flow>=.5: reasons.append({"signal":"relative_flow","explanation":"Flow is high relative to this dataset."})
        if f["complaints"]: reasons.append({"signal":"linked_complaint","explanation":f'{f["complaints"]} complaint(s) reference this account.'})
        evidence=sorted({r["transaction_id"] for r in tx_records(db) if r["source"]==f["account_id"] or r["target"]==f["account_id"]})
        out.append({"account_id":f["account_id"],"score":score,"incoming":round(f["incoming"],2),
            "outgoing":round(f["outgoing"],2),"degree":f["degree"],"complaints":f["complaints"],
            "reasons":reasons or [{"signal":"no_strong_demo_signal","explanation":"No strong signal under the demo rules."}],
            "evidence_transaction_ids":evidence,"review_band":"elevated_review" if score>=45 else "routine_review"})
    return sorted(out,key=lambda x:x["score"],reverse=True)
