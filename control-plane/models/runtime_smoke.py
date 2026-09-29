#!/usr/bin/env python3
import hashlib, json, pathlib, sys

def main():
    from sklearn.datasets import load_iris
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    data=load_iris()
    X=data.data
    y=data.target
    model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=500,random_state=7))
    model.fit(X,y)
    sample=X[0].reshape(1,-1)
    prediction=int(model.predict(sample)[0])
    probability=float(model.predict_proba(sample)[0][prediction])
    payload={
      'provider':'github_actions_sklearn',
      'runtime':'scikit-learn',
      'runtime_version':__import__('sklearn').__version__,
      'task_class':'classification-smoke',
      'dataset':'iris',
      'prediction':prediction,
      'expected_prediction':int(y[0]),
      'probability':probability,
      'status':'MODEL_EXECUTION_PASS' if prediction==int(y[0]) and probability>0.5 else 'MODEL_EXECUTION_FAIL'
    }
    encoded=json.dumps(payload,sort_keys=True).encode()
    payload['result_sha256']=hashlib.sha256(encoded).hexdigest()
    print(json.dumps(payload,sort_keys=True))
    if payload['status']!='MODEL_EXECUTION_PASS':
        raise SystemExit(2)

if __name__=='__main__': main()
