"""Generate reproducible trajectories and evaluate future escalation on held-out people."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

ROOT=Path(__file__).resolve().parents[1]
FEATURES=['current_distress','previous_distress','distress_delta_7d','threat_level','court_event','investigation_delay','compensation_delay','sleep_score','fear_score','missed_checkins']

def train():
    rng=np.random.default_rng(26094)
    records=[]
    for person in range(150):
        pattern=person%9
        distress=float(rng.uniform(15,65)); previous=distress
        trajectory=[]
        for week in range(16):
            threat=int(pattern==3 and week>=7 or rng.random()<.08)
            court=int(week%6==4)
            intervention=int(week>=9 and pattern in [6,7,8])
            drift=[0,2,0,1,1.2,1.4,0,-1,2.5][pattern]
            spike=20 if pattern==2 and week==8 else 0
            next_distress=float(np.clip(distress+drift+threat*6+court*4-intervention*(5 if pattern==7 else 1)+spike+rng.normal(0,4),3,98))
            sleep=int(np.clip(round(distress/25+rng.normal(0,.6)),0,4))
            row={'synthetic':True,'case_id':f'SYN-{person:04}','victim_id':f'SYN-V-{person:04}','week':week,'pattern':pattern,
                 'case_stage':'Court' if week>5 else 'Investigation','threat_level':threat,'court_event':court,'investigation_delay':int(pattern==4),
                 'compensation_delay':int(pattern==5),'rehabilitation_status':'pending' if pattern==6 else 'not_requested',
                 'sleep_score':sleep,'fear_score':int(np.clip(round(distress/25),0,4)),'sadness_score':distress/100,'anxiety_score':distress/100,
                 'sentiment_score':-distress/100,'emotion_fear':distress/100,'emotion_sadness':distress/120,'emotion_anger':float(rng.uniform(0,.5)),
                 'voice_pitch_mean':float(rng.normal(180,25)),'voice_pitch_std':float(rng.uniform(10,40)),
                 'speech_rate':float(150-distress*.6+rng.normal(0,8)),'pause_ratio':float(.1+distress/400),'energy':float(.5-distress/300),
                 'engagement_score':float(100-distress*.4),'missed_checkins':int(distress>65),'previous_distress':previous,
                 'current_distress':distress,'distress_delta_7d':distress-previous,'intervention_type':'Counselling' if intervention else 'None',
                 'intervention_status':'Completed' if intervention else 'None','outcome':'improving' if next_distress<distress else 'worsening',
                 'risk_level':'High' if distress>=70 else 'Moderate' if distress>=50 else 'Low',
                 'future_escalation_risk':int(next_distress-distress>=7 or (next_distress>=70 and distress<70))}
            trajectory.append(row); previous,distress=distress,next_distress
        records.extend(trajectory)
    target=ROOT/'data'/'synthetic'/'longitudinal.csv'; target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    # Person-level split prevents one person's history leaking into the test set.
    train_rows=[r for r in records if int(r['victim_id'].split('-')[-1])<120]
    test_rows=[r for r in records if int(r['victim_id'].split('-')[-1])>=120]
    x=np.array([[r[k] for k in FEATURES] for r in train_rows]); y=np.array([r['future_escalation_risk'] for r in train_rows])
    xt=np.array([[r[k] for k in FEATURES] for r in test_rows]); yt=np.array([r['future_escalation_risk'] for r in test_rows])
    scaler=StandardScaler().fit(x); model=LogisticRegression(class_weight='balanced',random_state=26094).fit(scaler.transform(x),y)
    probabilities=model.predict_proba(scaler.transform(xt))[:,1]; predictions=(probabilities>=.5).astype(int)
    directory=ROOT/'ai'/'models'; directory.mkdir(parents=True,exist_ok=True)
    version='synthetic-logistic-v1'
    (directory/'logistic.json').write_text(json.dumps({'version':version,'features':FEATURES,'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'coef':model.coef_[0].tolist(),'intercept':float(model.intercept_[0])},indent=2))
    metrics={'version':version,'dataset_version':'synthetic-26094-v1','training_date':datetime.now(timezone.utc).isoformat(),'records':len(records),
             'train_people':120,'test_people':30,'test_records':len(test_rows),'split':'Held-out people, no patient overlap',
             'accuracy':accuracy_score(yt,predictions),'precision':precision_score(yt,predictions,zero_division=0),
             'recall':recall_score(yt,predictions),'f1':f1_score(yt,predictions),'roc_auc':roc_auc_score(yt,probabilities),
             'confusion_matrix':confusion_matrix(yt,predictions).tolist(),
             'feature_importance':[{'name':name,'value':float(abs(value))} for name,value in zip(FEATURES,model.coef_[0])],
             'limitations':'Synthetic outcomes and features are generator-dependent; not clinical or real-world validation.'}
    (directory/'metrics.json').write_text(json.dumps(metrics,indent=2))
    print(json.dumps(metrics,indent=2))

if __name__=='__main__': train()
