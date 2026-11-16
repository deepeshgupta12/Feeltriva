"""Reproducible source audit and experimental Bernoulli baseline; not a clinical model.
Usage: python experiments/audit_and_baseline.py --sources /path/to/zip/folder
Dependencies: numpy. Never modifies original archives.
"""
import argparse,csv,io,json,hashlib,collections,re,zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def norm(s): return ' '.join(s.strip().casefold().split())
def dump(p,obj): p.write_text(json.dumps(obj,indent=2,ensure_ascii=False))
def writecsv(p,rows):
 if not rows:return
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def digest(row):return hashlib.sha256(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def write_candidate_catalogs(labels,featuremap):
 for rows,key,term,original,filename in [
  (labels,'candidate_disease_id','normalized_label','source_label','disease_candidate_catalog.csv'),
  (featuremap,'candidate_feature_id','candidate_term','original_header','feature_candidate_catalog.csv')]:
  groups=collections.defaultdict(list)
  for row in rows:groups[row[key]].append(row)
  catalog=[]
  for candidate_id,members in sorted(groups.items()):
   assert len({m[term] for m in members})==1, 'Candidate hash collision'
   catalog.append({'candidate_id':candidate_id,'lexical_term':members[0][term],
    'original_terms_json':json.dumps(sorted({m[original] for m in members}),ensure_ascii=False),
    'source_files_json':json.dumps(sorted({m['archive']+'/'+m['file'] for m in members})),
    'mapping_status':'lexical_candidate_not_clinically_approved'})
  writecsv(ROOT/'data_audit'/filename,catalog)
def metrics(y,probs,k):
 pred=probs.argmax(1); cm=np.zeros((k,k),dtype=int);np.add.at(cm,(y,pred),1)
 tp=cm.diagonal();support=cm.sum(1);precision=np.divide(tp,cm.sum(0),out=np.zeros(k),where=cm.sum(0)>0);recall=np.divide(tp,support,out=np.zeros(k),where=support>0)
 f1=np.divide(2*precision*recall,precision+recall,out=np.zeros(k),where=precision+recall>0)
 conf=probs.max(1);correct=pred==y;ece=0;bins=[]
 bin_index=np.minimum((conf*10).astype(int),9)
 for b in range(10):
  a=b/10
  ix=bin_index==b
  if ix.any():
   acc=float(correct[ix].mean());c=float(conf[ix].mean());ece+=ix.mean()*abs(acc-c)
   bins.append({'lower':float(a),'n':int(ix.sum()),'mean_confidence':c,'accuracy':acc})
 return {'n':len(y),'top1_accuracy':float(correct.mean()),'top3_accuracy':float(np.any(np.argsort(probs,axis=1)[:,-3:]==y[:,None],axis=1).mean()),'macro_f1':float(f1[support>0].mean()),'balanced_accuracy':float(recall[support>0].mean()),'ece_10_bins':float(ece),'brier_multiclass':float(np.mean(np.sum(probs**2,axis=1)-2*probs[np.arange(len(y)),y]+1)),'nll':float(-np.log(np.maximum(probs[np.arange(len(y)),y],1e-15)).mean()),'calibration_bins':bins},cm,recall,f1,support

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sources',required=True);args=ap.parse_args();sources=Path(args.sources)
 (ROOT/'data_audit').mkdir(exist_ok=True);(ROOT/'experiments/results').mkdir(exist_ok=True)
 files=[];labels=[];featuremap=[];sets={};train_rows=[];baseline_headers=[];source15={};rawhashes={}
 for idx in range(11,17):
  p=sources/f'archive({idx}).zip';arc=p.name;sets[arc]=set();rawhashes[arc]=hashlib.sha256(p.read_bytes()).hexdigest()
  with zipfile.ZipFile(p) as z:
   for n in z.namelist():
    if not n.endswith('.csv'):continue
    with z.open(n) as raw:
     rd=csv.reader(io.TextIOWrapper(raw,encoding='utf-8-sig'));h=next(rd)
     di=next(i for i,c in enumerate(h) if c.lower() in ('disease','diseases','name','disease_name'))
     idcols=[i for i,c in enumerate(h) if c.lower()=='patient_id'];seen=set();seen_noid=set();count=0;names=set();sexc=collections.Counter();sexi=next((i for i,c in enumerate(h) if c.lower() in ('sex','gender')),None)
     dups={a:[i for i,v in enumerate(h) if v==a] for a,c in collections.Counter(h).items() if c>1};conflicts=collections.Counter();bad=0
     for row in rd:
      count+=1
      if len(row)!=len(h):bad+=1;continue
      seen.add(digest(row));seen_noid.add(digest([v for i,v in enumerate(row) if i not in idcols]));names.add(row[di]);sets[arc].add(norm(row[di]))
      if sexi is not None:sexc[row[sexi]]+=1
      for name,positions in dups.items():
       if len({row[i] for i in positions})>1:conflicts[name]+=1
      if idx==11:train_rows.append(row)
     rec={'archive':arc,'file':n,'rows':count,'columns':len(h),'disease_labels':len(names),'exact_unique_rows':len(seen),'exact_duplicate_rows':count-len(seen),'unique_profiles_excluding_patient_id':len(seen_noid),'repeated_profiles_excluding_patient_id':count-len(seen_noid),'malformed_rows':bad,'sex_counts':dict(sexc),'duplicate_header_count':len(dups),'duplicate_column_disagreement_rows':dict(conflicts)}
     files.append(rec);print(json.dumps({k:v for k,v in rec.items() if k!='duplicate_column_disagreement_rows'}),flush=True)
     for s in sorted(names):labels.append({'archive':arc,'file':n,'source_label':s,'normalized_label':norm(s),'candidate_disease_id':'dis_'+hashlib.sha256(norm(s).encode()).hexdigest()[:16],'mapping_status':'lexical_only_unreviewed'})
     if idx in (11,12,15,16) and len(h)>20:
      for i,c in enumerate(h):
       if i==di or c.lower() in ('patient_id','age','sex','symptom_count'):continue
       v=re.sub(r'^(rare_symptom_|symptom_)','',c);v=norm(v.replace('_',' '))
       featuremap.append({'archive':arc,'file':n,'column_index':i,'original_header':c,'candidate_term':v,'candidate_feature_id':'feat_'+hashlib.sha256(v.encode()).hexdigest()[:16],'mapping_status':'needs_semantic_review' if idx==15 or c in dups else 'lexical_only_unreviewed'})
     if idx==11:baseline_headers=h
     if idx==15:source15[n]=seen_noid
 overlap=[{'archive_a':a,'archive_b':b,'shared_lexical_labels':len(sets[a]&sets[b])} for a in sets for b in sets if a<b]
 summary={'normalization':'casefold + strip + collapse whitespace only; no semantic synonym merges','union_lexical_disease_labels':len(set.union(*sets.values())),'source_sha256':rawhashes,'files':files,'overlap':overlap,'archive15_train_test_shared_profiles_excluding_patient_id':len(source15['train.csv']&source15['test.csv']),'clinical_dedup_status':'not established; no cross-source patient identity inferred'}
 dump(ROOT/'data_audit/audit.json',summary);writecsv(ROOT/'data_audit/disease_mappings.csv',labels);writecsv(ROOT/'data_audit/feature_column_mappings.csv',featuremap);writecsv(ROOT/'data_audit/disease_overlap.csv',overlap)
 write_candidate_catalogs(labels,featuremap)
 # Archive 11: deduplicate exact label+feature rows. Split all identical feature vectors together.
 names=sorted({r[0] for r in train_rows});classidx={n:i for i,n in enumerate(names)};unique={tuple(r) for r in train_rows};rows=sorted(unique)
 X=np.asarray([[int(v) for v in r[1:]] for r in rows],dtype=np.float64);y=np.asarray([classidx[r[0]] for r in rows]);assert set(np.unique(X))<={0,1}
 groups=[hashlib.sha256(bytes(int(v) for v in r[1:])).hexdigest() for r in rows]
 split=np.asarray([int(g[:8],16)%100 for g in groups]);itr=np.where(split<70)[0];iva=np.where((split>=70)&(split<85))[0];ite=np.where(split>=85)[0]
 assert not(set(np.asarray(groups)[itr])&set(np.asarray(groups)[ite]))
 K=len(names)
 def fit(ids):
  cnt=np.bincount(y[ids],minlength=K).astype(float);fc=np.array([X[ids][y[ids]==c].sum(0) for c in range(K)]);p=(fc+1)/(cnt[:,None]+2)
  return np.log(p),np.log1p(-p),np.log((cnt+1)/(len(ids)+K))
 def predict(ids,model,mask=None):
  lp,ln,prior=model;a=X[ids];m=np.ones_like(a) if mask is None else mask
  score=(a*m)@lp.T+((1-a)*m)@ln.T+prior;score-=score.max(1,keepdims=True);probs=np.exp(score);return probs/probs.sum(1,keepdims=True)
 model=fit(itr);result={'dataset':'archive(11).zip only','model':'Bernoulli Naive Bayes; alpha=1; smoothed empirical training priors','clinical_validation':False,'binary_zero_semantics':'assumed negative for offline experiment only; not established by source documentation','raw_rows':len(train_rows),'unique_labeled_rows':len(rows),'feature_groups':len(set(groups)),'split':'SHA256 feature vector first 8 hex mod 100: <70 train, 70..84 validation, >=85 test','group_leakage':0,'classes':K,'features':X.shape[1],'splits':{},'missing_feature_experiment':[],'learning_curve':[]}
 for label,ids in [('train',itr),('validation',iva),('test',ite)]:
  met,cm,rec,f1,support=metrics(y[ids],predict(ids,model),K);result['splits'][label]=met;result['splits'][label]['classes_present']=len(set(y[ids]))
  if label=='test':
   np.save(ROOT/'experiments/results/confusion_matrix.npy',cm)
   writecsv(ROOT/'experiments/results/per_class.csv',[{'disease':names[c],'support':int(support[c]),'recall':float(rec[c]),'f1':float(f1[c])} for c in range(K)])
   failures=sorted([(int(cm[i,j]),names[i],names[j]) for i in range(K) for j in range(K) if i!=j and cm[i,j]],reverse=True)
   writecsv(ROOT/'experiments/results/confusions.csv',[{'count':n,'actual':a,'predicted':b} for n,a,b in failures]);result['top_confusions']=failures[:10]
   probs=predict(ids,model);wrong=np.where(probs.argmax(1)!=y[ids])[0]
   writecsv(ROOT/'experiments/results/failure_examples.csv',[{'feature_group':groups[ids[i]],'actual':names[y[ids[i]]],'predicted':names[probs[i].argmax()],'model_confidence_not_clinical_probability':float(probs[i].max()),'positive_features':'; '.join(baseline_headers[j+1] for j in np.where(X[ids[i]]==1)[0])} for i in wrong[:50]])
 rng=np.random.default_rng(42)
 for fraction in [1,.75,.5,.25]:
  mask=(rng.random((len(ite),X.shape[1]))<fraction).astype(float)
  met,*_=metrics(y[ite],predict(ite,model,mask),K);result['missing_feature_experiment'].append({'fraction_features_observed':fraction,'top1_accuracy':met['top1_accuracy'],'macro_f1':met['macro_f1']})
 for frac in [.1,.25,.5,1]:
  ids=itr[:max(1,int(len(itr)*frac))] if frac==1 else rng.choice(itr,max(1,int(len(itr)*frac)),replace=False)
  met,*_=metrics(y[iva],predict(iva,fit(ids)),K);result['learning_curve'].append({'training_rows':len(ids),'validation_accuracy':met['top1_accuracy']})
 majority=int(np.bincount(y[itr],minlength=K).argmax());result['majority_test_accuracy']=float(np.mean(y[ite]==majority))
 dump(ROOT/'experiments/results/metrics.json',result);dump(ROOT/'experiments/results/classes.json',names)
 np.savez_compressed(ROOT/'experiments/results/baseline_parameters.npz',log_positive=model[0],log_negative=model[1],log_prior=model[2])
 print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
