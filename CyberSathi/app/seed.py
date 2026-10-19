
from datetime import datetime, timezone
import hashlib
from sqlalchemy.orm import Session
from .models import Transaction, Complaint

TX = [
("T001","VICTIM_A","ACC_X",50000,"2026-10-20T10:00:00","UPI"),
("T002","ACC_X","ACC_Y",48000,"2026-10-20T10:03:00","IMPS"),
("T003","ACC_Y","ACC_Z",24000,"2026-10-20T10:06:00","UPI"),
("T004","ACC_Y","ACC_W",23000,"2026-10-20T10:07:00","UPI"),
("T005","VICTIM_B","ACC_Z",30000,"2026-10-20T10:08:00","IMPS"),
("T006","ACC_Z","ACC_Q",51000,"2026-10-20T10:11:00","NEFT"),
("T007","ACC_W","ACC_Q",21000,"2026-10-20T10:12:00","UPI"),
("T008","ACC_Q","MERCHANT_1",69000,"2026-10-20T10:15:00","IMPS"),
("T009","NORMAL_A","NORMAL_B",1200,"2026-10-20T11:30:00","UPI"),
("T010","ACC_X","ACC_R",1500,"2026-10-20T10:40:00","UPI"),
("T011","ACC_R","MERCHANT_2",1400,"2026-10-20T10:42:00","UPI"),
("T012","NORMAL_C","NORMAL_D",850,"2026-10-20T12:20:00","UPI"),
("T013","VICTIM_C","ACC_M",40000,"2026-10-20T13:00:00","IMPS"),
("T014","ACC_M","ACC_N",39000,"2026-10-20T13:04:00","UPI"),
("T015","ACC_N","MERCHANT_3",38000,"2026-10-20T13:08:00","IMPS"),
]
CP = [
("C001","VICTIM_A","unauthorized_transfer","Customer reports an unauthorized transfer of 50000","2026-10-20T10:20:00","open"),
("C002","VICTIM_B","online_fraud","Customer reports online fraud and transfer of 30000","2026-10-20T10:25:00","open"),
("C003","NORMAL_A","account_query","Question about a small routine payment","2026-10-20T11:40:00","closed"),
("C004","VICTIM_C","unauthorized_transfer","Customer reports an unknown transfer around 40000","2026-10-20T13:15:00","open"),
]
def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()

def seed_demo(db: Session):
    if db.query(Transaction).count()==0:
        for tid,src,tgt,amount,ts,channel in TX:
            raw=f"{tid}|{src}|{tgt}|{amount}|{ts}|{channel}"
            db.add(Transaction(transaction_id=tid,source=src,target=tgt,amount=amount,
                timestamp=datetime.fromisoformat(ts).replace(tzinfo=timezone.utc),channel=channel,source_hash=sha(raw)))
    if db.query(Complaint).count()==0:
        for cid,acct,cat,desc,ts,status in CP:
            raw=f"{cid}|{acct}|{cat}|{desc}|{ts}|{status}"
            db.add(Complaint(complaint_id=cid,account_id=acct,category=cat,description=desc,
                created_at=datetime.fromisoformat(ts).replace(tzinfo=timezone.utc),status=status,source_hash=sha(raw)))
    db.commit()
