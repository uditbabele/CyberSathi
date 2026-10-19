
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timezone
import csv, io, json, os, hashlib
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from .db import Base, engine, get_db, SessionLocal
from .models import Transaction, Complaint, AuditLog, User
from .security import get_current_user, require_role, create_token, verify_password, seed_admin, password_hash
from .config import ADMIN_USERNAME, ADMIN_PASSWORD, DEMO_MODE
from .security_hardening import MaxRequestBodyMiddleware, validate_production_config
from .seed import seed_demo
from . import analytics

app=FastAPI(title="CyberSathi",version="0.3.0",
    description="Evidence-linked transaction network investigation prototype")
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC=os.path.join(ROOT,"app","static")
app.mount("/static",StaticFiles(directory=STATIC),name="static")
app.add_middleware(MaxRequestBodyMiddleware, max_bytes=10_500_000)

@app.on_event("startup")
def startup():
    validate_production_config()
    if os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true" and os.getenv("ENVIRONMENT", "development").lower() != "production":
        Base.metadata.create_all(bind=engine)
    db=SessionLocal()
    try:
        seed_admin(db)
        seed_demo(db)
    finally: db.close()

def audit(db,user,action,resource="",details=""):
    db.add(AuditLog(username=user.username if user else "anonymous",action=action,
                    resource=resource,details=details[:2000]))
    db.commit()

def time_filter(start,end):
    for name,value in [("start",start),("end",end)]:
        if value:
            try: datetime.fromisoformat(value.replace("Z","+00:00"))
            except Exception: raise HTTPException(400,f"Invalid {name} timestamp.")
    return start,end

class LoginInput(BaseModel):
    username:str
    password:str

class UserInput(BaseModel):
    username:str
    password:str
    role:str="investigator"

class CounterfactualInput(BaseModel):
    remove_account:str
    start: str|None=None
    end: str|None=None

@app.get("/")
def home():
    return FileResponse(os.path.join(STATIC,"index.html"))

@app.get("/api/health")
def health():
    return {"status":"ok","version":"0.3.0","database":engine.dialect.name,
            "demo_mode":DEMO_MODE}

@app.post("/api/auth/login")
def login(body:LoginInput,db:Session=Depends(get_db)):
    user=db.query(User).filter(User.username==body.username,User.active==True).first()
    if not user or not verify_password(body.password,user.password_hash):
        audit(db,None,"login_failed",body.username,"Invalid credentials")
        raise HTTPException(401,"Invalid username or password.")
    token=create_token(user.username,user.role)
    audit(db,user,"login","session","Successful sign-in")
    return {"access_token":token,"token_type":"bearer","username":user.username,"role":user.role}

@app.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    return {"username":user.username,"role":user.role}

@app.post("/api/auth/users")
def create_user(body:UserInput,db:Session=Depends(get_db),user=Depends(require_role("admin"))):
    if body.role not in ("admin","investigator","reviewer"):
        raise HTTPException(400,"Role must be admin, investigator, or reviewer.")
    if len(body.password)<12: raise HTTPException(400,"Password must contain at least 12 characters.")
    if db.query(User).filter(User.username==body.username).first():
        raise HTTPException(409,"Username already exists.")
    new=User(username=body.username,password_hash=password_hash(body.password),role=body.role,active=True)
    db.add(new);db.commit()
    audit(db,user,"user_created",body.username,f"Role={body.role}")
    return {"created":True,"username":body.username,"role":body.role}

@app.get("/api/summary")
def summary(start: str|None=None,end: str|None=None,db:Session=Depends(get_db),user=Depends(get_current_user)):
    start,end=time_filter(start,end); rows=analytics.tx_records(db,start,end)
    graph=analytics.graph_from_records(rows)
    return {"transactions":len(rows),"accounts":graph.number_of_nodes(),"connections":graph.number_of_edges(),
        "complaints":db.query(Complaint).count(),"total_amount":round(sum(x["amount"] for x in rows),2),
        "currency":"INR","data_mode":"synthetic demo unless uploaded data replaces it",
        "period":{"start":rows[0]["timestamp"] if rows else None,"end":rows[-1]["timestamp"] if rows else None}}

@app.get("/api/transactions")
def transactions(start:str|None=None,end:str|None=None,db:Session=Depends(get_db),user=Depends(get_current_user)):
    start,end=time_filter(start,end); result=analytics.tx_records(db,start,end)
    audit(db,user,"transactions_viewed","transactions",f"count={len(result)}")
    return result

@app.get("/api/complaints")
def complaints(db:Session=Depends(get_db),user=Depends(get_current_user)):
    rows=db.query(Complaint).order_by(desc(Complaint.created_at)).all()
    audit(db,user,"complaints_viewed","complaints",f"count={len(rows)}")
    return [{"complaint_id":c.complaint_id,"account_id":c.account_id,"category":c.category,
             "description":c.description,"created_at":c.created_at.isoformat(),"status":c.status,
             "source_hash":c.source_hash} for c in rows]

@app.get("/api/graph")
def graph(start:str|None=None,end:str|None=None,db:Session=Depends(get_db),user=Depends(get_current_user)):
    start,end=time_filter(start,end); result=analytics.graph_payload(db,start,end)
    audit(db,user,"graph_viewed","transaction_graph",f"nodes={len(result['nodes'])}, edges={len(result['edges'])}")
    return result

@app.get("/api/investigate/{account_id}")
def investigate(account_id:str,max_hops:int=Query(default=4,ge=1,le=8),start:str|None=None,end:str|None=None,
                db:Session=Depends(get_db),user=Depends(get_current_user)):
    start,end=time_filter(start,end)
    result=analytics.investigate_account(db,account_id,max_hops,start,end)
    if result is None: raise HTTPException(404,"Account not found in selected time window.")
    audit(db,user,"account_investigated",account_id,f"paths={len(result['paths'])}")
    return result

@app.get("/api/analytics/temporal-patterns")
def temporal_patterns(start:str|None=None,end:str|None=None,db:Session=Depends(get_db),user=Depends(get_current_user)):
    start,end=time_filter(start,end); result=analytics.temporal_patterns(db,start,end)
    audit(db,user,"temporal_patterns_viewed","analytics",f"patterns={len(result['patterns'])}")
    return result

@app.get("/api/analytics/complaint-matches")
def complaint_matches(db:Session=Depends(get_db),user=Depends(get_current_user)):
    result=analytics.complaint_matches(db)
    audit(db,user,"complaint_matches_viewed","complaint_transaction_links",f"matches={len(result['matches'])}")
    return result

@app.get("/api/analytics/anomalies")
def anomalies(db:Session=Depends(get_db),user=Depends(get_current_user)):
    result=analytics.anomaly_scores(db)
    audit(db,user,"anomaly_analysis_run","accounts",f"count={len(result)}")
    return {"results":result,"method":"IsolationForest on account-level graph features",
            "warning":"Relative unsupervised anomaly score; not a fraud probability. Small data can be unstable."}

@app.get("/api/risk")
def risk(db:Session=Depends(get_db),user=Depends(get_current_user)):
    result=analytics.review_priorities(db)
    audit(db,user,"review_priorities_viewed","accounts",f"count={len(result)}")
    return result

@app.post("/api/counterfactual")
def counterfactual(body:CounterfactualInput,db:Session=Depends(get_db),user=Depends(get_current_user)):
    start,end=time_filter(body.start,body.end)
    rows=analytics.tx_records(db,start,end); g=analytics.graph_from_records(rows)
    if body.remove_account not in g: raise HTTPException(404,"Account not found in selected window.")
    before={"nodes":g.number_of_nodes(),"edges":g.number_of_edges(),"components":__import__("networkx").number_weakly_connected_components(g)}
    g.remove_node(body.remove_account)
    after={"nodes":g.number_of_nodes(),"edges":g.number_of_edges(),"components":__import__("networkx").number_weakly_connected_components(g)}
    audit(db,user,"counterfactual_simulation",body.remove_account,json.dumps({"before":before,"after":after}))
    return {"removed_account":body.remove_account,"before":before,"after":after,
            "note":"Graph structure only; not a real-world causal conclusion."}

@app.post("/api/upload/transactions")
async def upload_transactions(file:UploadFile=File(...),db:Session=Depends(get_db),user=Depends(require_role("admin","investigator"))):
    if not file.filename.lower().endswith(".csv"): raise HTTPException(400,"Upload CSV only.")
    raw=await file.read()
    if len(raw)>10_000_000: raise HTTPException(413,"CSV must be smaller than 10 MB.")
    try: rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except Exception: raise HTTPException(400,"CSV must be UTF-8 encoded.")
    required={"transaction_id","source","target","amount","timestamp"}
    if not rows or not required.issubset(rows[0].keys()): raise HTTPException(400,f"Required columns: {sorted(required)}")
    clean=[]; seen=set()
    for i,r in enumerate(rows, start=2):
        try:
            tid=r["transaction_id"].strip();src=r["source"].strip();tgt=r["target"].strip()
            amount=float(r["amount"]);ts=datetime.fromisoformat(r["timestamp"].replace("Z","+00:00"))
            if ts.tzinfo is None: ts=ts.replace(tzinfo=timezone.utc)
            if not tid or not src or not tgt or amount<0: raise ValueError()
            if tid in seen: raise HTTPException(400,f"Duplicate transaction_id at CSV row {i}.")
            seen.add(tid);channel=r.get("channel","")
            canonical=f"{tid}|{src}|{tgt}|{amount}|{ts.isoformat()}|{channel}"
            clean.append(Transaction(transaction_id=tid,source=src,target=tgt,amount=amount,timestamp=ts,
                                     channel=channel,source_hash=hashlib.sha256(canonical.encode()).hexdigest()))
        except HTTPException: raise
        except Exception: raise HTTPException(400,f"Invalid values at CSV row {i}.")
    db.query(Transaction).delete()
    db.add_all(clean);db.commit()
    audit(db,user,"transactions_imported","transactions",f"rows={len(clean)}")
    return {"ok":True,"rows":len(clean),"message":"Validated transactions imported. Existing transaction rows were replaced."}

@app.post("/api/upload/complaints")
async def upload_complaints(file:UploadFile=File(...),db:Session=Depends(get_db),user=Depends(require_role("admin","investigator"))):
    if not file.filename.lower().endswith(".csv"): raise HTTPException(400,"Upload CSV only.")
    raw=await file.read()
    if len(raw)>10_000_000: raise HTTPException(413,"CSV must be smaller than 10 MB.")
    try: rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except Exception: raise HTTPException(400,"CSV must be UTF-8 encoded.")
    required={"complaint_id","account_id","category","description","created_at","status"}
    if not rows or not required.issubset(rows[0].keys()): raise HTTPException(400,f"Required columns: {sorted(required)}")
    clean=[];seen=set()
    for i,r in enumerate(rows,start=2):
        try:
            cid=r["complaint_id"].strip();account=r["account_id"].strip()
            ts=datetime.fromisoformat(r["created_at"].replace("Z","+00:00"))
            if ts.tzinfo is None:ts=ts.replace(tzinfo=timezone.utc)
            if not cid or not account or cid in seen: raise ValueError()
            seen.add(cid);canonical="|".join(r.get(k,"") for k in sorted(required))
            clean.append(Complaint(complaint_id=cid,account_id=account,category=r["category"],
                description=r["description"],created_at=ts,status=r["status"],
                source_hash=hashlib.sha256(canonical.encode()).hexdigest()))
        except Exception: raise HTTPException(400,f"Invalid or duplicate complaint at CSV row {i}.")
    db.query(Complaint).delete();db.add_all(clean);db.commit()
    audit(db,user,"complaints_imported","complaints",f"rows={len(clean)}")
    return {"ok":True,"rows":len(clean),"message":"Validated complaints imported. Existing complaint rows were replaced."}

@app.get("/api/audit")
def get_audit(limit:int=Query(default=100,ge=1,le=500),db:Session=Depends(get_db),user=Depends(require_role("admin","reviewer"))):
    rows=db.query(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit).all()
    return [{"id":x.id,"username":x.username,"action":x.action,"resource":x.resource,
             "details":x.details,"created_at":x.created_at.isoformat()} for x in rows]

@app.get("/api/export/report.json")
def export_json(db:Session=Depends(get_db),user=Depends(get_current_user)):
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"platform":"CyberSathi",
        "summary":summary(db=db,user=user),"review_priorities":analytics.review_priorities(db),
        "temporal_patterns":analytics.temporal_patterns(db)["patterns"],
        "complaint_matches":analytics.complaint_matches(db)["matches"][:100],
        "limitations":["Synthetic demo data unless replaced.","Heuristic and anomaly outputs are not proof of crime.",
                       "Text similarity generates candidates only.","Human review required."]}
    audit(db,user,"report_exported","json_report","Exported investigation JSON")
    return report

@app.get("/api/export/report.pdf")
def export_pdf(db:Session=Depends(get_db),user=Depends(get_current_user)):
    buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=32,leftMargin=32,topMargin=32,bottomMargin=32)
    styles=getSampleStyleSheet();story=[]
    story.append(Paragraph("CyberSathi — Investigation Review Report",styles["Title"]))
    story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).isoformat()}",styles["Normal"]))
    story.append(Paragraph("Prototype report. Review leads are not proof of wrongdoing.",styles["Italic"]))
    s=summary(db=db,user=user)
    story.append(Spacer(1,12));story.append(Paragraph("Dataset summary",styles["Heading2"]))
    story.append(Paragraph(f"Transactions: {s['transactions']} | Accounts: {s['accounts']} | Connections: {s['connections']} | Complaints: {s['complaints']} | Sum of row amounts: ₹{s['total_amount']:,.0f}",styles["Normal"]))
    story.append(Spacer(1,12));story.append(Paragraph("Review-priority signals",styles["Heading2"]))
    data=[["Account","Score / 100","Incoming","Outgoing","Signals","Evidence transaction IDs"]]
    for r in analytics.review_priorities(db)[:30]:
        signals="; ".join(x["signal"] for x in r["reasons"])
        data.append([r["account_id"],str(r["score"]),f"INR {r['incoming']:,.0f}",f"INR {r['outgoing']:,.0f}",signals,", ".join(r["evidence_transaction_ids"][:12])])
    table=Table(data,repeatRows=1,colWidths=[90,65,85,85,175,230])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1f3a5b")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#aab7c4")),
        ("FONTSIZE",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f1f5f9")])]))
    story.append(table);story.append(Spacer(1,14));story.append(Paragraph("Methodology and limitations",styles["Heading2"]))
    story.append(Paragraph("Scores are transparent rule-based triage signals, not calibrated fraud probabilities. Temporal patterns and complaint text matches are candidate leads requiring human verification. Transaction IDs are included to support review. The demo dataset is synthetic by default. Do not use this report as a determination of guilt.",styles["BodyText"]))
    doc.build(story);buf.seek(0)
    audit(db,user,"report_exported","pdf_report","Exported investigation PDF")
    return StreamingResponse(buf,media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=traceweave_investigation_report.pdf"})
