from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import json,csv,math,os
import numpy as np
R=Path(__file__).resolve().parents[1];M=json.loads((R/'experiments/results/metrics.json').read_text());A=json.loads((R/'data_audit/audit.json').read_text())
# Override FEELTRIVA_FONT and FEELTRIVA_BOLD_FONT on other platforms.
FONT=os.environ.get('FEELTRIVA_FONT','/System/Library/Fonts/Supplemental/Arial.ttf')
BOLD=os.environ.get('FEELTRIVA_BOLD_FONT','/System/Library/Fonts/Supplemental/Arial Bold.ttf')
if not Path(FONT).exists(): FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
if not Path(BOLD).exists(): BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
if not Path(FONT).exists(): raise SystemExit('Set FEELTRIVA_FONT and FEELTRIVA_BOLD_FONT to installed TrueType fonts.')
N='#142B43';GRAY='#617186';BLUE='#356EDD';TEAL='#068680';RED='#BF4D4D';PURPLE='#7957BE';BG='#F5F7FA'
def f(n,b=False):return ImageFont.truetype(BOLD if b else FONT,n)
def canvas(w,h):return Image.new('RGB',(w,h),BG)
def txt(d,x,y,s,n=28,c=N,b=False):d.text((x,y),s,font=f(n,b),fill=c)
def box(d,x,y,w,h):d.rounded_rectangle((x,y,x+w,y+h),18,fill='white',outline='#DAE2EC',width=2)
def wrap(d,s,w,n=28):
 out=[];line=''
 for word in s.split():
  a=(line+' '+word).strip()
  if d.textlength(a,font=f(n))>w and line:out.append(line);line=word
  else:line=a
 out.append(line);return out
def paragraph(d,x,y,s,w,n=28,c=GRAY):
 for line in wrap(d,s,w,n):txt(d,x,y,line,n,c);y+=n+9
 return y
def bars(d,x,y,w,items,maxv=1,color=BLUE,row=75,labelw=280):
 for i,(label,val) in enumerate(items):
  yy=y+i*row;txt(d,x,yy,label,27)
  d.rounded_rectangle((x+labelw,yy,x+labelw+w,yy+34),6,fill='#EEF2F7')
  if val>0:d.rounded_rectangle((x+labelw,yy,x+labelw+w*val/maxv,yy+34),6,fill=color)
  txt(d,x+labelw+w+18,yy,f'{val:.1%}',27,color,True)
def arrow(d,pts,c=GRAY):
 d.line(pts,fill=c,width=4)
 a,b=pts[-2:];ang=math.atan2(b[1]-a[1],b[0]-a[0]);sz=14
 d.polygon([b,(b[0]-sz*math.cos(ang-.5),b[1]-sz*math.sin(ang-.5)),(b[0]-sz*math.cos(ang+.5),b[1]-sz*math.sin(ang+.5))],fill=c)
# Baseline panel
im=canvas(2400,1940);d=ImageDraw.Draw(im)
txt(d,65,40,'Measured baseline: useful failure evidence',52,N,True)
txt(d,65,110,'Archive 11 only • Bernoulli Naive Bayes • experimental label prediction, not clinical accuracy',29,GRAY)
box(d,60,180,1120,490);txt(d,90,205,'TRAIN / VALIDATION / TEST',30,N,True)
bars(d,90,275,590,[(k.title()+f' (n={v["n"]:,})',v['top1_accuracy']) for k,v in M['splits'].items()],.5,row=85,labelw=300)
bars(d,90,545,590,[('Majority baseline',M['majority_test_accuracy'])],.5,color=RED,labelw=300)
txt(d,90,625,'Fixed profile-hash split; no identical feature groups cross splits.',24,GRAY)
box(d,1220,180,1120,490);txt(d,1250,205,'TEST METRICS AND COVERAGE',30,N,True)
y=275
for title,val in [('Top-1 accuracy',f"{M['splits']['test']['top1_accuracy']:.2%}"),('Top-3 accuracy',f"{M['splits']['test']['top3_accuracy']:.2%}"),('Macro F1 (39 supported classes)',f"{M['splits']['test']['macro_f1']:.3f}"),('Test label coverage','39 of 46 classes'),('Calibration ECE (10 bins)',f"{M['splits']['test']['ece_10_bins']:.3f}")]:
 txt(d,1250,y,title,29);txt(d,2080,y,val,30,RED if 'ECE' in title else BLUE,True);y+=64
box(d,60,710,1120,560);txt(d,90,740,'RANDOM FEATURE MASKING',30,N,True)
bars(d,90,810,590,[(f"{r['fraction_features_observed']:.0%} observed",r['top1_accuracy']) for r in M['missing_feature_experiment']],.5,row=85,labelw=300)
paragraph(d,90,1170,'Accuracy rises as features are hidden. Investigate the model/data; this is not evidence that fewer clinical questions are better.',1040,27)
box(d,1220,710,1120,560);txt(d,1250,740,'LARGEST TEST CONFUSIONS',30,N,True)
y=805
for count,a,b in M['top_confusions'][:5]:
 txt(d,1250,y,f'{count} cases',29,RED,True)
 paragraph(d,1440,y,a.replace('_',' ')+' → '+b.replace('_',' '),830,27,N);y+=80
box(d,60,1310,1120,480);txt(d,90,1340,'VALIDATION LEARNING CURVE',30,N,True)
bars(d,90,1410,590,[(f"{r['training_rows']:,} train rows",r['validation_accuracy']) for r in M['learning_curve']],.5,row=77,labelw=300)
box(d,1220,1310,1120,480);txt(d,1250,1340,'WHAT THIS EXPERIMENT DOES NOT TEST',30,N,True)
paragraph(d,1250,1410,'No clinical diagnoses or urgency outcomes were independently verified. No free-text chatbot, clinician triage, age/sex performance, external population, advanced model or full six-source system was evaluated.',1020,31)
paragraph(d,1250,1630,'Zero in the binary inputs was assumed negative for this experiment only. Source semantics and real/synthetic origin remain unverified.',1020,27)
txt(d,65,1840,'Decision: reject this baseline for clinical serving. Preserve it as a reproducible benchmark.',32,RED,True)
txt(d,65,1895,'Source: experiments/results/metrics.json • fixed alpha=1 • no tuning against test • 16 November 2026',25,GRAY)
im.save(R/'figures/baseline-results.png')
# all-class confusion matrix, row normalized
cm=np.load(R/'experiments/results/confusion_matrix.npy');names=json.loads((R/'experiments/results/classes.json').read_text());k=len(names)
im=canvas(2660,2440);d=ImageDraw.Draw(im);txt(d,60,35,'Where the baseline fails: all 46 labels',50,N,True)
txt(d,60,105,'Rows = actual label; columns = predicted label • darker blue = larger share within the actual class',28,GRAY)
x0,y0,cell=660,210,36
support=cm.sum(1);norm=np.divide(cm,support[:,None],out=np.zeros_like(cm,dtype=float),where=support[:,None]>0)
for i in range(k):
 txt(d,30,y0+i*cell+3,f'{i+1:02d} '+names[i].replace('_',' '),22)
 for j in range(k):
  v=norm[i,j];c=tuple(int(a*(1-v)+b*v) for a,b in zip((239,244,251),(35,91,184)))
  if support[i]==0:c=(218,220,223)
  d.rectangle((x0+j*cell,y0+i*cell,x0+(j+1)*cell-1,y0+(i+1)*cell-1),fill=c)
 txt(d,x0+i*cell+4,y0-37,str(i+1),20)
 txt(d,x0+k*cell+18,y0+i*cell+3,f'n={support[i]:,}',21,GRAY)
paragraph(d,60,1935,'Column numbers correspond to the row labels. Gray rows have no test examples; performance for those seven labels cannot be estimated from this test split. Values are normalized by row and are not clinical disease probabilities.',2480,31)
paragraph(d,60,2090,'Interpretation: the weak diagonal, large off-diagonal concentrations and missing test classes make the limitations visible. See per_class.csv for recall/F1/support, confusions.csv for all error pairs and failure_examples.csv for 50 exported model failures.',2480,31)
txt(d,60,2310,'Experimental archive-11 classifier. Clinical validation: not performed.',32,RED,True)
im.save(R/'figures/confusion-matrix.png')
# architecture
im=canvas(2400,2000);d=ImageDraw.Draw(im)
txt(d,60,40,'Feeltriva: product and data architecture',52,N,True)
txt(d,60,110,'Proposed coding target • clinical mode off until reviewed knowledge, rules and validation are available',29,GRAY)
def node(x,y,w,h,title,body,c=BLUE):
 box(d,x,y,w,h);txt(d,x+25,y+18,title,29,c,True);paragraph(d,x+25,y+68,body,w-50,27)
node(70,210,690,190,'WEB APPLICATION','Lovable / React + TypeScript • chat, corrections, evidence and summary export')
node(855,210,690,190,'PRODUCT MCP SERVER','Authenticated client tools • same application services as REST')
node(1640,210,690,190,'REVIEW CONSOLE','Approve mappings, evidence, rules, questions and release versions',TEAL)
arrow(d,[(415,400),(415,460),(1200,460),(1200,510)])
arrow(d,[(1200,400),(1200,510)])
node(470,530,1460,180,'API + CONTROLLED ASSESSMENT SERVICE','Ownership → version check → extraction/confirmation → urgency and scope gate. A failed or incomplete assessment never becomes reassurance.',TEAL)
arrow(d,[(1200,710),(1200,770)])
node(70,800,690,220,'RULES AND QUESTION POLICY','Reviewed urgency/scope rules first. Approved follow-ups selected by safety, relevance and burden.',TEAL)
node(855,800,690,220,'CANDIDATE RANKING','Transparent baseline → evaluated challengers → calibration + abstention. No unvalidated percentages.')
node(1640,800,690,220,'EVIDENCE RAG + LLM','Approved hybrid retrieval, reranking, bounded graph expansion and claim-level citation checks.',PURPLE)
arrow(d,[(1200,770),(415,770),(415,800)])
arrow(d,[(1200,770),(1200,800)])
arrow(d,[(1200,770),(1985,770),(1985,800)])
arrow(d,[(415,1020),(415,1080),(1200,1080),(1200,1120)])
arrow(d,[(1200,1020),(1200,1120)])
arrow(d,[(1985,1020),(1985,1080),(1200,1080)])
node(470,1140,1460,170,'VALIDATED RESPONSE + VERSIONED SESSION','Urgency, next action, provisional candidates, unknowns and evidence. Persist model / knowledge / rule / prompt versions.',TEAL)
node(70,1390,690,240,'SOURCE + NORMALIZED DATA','6 ZIPs → immutable records → 960 lexical disease groups → reviewed mappings. Raw duplicates retain lineage.')
node(855,1390,690,240,'SERVING KNOWLEDGE','PostgreSQL + pgvector / full-text search. Disease ↔ feature evidence; descriptions, causes and care statements.',TEAL)
node(1640,1390,690,240,'PRIVATE USER DATA','Separate sessions, observations and assessments. Consent, encryption, ownership and deletion; no default training use.',PURPLE)
arrow(d,[(760,1510),(855,1510)],TEAL)
arrow(d,[(1200,1390),(1200,1310)],TEAL)
arrow(d,[(1985,1390),(1985,1220),(1930,1220)],PURPLE)
node(70,1710,1090,200,'OFFLINE EVALUATION + RELEASE REGISTRY','Leakage-controlled splits • clinical and subgroup evals • model/data cards • monitoring • rollback',TEAL)
node(1240,1710,1090,200,'GITNEXUS: DEVELOPER CODE GRAPH','Indexes symbols, calls and routes. Separate from the medical graph; excludes private health data and model artifacts.',PURPLE)
im.save(R/'figures/technical-architecture.png')
# Reliability diagram using measured equal-width confidence bins.
im=canvas(2000,1450);d=ImageDraw.Draw(im)
txt(d,60,40,'Confident predictions, weak correctness',48,N,True)
txt(d,60,110,'Archive 11 test set • Bernoulli baseline • confidence is not a clinical probability',27,GRAY)
x,y,w,h=170,240,1040,940
for t in np.linspace(0,1,6):
    xx=x+t*w; yy=y+h-t*h
    d.line((x,yy,x+w,yy),fill='#DEE5EE',width=2)
    txt(d,80,yy-12,f'{t:.0%}',25,GRAY)
    txt(d,xx-20,y+h+20,f'{t:.0%}',25,GRAY)
d.line((x,y+h,x+w,y),fill=GRAY,width=4)
points=[]
for b in M['splits']['test']['calibration_bins']:
    xx=x+b['mean_confidence']*w; yy=y+h-b['accuracy']*h
    points.append((xx,yy))
d.line(points,fill=RED,width=6)
for xx,yy in points:d.ellipse((xx-9,yy-9,xx+9,yy+9),fill=RED)
txt(d,175,195,'Observed correctness',27,N,True)
txt(d,450,y+h+80,'Mean model confidence per bin',28,N,True)
box(d,1300,240,620,560)
txt(d,1330,270,'MEASURED RESULT',29,RED,True)
paragraph(d,1330,340,'The highest-confidence bin contains 6,048 test examples. Mean confidence is 97.48%, but only 19.58% are correct against the dataset label.',550,31)
paragraph(d,1330,580,'ECE = 0.613 across 10 equal-width bins. Empty bins are omitted. Gray diagonal = ideal agreement.',550,29)
paragraph(d,1310,880,'No calibration was fitted. This plot exposes a failure of this model, not uncertainty that can be fixed by changing UI wording.',570,30)
paragraph(d,65,1350,'Do not show these scores as a user\'s disease risk. Calibration must be fitted separately and evaluated on independent, relevant data.',1870,28,RED)
im.save(R/'figures/calibration.png')
# Source and relational mapping overview; overlaps between source families are intentional.
im=canvas(2400,2020);d=ImageDraw.Draw(im)
txt(d,60,40,'How the six datasets become one product',52,N,True)
txt(d,60,110,'Full union with source lineage • lexical dedup completed • clinical semantic mapping still requires review',28,GRAY)
node(70,210,690,220,'CASE / FEATURE SOURCES','11: binary symptoms; 12: matrix + symptom text; 14: symptom lists; 15: E_* questions; 16: symptom matrix')
node(855,210,690,220,'NARRATIVE SOURCES','13: disease summaries, causes, symptoms and treatments; 16: descriptions + source URLs',TEAL)
node(1640,210,690,220,'DEMOGRAPHIC CONTEXT','14: Age and Gender; 15: AGE and SEX. Keep field meanings and source sample counts separate.',PURPLE)
for xx in [415,1200,1985]: arrow(d,[(xx,430),(xx,480),(1200,480),(1200,520)])
node(470,540,1460,170,'IMMUTABLE SOURCE RECORDS + REVIEW QUEUE','Source/version, file/row, checksum, original terms and values. Retain duplicates, conflicting columns, unknowns and all attributions.',TEAL)
for xx in [415,1200,1985]: arrow(d,[(1200,710),(1200,760),(xx,760),(xx,800)])
node(70,820,690,220,'DISEASE MASTER + ALIASES','960 lexical candidate groups. Source labels → disease mappings → stable disease IDs. Semantic merges require review.')
node(855,820,690,220,'FEATURE MASTER + MAPPINGS','1,651 matrix column mappings → 958 lexical candidates. Include symptoms, history, risk and measurements.',TEAL)
node(1640,820,690,220,'SOURCED CARE STATEMENTS','Descriptions, causes, treatment/management text and applicability. A treatment mention is not a cure.',PURPLE)
arrow(d,[(415,1040),(415,1100),(760,1100),(760,1160)])
arrow(d,[(1200,1040),(1200,1100),(760,1100)])
arrow(d,[(1985,1040),(1985,1100),(1700,1100),(1700,1160)])
node(70,1180,1120,250,'CASE FEATURES + DISEASE-FEATURE EVIDENCE','Imported cases link labels and feature values. Reviewed disease-feature assertions retain supporting records or statements. These are different relationships; co-occurrence alone is not clinical proof.',TEAL)
node(1250,1180,1080,250,'KNOWLEDGE RELEASE + RETRIEVAL','Approved statements and edges become a versioned serving corpus. Retrieval uses disease/feature IDs, population, dates, permissions and citations.',PURPLE)
arrow(d,[(1190,1305),(1250,1305)],TEAL)
arrow(d,[(1790,1430),(1790,1490),(1200,1490),(1200,1530)])
node(470,1550,1460,220,'PRIVATE USER SESSION → ASSESSMENT','Confirmed observations + relevant context + approved rules + evidence → next question, provisional explanations or abstention. Persist observation, knowledge, rule and model versions.',TEAL)
paragraph(d,75,1850,'Medical evidence graph: diseases, features and sourced statements. GitNexus graph: software symbols, calls and routes. They remain separate. User sessions are not automatically added to training data.',2250,32)
im.save(R/'figures/data-relationships.png')
