
"""Reproducible, explicitly synthetic model sanity-check. Not a real-world fraud benchmark."""
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

def make_data(n=2400, seed=42):
    rng=np.random.default_rng(seed)
    # Feature columns: amount, degree, amount_similarity, rapid_transfer, complaint_count, fan_out
    normal=np.column_stack([
        rng.lognormal(7.0,.8,n), rng.poisson(1.4,n), rng.beta(1.4,5,n),
        rng.binomial(1,.08,n), rng.poisson(.12,n), rng.poisson(.6,n)
    ])
    labels=np.zeros(n,dtype=int)
    suspicious_n=n//5
    suspicious=np.column_stack([
        rng.lognormal(9.0,.55,suspicious_n), rng.poisson(3.8,suspicious_n),
        rng.beta(5,1.8,suspicious_n), rng.binomial(1,.72,suspicious_n),
        rng.poisson(.6,suspicious_n), rng.poisson(2.6,suspicious_n)
    ])
    X=np.vstack([normal,suspicious])
    y=np.concatenate([labels,np.ones(suspicious_n,dtype=int)])
    # Add overlap/noise so the toy dataset is not perfectly separable.
    X += rng.normal(0,.04,X.shape)*np.maximum(X,1)
    idx=rng.permutation(len(y))
    return X[idx],y[idx]

if __name__=="__main__":
    X,y=make_data()
    X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=.25,random_state=42,stratify=y)
    model=make_pipeline(StandardScaler(),RandomForestClassifier(n_estimators=250,
        max_depth=8,min_samples_leaf=3,class_weight="balanced",random_state=42))
    model.fit(X_train,y_train)
    p=model.predict(X_test); probs=model.predict_proba(X_test)[:,1]
    print("SYNTHETIC DATA ONLY — results do not estimate real-world fraud performance")
    print("Feature order: amount, degree, amount_similarity, rapid_transfer, complaint_count, fan_out")
    print(classification_report(y_test,p,target_names=["synthetic_normal","synthetic_pattern"]))
    print("Confusion matrix:\n",confusion_matrix(y_test,p))
    print("ROC-AUC:",round(roc_auc_score(y_test,probs),4))
