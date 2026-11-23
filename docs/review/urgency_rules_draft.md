# Urgency rules: review document

> **Not shown to anyone.** These rules reach a person only from a published release with clinical mode switched on. Neither exists yet.
> Written by the engineering assistant on the owner's instruction (decision E39), not by a clinician. Approved by the owner on 2026-11-23 without a doctor's review. It is not a validated triage protocol.
> Decisions on the rules are recorded in the system, with the name of who decided and the time, not in this document. The history at the end says what the owner decided.

Rule set `urgency-draft-1` for India, written 2026-11-20. This document is generated from `packages/clinical/feeltriva_clinical/drafts/urgency_draft.json`: change the file, not this text. The finished text for approval, without the working notes, is in [urgency_rules_final.md](urgency_rules_final.md).

## 1. At a glance

20 rules: 12 emergency and 8 urgent, over 85 features of the vocabulary, resting on 19 published pages.

| No. | Rule | Level |
|---:|---|---|
| 1 | [Chest pain with signs of a heart attack](#rule-1) | Emergency |
| 2 | [Severe breathing difficulty](#rule-2) | Emergency |
| 3 | [Signs of a stroke](#rule-3) | Emergency |
| 4 | [Seizure (fit)](#rule-4) | Emergency |
| 5 | [Loss of consciousness with other warning signs](#rule-5) | Emergency |
| 6 | [Bleeding that is heavy or will not stop](#rule-6) | Emergency |
| 7 | [Vomiting blood with other warning signs](#rule-7) | Emergency |
| 8 | [Coughing up blood with other warning signs](#rule-8) | Emergency |
| 9 | [Signs of a severe allergic reaction](#rule-9) | Emergency |
| 10 | [Thoughts of suicide or self-harm](#rule-10) | Emergency |
| 11 | [Stiff neck or headache with signs of a serious infection](#rule-11) | Emergency |
| 12 | [Bleeding in pregnancy with fainting or dizziness](#rule-12) | Emergency |
| 13 | [Chest pain or chest tightness](#rule-13) | Urgent |
| 14 | [Breathing difficulty](#rule-14) | Urgent |
| 15 | [Fainting or loss of consciousness](#rule-15) | Urgent |
| 16 | [Vomiting blood](#rule-16) | Urgent |
| 17 | [Coughing up blood](#rule-17) | Urgent |
| 18 | [Black stools, bloody diarrhoea or bleeding in the gut](#rule-18) | Urgent |
| 19 | [Confusion](#rule-19) | Urgent |
| 20 | [Bleeding or spotting in pregnancy](#rule-20) | Urgent |

## 2. How the rules behave

- The rules are checked on every new or corrected answer, before any possible explanation is looked for.
- A rule fires only when what has been recorded makes its condition true. A symptom nobody has asked about is unknown: it counts neither as present nor as absent.
- Emergency rules are checked before urgent ones. The first rule that fires decides the text shown.
- When a rule fires, the assessment stops asking routine questions and shows the rule's text first.
- No rule uses a number as a threshold. Each asks only whether named symptoms are present.
- The service does not load these rules today. It loads only the synthetic sample release.

## 3. The two levels

| Level | Meaning | Rules |
|---|---|---:|
| Emergency | The published advice is an ambulance or an emergency department now. | 12 |
| Urgent | The published advice is help the same day, with an ambulance if named signs appear. | 8 |

## 4. Telephone numbers named in the texts

| Number | What it is | Quoted from | Confirmed by the owner |
|---|---|---|---|
| **112** | The single emergency number for the whole of India (Emergency Response Support System) | [Kerala Police (Government of Kerala)](https://keralapolice.gov.in/home/page/award/10) | 2026-11-23 |
| **14416** | Tele MANAS mental health helpline: toll-free, 24 hours a day, every day | [Dhubri Medical College & Hospital (Government of Assam)](https://dhubri-mch.assam.gov.in/services/tele-manas-call-14416-24%C3%977-mental-health-helpline); [JIPMER (an institute of the Government of India)](https://jipmer.edu.in/Tele-MANAS) | 2026-11-23 |

No other number appears in any text shown. A check refuses a draft whose texts name a number not listed here.

## 5. Still open

1. No doctor has reviewed the rules. The owner approved them on 2026-11-23 without such a review. A review by a doctor practising in India remains advised before clinical mode is switched on.
2. The ambulance number 108 is not used: no official page stating it could be read, and the ambulance number differs between states. The owner has not asked for it.

## 6. Weaknesses that remain whatever is decided

- The rules were written by an engineering assistant, not by a clinician.
- The rules have not been tried on a single real case. No urgency labels exist, so nobody knows how often a rule would fire when it should not, or stay silent when it should fire.
- The vocabulary records that a symptom is present, not how severe or how sudden it is. Where that decides the level, the rule escalates. Some people will be told to seek emergency care who did not need it.
- A rule fires only on what has been recorded as present. A warning sign that the person has but was not asked about, or described in words the system did not recognise, fires nothing.
- Several features from different sources mean the same thing and are joined inside the rules, because no synonym has been approved yet. A feature added to the vocabulary later is not part of any rule until the rule is edited.
- Emergency care, common illnesses and the words people use for symptoms differ between England and India. The published advice was not adapted beyond the telephone numbers.

## 7. Published warning signs the rules do not cover

| Published warning sign | Why there is no rule |
|---|---|
| How severe or how sudden a symptom is (severe pain, sudden headache, sudden swelling) | the feature vocabulary records that a symptom is present, not its severity or onset |
| Choking on food or an object, serious injury, burns, poisoning or overdose | no feature in the vocabulary |
| A rash that does not fade when pressed; the other signs of sepsis | no feature in the vocabulary |
| Weakness or numbness down one side of the body; sudden loss of vision | the vocabulary has only general weakness, numbness and vision features, which are common without a stroke |
| Labour and childbirth; warning signs in babies and children | outside what the product assesses (adults; no pregnancy flows) |
| Blood in the stool that is not black, dark red or with diarrhoea | the published advice is a routine appointment, not an urgent one |

## 8. The rules

<a id="rule-1"></a>
### Rule 1. Chest pain with signs of a heart attack

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.chest_pain_emergency` | 1 of 20 |

**Fires when**

- **any one of these is enough:**
  - “chest pain with pressure”
  - **all of these together:**
    - any one of: “chest pain”; “Do you have chest pain even at rest?”; “sharp chest pain”; “burning chest pain”; “exertional chest pain”; “pleuritic chest pain”; “chest pain with pressure”
    - any one of: “chest tightness”; “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”; “sweating”; “Have you had significantly increased sweating?”; “nausea”; “vomiting”; “Are you feeling nauseous or do you feel like vomiting?”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “Do you feel slightly dizzy or lightheaded?”; “arm pain”; “jaw pain”; “neck pain”

**The person is shown**

> Chest pain that feels like pressure or tightness, or chest pain together with breathlessness, sweating, feeling sick or light-headed, or pain in an arm, the neck or the jaw, can be a sign of a heart attack. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** The published advice is to call an ambulance straight away for exactly these combinations.

**Checked with two cases**

- Fires: recorded as present “chest pain”; “sweating”.
- Does not fire: recorded as present “chest pain”; recorded as absent “chest tightness”; “shortness of breath”; “sweating”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “arm pain”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Chest pain](https://www.nhs.uk/symptoms/chest-pain/), page last reviewed 08 August 2023:
  - “Call 999 if:”
  - “you get sudden pain or discomfort in your chest that does not go away – the pain can feel like squeezing or pressure inside your chest, burning or indigestion”
  - “you get pain that spreads to your left or right arm, or your neck, jaw, stomach or back”
  - “you have chest pain and you feel sweaty, sick, light headed or short of breath”
  - “You could be having a heart attack. Call 999 straight away as you need immediate treatment in hospital.”
  - “Most chest pain is not a sign of anything serious but get medical advice just in case.”
- NHS (National Health Service, England), [Heart attack: symptoms](https://www.nhs.uk/conditions/heart-attack/symptoms/), page last reviewed 31 March 2026:
  - “you have chest pain that feels tight or like squeezing on your chest”
  - “you have chest pain that's spreading to your arms, neck or jaw”
  - “Do not drive yourself to A&E.”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-2"></a>
### Rule 2. Severe breathing difficulty

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.breathing_emergency` | 2 of 20 |

**Fires when**

- **any one of these is enough:**
  - any one of: “Do you feel like you are (or were) choking or suffocating?”; “cyanosis”
  - **all of these together:**
    - any one of: “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”
    - any one of: “chest tightness”; “chest pain with pressure”; “Is your skin much paler than usual?”; “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”; “arm pain”; “jaw pain”; “neck pain”

**The person is shown**

> A feeling of choking or suffocating, blue lips or skin, or breathing difficulty together with a tight or heavy chest, very pale skin, sudden confusion or pain in an arm, the neck or the jaw, needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** Published as reasons to call an ambulance. The vocabulary has no feature for how severe the breathlessness is, so breathlessness alone is placed one level lower (see the rule on breathing difficulty).

**Checked with two cases**

- Fires: recorded as present “Do you feel like you are (or were) choking or suffocating?”.
- Does not fire: recorded as present “shortness of breath”; recorded as absent “chest tightness”; “chest pain with pressure”; “Is your skin much paler than usual?”; “confusion symptom”; “arm pain”; “Do you feel like you are (or were) choking or suffocating?”; “cyanosis”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Shortness of breath](https://www.nhs.uk/symptoms/shortness-of-breath/), page last reviewed 30 January 2024:
  - “Call 999 or go to A&E immediately if:”
  - “you have severe difficulty breathing – you’re gasping, choking or not able to get words out”
  - “your chest feels tight or heavy”
  - “you have pain that spreads to your arms, back, neck and jaw”
  - “your lips or skin are turning very pale, blue or grey”
  - “you feel suddenly confused”
  - “Contact NHS 111 if:”
  - “you have difficulty breathing – you may be more short of breath than usual”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-3"></a>
### Rule 3. Signs of a stroke

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.stroke_signs` | 3 of 20 |

**Fires when**

- any one of: “facial droop”; “Have you had weakness or paralysis on one side of the face, which may still be present or completely resolved?”; “arm weakness”; “slurred speech”; “slurring words”; “speech difficulty”; “Do you have difficulty articulating words/speaking?”; “focal weakness”; “paralysis”; “paralysed body”; “Did you previously, or do you currently, have any weakness/paralysis in one or more of your limbs or in your face?”

**The person is shown**

> Weakness or drooping on one side of the face, weakness in an arm or a leg, or slurred or difficult speech can be signs of a stroke, even if they have now stopped. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** The published advice is to call an ambulance for any of these signs, also when they have stopped. The vocabulary cannot say whether a weakness is new, so any report of one of these signs escalates.

**Checked with two cases**

- Fires: recorded as present “facial droop”.
- Does not fire: recorded as present “headache”; recorded as absent “facial droop”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Symptoms of a stroke](https://www.nhs.uk/conditions/stroke/symptoms/), page last reviewed 12 September 2024:
  - “face weakness – one side of your face may droop (fall) and it might be hard to smile”
  - “arm weakness – you may not be able to fully lift both arms and keep them there because of weakness or numbness in 1 arm”
  - “speech problems – you may slur your words or sound confused”
  - “weakness or numbness down 1 side of your body”
  - “you've had signs of a stroke within the last 24 hours even if they've now stopped”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-4"></a>
### Rule 4. Seizure (fit)

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.seizure` | 4 of 20 |

**Fires when**

- any one of: “seizures”; “seizures symptom”; “Have you lost consciousness associated with violent and sustained muscle contractions or had an absence episode?”; “sudden uncontrolled electrical disturbances in the brain”

**The person is shown**

> A seizure (fit) needs emergency help when it is a first seizure, lasts more than 5 minutes, repeats, or the person does not fully recover. If you are not sure, treat it as an emergency. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** The published advice is an ambulance for a first seizure. The vocabulary cannot say whether a seizure is the first one, so every reported seizure escalates. People with known epilepsy do not always need an ambulance.

**Checked with two cases**

- Fires: recorded as present “seizures”.
- Does not fire: recorded as present “headache”; recorded as absent “seizures”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [What to do if someone has a seizure (fit)](https://www.nhs.uk/symptoms/what-to-do-if-someone-has-a-seizure-fit/), page last reviewed 19 December 2023:
  - “Call 999 and ask for an ambulance if:”
  - “it's the first time someone has had a seizure”
  - “the seizure lasts more than 5 minutes, if you do not know how long their seizures usually last”
  - “the person does not regain full consciousness, or has several seizures without regaining consciousness”
  - “People with epilepsy do not always need an ambulance or to go to hospital every time they have a seizure.”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-5"></a>
### Rule 5. Loss of consciousness with other warning signs

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.loss_of_consciousness_emergency` | 5 of 20 |

**Fires when**

- **any one of these is enough:**
  - “coma”
  - **all of these together:**
    - any one of: “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”
    - any one of: “chest pain”; “Do you have chest pain even at rest?”; “sharp chest pain”; “burning chest pain”; “exertional chest pain”; “pleuritic chest pain”; “chest pain with pressure”; “palpitations”; “Do you feel your heart is beating fast (racing), irregularly (missing a beat) or do you feel palpitations?”; “irregular heartbeat”; “fast heart rate”; “seizures”; “seizures symptom”; “Have you lost consciousness associated with violent and sustained muscle contractions or had an absence episode?”; “sudden uncontrolled electrical disturbances in the brain”; “facial droop”; “Have you had weakness or paralysis on one side of the face, which may still be present or completely resolved?”; “arm weakness”; “slurred speech”; “slurring words”; “speech difficulty”; “Do you have difficulty articulating words/speaking?”; “focal weakness”; “paralysis”; “paralysed body”; “Did you previously, or do you currently, have any weakness/paralysis in one or more of your limbs or in your face?”; “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”

**The person is shown**

> Losing consciousness together with chest pain, a racing or irregular heartbeat, a seizure, difficulty with speech or movement, or breathing difficulty needs immediate help. So does anyone who cannot be woken. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** Published as reasons to call an ambulance after a faint.

**Checked with two cases**

- Fires: recorded as present “loss of consciousness”; “palpitations”.
- Does not fire: recorded as present “loss of consciousness”; recorded as absent “chest pain”; “palpitations”; “seizures”; “facial droop”; “shortness of breath”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Fainting](https://www.nhs.uk/symptoms/fainting/), page last reviewed 17 August 2026:
  - “See a GP if:”
  - “you have fainted”
  - “Call 999 if someone:”
  - “cannot be woken up within 1 minute”
  - “has not fully recovered or has difficulty with speech or movement”
  - “has chest pain or a pounding, fluttering or irregular heartbeat (heart palpitations)”
  - “is shaking or jerking (having a seizure or fit)”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-6"></a>
### Rule 6. Bleeding that is heavy or will not stop

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.heavy_bleeding` | 6 of 20 |

**Fires when**

- any one of: “excessive bleeding”; “prolonged bleeding”

**The person is shown**

> Bleeding that is heavy or that you cannot stop needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** Published as a reason to call an ambulance or go to an emergency department.

**Checked with two cases**

- Fires: recorded as present “excessive bleeding”.
- Does not fire: recorded as present “headache”; recorded as absent “excessive bleeding”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Cuts and grazes](https://www.nhs.uk/conditions/cuts-and-grazes/), page last reviewed 02 April 2026:
  - “Call 999 or go to A&E if:”
  - “you have a cut and cannot stop the bleeding”
  - “the blood comes out in spurts and is bright red and hard to control”
- NHS (National Health Service, England), [Bleeding from the bottom (rectal bleeding)](https://www.nhs.uk/symptoms/bleeding-from-the-bottom-rectal-bleeding/), page last reviewed 12 April 2023:
  - “Ask for an urgent GP appointment or get help from NHS 111 if:”
  - “your poo is black or dark red”
  - “you have bloody diarrhoea”
  - “Go to A&E or call 999 if:”
  - “you're bleeding non-stop”
  - “there's a lot of blood – for example, the toilet water turns red or you see large blood clots”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-7"></a>
### Rule 7. Vomiting blood with other warning signs

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.vomiting_blood_emergency` | 7 of 20 |

**Fires when**

- **all of these together:**
  - any one of: “vomiting blood”; “hematemesis”; “Have you recently thrown up blood or something resembling coffee beans?”
  - any one of: “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “Do you feel slightly dizzy or lightheaded?”; “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”; “clammy skin”; “rapid breathing”; “breathing fast”; “melena”; “Have you recently had stools that were black (like coal)?”

**The person is shown**

> Vomiting blood together with feeling faint, dizzy or confused, fast breathing, cold clammy skin or black stools needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** Published as reasons to call an ambulance when someone is vomiting blood.

**Checked with two cases**

- Fires: recorded as present “vomiting blood”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”.
- Does not fire: recorded as present “vomiting blood”; recorded as absent “confusion symptom”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “loss of consciousness”; “clammy skin”; “melena”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Vomiting blood](https://www.nhs.uk/symptoms/vomiting-blood/), page last reviewed 18 August 2025:
  - “Call 999 or go to A&E if:”
  - “You or your child are vomiting blood (or have vomited blood) and:”
  - “feel confused”
  - “feel faint or dizzy”
  - “have rapid or shallow breathing”
  - “have cold, clammy, pale skin”
  - “have black poo”
  - “If you have stopped vomiting blood and had no other symptoms, ask for an urgent GP appointment, call 111 or get help from 111 online.”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-8"></a>
### Rule 8. Coughing up blood with other warning signs

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.coughing_blood_emergency` | 8 of 20 |

**Fires when**

- **all of these together:**
  - any one of: “coughing blood”; “hemoptysis”; “blood in sputum”; “Have you been coughing up blood?”
  - any one of: “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”; “Do you feel like you are (or were) choking or suffocating?”; “chest pain”; “Do you have chest pain even at rest?”; “sharp chest pain”; “burning chest pain”; “exertional chest pain”; “pleuritic chest pain”; “chest pain with pressure”; “palpitations”; “Do you feel your heart is beating fast (racing), irregularly (missing a beat) or do you feel palpitations?”; “irregular heartbeat”; “fast heart rate”

**The person is shown**

> Coughing up blood together with difficulty breathing, a very fast heartbeat or chest pain needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** Published as reasons to call an ambulance when someone is coughing up blood.

**Checked with two cases**

- Fires: recorded as present “coughing blood”; “shortness of breath”.
- Does not fire: recorded as present “coughing blood”; recorded as absent “shortness of breath”; “Do you feel like you are (or were) choking or suffocating?”; “chest pain”; “palpitations”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Coughing up blood (blood in phlegm)](https://www.nhs.uk/symptoms/coughing-up-blood/), page last reviewed 13 June 2024:
  - “Ask for an urgent GP appointment or get help from NHS 111 if:”
  - “you've coughed up a few small spots, flecks or streaks of blood, or noticed blood in your phlegm or handkerchief”
  - “you're coughing up more than just a few spots or streaks of blood”
  - “you're coughing up blood and finding it hard to breathe, have a very fast heartbeat or have pain in your chest or upper back”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-9"></a>
### Rule 9. Signs of a severe allergic reaction

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.severe_allergic_reaction` | 9 of 20 |

**Fires when**

- **any one of these is enough:**
  - any one of: “lip swelling”; “throat swelling”
  - **all of these together:**
    - any one of: “allergic reaction”; “Have you been in contact with or ate something that you have an allergy to?”
    - any one of: “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”; “Do you feel like you are (or were) choking or suffocating?”; “difficulty in swallowing”; “difficulty swallowing”; “Do you have difficulty swallowing, or have a feeling of discomfort/blockage when swallowing?”; “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “Do you feel slightly dizzy or lightheaded?”; “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”; “cyanosis”

**The person is shown**

> Swelling of the lips or throat, or an allergic reaction together with difficulty breathing or swallowing, confusion, dizziness or fainting, can be a severe allergic reaction. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** Published as reasons to call an ambulance. The vocabulary cannot say whether a swelling is sudden, so any reported swelling of the lips or throat escalates.

**Checked with two cases**

- Fires: recorded as present “allergic reaction”; “difficulty in swallowing”.
- Does not fire: recorded as present “allergic reaction”; recorded as absent “shortness of breath”; “Do you feel like you are (or were) choking or suffocating?”; “difficulty in swallowing”; “confusion symptom”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “loss of consciousness”; “cyanosis”; “lip swelling”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Anaphylaxis](https://www.nhs.uk/conditions/anaphylaxis/), page last reviewed 21 June 2023:
  - “Call 999 if:”
  - “your lips, mouth, throat or tongue suddenly become swollen”
  - “you're breathing very fast or struggling to breathe (you may become very wheezy or feel like you're choking or gasping for air)”
  - “your throat feels tight or you're struggling to swallow”
  - “you suddenly become very confused, drowsy or dizzy”
  - “someone faints and cannot be woken up”
  - “These can be signs of a serious allergic reaction and may need immediate treatment in hospital.”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-10"></a>
### Rule 10. Thoughts of suicide or self-harm

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.thoughts_of_self_harm` | 10 of 20 |

**Fires when**

- “suicidal ideation”

**The person is shown**

> You do not have to face this alone, and help is available right now. If you have harmed yourself or feel you may be about to, call 112 now or go to the nearest hospital emergency department, or ask someone to take you. You can also speak to a trained counsellor free of charge at any time on Tele MANAS: call 14416.

**Why this level.** The published advice is to tell someone and, where there is harm or a risk of it, to call an ambulance. The highest level is used so that this text is shown before anything else.

**Checked with two cases**

- Fires: recorded as present “suicidal ideation”.
- Does not fire: recorded as present “headache”; recorded as absent “suicidal ideation”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Help for suicidal thoughts](https://www.nhs.uk/mental-health/feelings-symptoms-behaviours/behaviours/help-for-suicidal-thoughts/), page last reviewed 26 April 2024:
  - “If you're feeling like you want to end your life, it's important to tell someone.”
  - “Help and support is available right now if you need it. You do not have to struggle with difficult feelings alone.”
  - “If you have seriously harmed yourself – for example, by taking a drug overdose – or you feel that you may be about to harm yourself, call 999 for an ambulance or go straight to A&E.”
- Dhubri Medical College & Hospital (Government of Assam), [TELE MANAS (Call 14416 | 24×7 Mental Health Helpline)](https://dhubri-mch.assam.gov.in/services/tele-manas-call-14416-24%C3%977-mental-health-helpline):
  - “TELE MANAS (Call 14416 | 24×7 Mental Health Helpline)”
  - “toll-free helpline number 14416 or 1-800-891-4416”
- JIPMER (an institute of the Government of India), [Tele MANAS](https://jipmer.edu.in/Tele-MANAS):
  - “Toll-Free Mental Health Helpline Number: 14416”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-11"></a>
### Rule 11. Stiff neck or headache with signs of a serious infection

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.meningitis_signs` | 11 of 20 |

**Fires when**

- **any one of these is enough:**
  - **all of these together:**
    - any one of: “stiff neck”; “neck stiffness or tightness”
    - any one of: “photophobia”; “sensitivity to light”
  - **all of these together:**
    - any one of: “headache”; “frontal headache”
    - any one of: “stiff neck”; “neck stiffness or tightness”; “photophobia”; “sensitivity to light”; “high fever”; “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”

**The person is shown**

> A stiff neck with a dislike of bright lights, or a headache together with a stiff neck, a dislike of bright lights, a very high temperature or confusion, can be signs of a serious infection. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** Published as reasons to call an ambulance or go to an emergency department.

**Checked with two cases**

- Fires: recorded as present “headache”; “stiff neck”.
- Does not fire: recorded as present “headache”; recorded as absent “stiff neck”; “photophobia”; “high fever”; “confusion symptom”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Meningitis: symptoms](https://www.nhs.uk/conditions/meningitis/symptoms/), page last reviewed 12 June 2026:
  - “Call 999 or go to A&E if:”
  - “has a stiff neck and cannot look at bright lights”
  - “is confused, has slurred speech, or is not making sense”
- NHS (National Health Service, England), [Headaches](https://www.nhs.uk/symptoms/headaches/), page last reviewed 17 April 2024:
  - “Call 999 or go to A&E if:”
  - “You or a child has a headache and:”
  - “are drowsy or confused”
  - “has a very high temperature, a stiff neck, or bright lights are bothering you”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-12"></a>
### Rule 12. Bleeding in pregnancy with fainting or dizziness

| Level | Identifier | Checked in position |
|---|---|---:|
| **Emergency** | `urg.draft.pregnancy_bleeding_emergency` | 12 of 20 |

**Fires when**

- **all of these together:**
  - “spotting or bleeding during pregnancy”
  - any one of: “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “Do you feel slightly dizzy or lightheaded?”

**The person is shown**

> Bleeding in pregnancy together with feeling faint or dizzy, or losing consciousness, needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.

**Why this level.** Published as a reason to call an ambulance. Pregnancy is outside what the product assesses, but an escalation is still shown.

**Checked with two cases**

- Fires: recorded as present “spotting or bleeding during pregnancy”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”.
- Does not fire: recorded as present “spotting or bleeding during pregnancy”; recorded as absent “loss of consciousness”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Vaginal bleeding in pregnancy](https://www.nhs.uk/pregnancy/related-conditions/common-symptoms/vaginal-bleeding/), page last reviewed 17 February 2026:
  - “You're pregnant and have light bleeding or spotting with:”
  - “You're pregnant and bleeding and:”
  - “you feel sick, faint, dizzy or lose consciousness”
  - “the bleeding is heavy (soaking a period pad soon after putting it on)”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-13"></a>
### Rule 13. Chest pain or chest tightness

| Level | Identifier | Checked in position |
|---|---|---:|
| **Urgent** | `urg.draft.chest_pain` | 13 of 20 |

**Fires when**

- any one of: “chest pain”; “Do you have chest pain even at rest?”; “sharp chest pain”; “burning chest pain”; “exertional chest pain”; “pleuritic chest pain”; “chest pain with pressure”; “chest tightness”

**The person is shown**

> Chest pain should be checked by a doctor even when it is probably nothing serious. Please see a doctor today. Call 112 at once if the pain does not go away, feels like pressure or tightness, spreads to an arm, the neck or the jaw, or comes with breathlessness, sweating or feeling sick.

**Why this level.** The published advice for chest pain without the heart-attack signs is to see a doctor, not an ambulance. The draft asks for the same day and names the signs that need 112.

**Checked with two cases**

- Fires: recorded as present “chest pain”.
- Does not fire: recorded as present “headache”; recorded as absent “chest pain”; “chest tightness”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Chest pain](https://www.nhs.uk/symptoms/chest-pain/), page last reviewed 08 August 2023:
  - “Call 999 if:”
  - “you get sudden pain or discomfort in your chest that does not go away – the pain can feel like squeezing or pressure inside your chest, burning or indigestion”
  - “you get pain that spreads to your left or right arm, or your neck, jaw, stomach or back”
  - “you have chest pain and you feel sweaty, sick, light headed or short of breath”
  - “You could be having a heart attack. Call 999 straight away as you need immediate treatment in hospital.”
  - “Most chest pain is not a sign of anything serious but get medical advice just in case.”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-14"></a>
### Rule 14. Breathing difficulty

| Level | Identifier | Checked in position |
|---|---|---:|
| **Urgent** | `urg.draft.breathing_difficulty` | 14 of 20 |

**Fires when**

- any one of: “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”

**The person is shown**

> Difficulty breathing, or being more short of breath than usual, should be checked today. Please see a doctor today. Call 112 at once if you are gasping, cannot get words out, your chest feels tight or heavy, your lips or skin turn blue or very pale, or you feel suddenly confused.

**Why this level.** The published advice for breathing difficulty without the severe signs is urgent advice the same day.

**Checked with two cases**

- Fires: recorded as present “shortness of breath”.
- Does not fire: recorded as present “headache”; recorded as absent “shortness of breath”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Shortness of breath](https://www.nhs.uk/symptoms/shortness-of-breath/), page last reviewed 30 January 2024:
  - “Call 999 or go to A&E immediately if:”
  - “you have severe difficulty breathing – you’re gasping, choking or not able to get words out”
  - “your chest feels tight or heavy”
  - “you have pain that spreads to your arms, back, neck and jaw”
  - “your lips or skin are turning very pale, blue or grey”
  - “you feel suddenly confused”
  - “Contact NHS 111 if:”
  - “you have difficulty breathing – you may be more short of breath than usual”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-15"></a>
### Rule 15. Fainting or loss of consciousness

| Level | Identifier | Checked in position |
|---|---|---:|
| **Urgent** | `urg.draft.fainting` | 15 of 20 |

**Fires when**

- any one of: “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”

**The person is shown**

> Fainting or losing consciousness should be checked by a doctor to find out what caused it. Please see a doctor today. Call 112 at once if it comes with chest pain, a racing or irregular heartbeat, a seizure, or difficulty with speech or movement, or if you have not fully recovered.

**Why this level.** The published advice after a simple faint is to see a doctor. The draft asks for the same day.

**Checked with two cases**

- Fires: recorded as present “loss of consciousness”.
- Does not fire: recorded as present “headache”; recorded as absent “loss of consciousness”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Fainting](https://www.nhs.uk/symptoms/fainting/), page last reviewed 17 August 2026:
  - “See a GP if:”
  - “you have fainted”
  - “Call 999 if someone:”
  - “cannot be woken up within 1 minute”
  - “has not fully recovered or has difficulty with speech or movement”
  - “has chest pain or a pounding, fluttering or irregular heartbeat (heart palpitations)”
  - “is shaking or jerking (having a seizure or fit)”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-16"></a>
### Rule 16. Vomiting blood

| Level | Identifier | Checked in position |
|---|---|---:|
| **Urgent** | `urg.draft.vomiting_blood` | 16 of 20 |

**Fires when**

- any one of: “vomiting blood”; “hematemesis”; “Have you recently thrown up blood or something resembling coffee beans?”

**The person is shown**

> Vomiting blood needs to be assessed urgently, even if it has stopped. Please see a doctor today. Call 112 at once if you feel faint, dizzy, confused or generally unwell, or have black stools.

**Why this level.** The published advice when the vomiting has stopped and there are no other symptoms is an urgent appointment.

**Checked with two cases**

- Fires: recorded as present “vomiting blood”.
- Does not fire: recorded as present “headache”; recorded as absent “vomiting blood”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Vomiting blood](https://www.nhs.uk/symptoms/vomiting-blood/), page last reviewed 18 August 2025:
  - “Call 999 or go to A&E if:”
  - “You or your child are vomiting blood (or have vomited blood) and:”
  - “feel confused”
  - “feel faint or dizzy”
  - “have rapid or shallow breathing”
  - “have cold, clammy, pale skin”
  - “have black poo”
  - “If you have stopped vomiting blood and had no other symptoms, ask for an urgent GP appointment, call 111 or get help from 111 online.”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-17"></a>
### Rule 17. Coughing up blood

| Level | Identifier | Checked in position |
|---|---|---:|
| **Urgent** | `urg.draft.coughing_blood` | 17 of 20 |

**Fires when**

- any one of: “coughing blood”; “hemoptysis”; “blood in sputum”; “Have you been coughing up blood?”

**The person is shown**

> Coughing up blood, even a small amount, should be checked urgently. Please see a doctor today. Call 112 at once if it is more than a few spots or streaks, or if you also find it hard to breathe, have a very fast heartbeat or have chest pain.

**Why this level.** The published advice for a few spots or streaks of blood is an urgent appointment.

**Checked with two cases**

- Fires: recorded as present “coughing blood”.
- Does not fire: recorded as present “headache”; recorded as absent “coughing blood”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Coughing up blood (blood in phlegm)](https://www.nhs.uk/symptoms/coughing-up-blood/), page last reviewed 13 June 2024:
  - “Ask for an urgent GP appointment or get help from NHS 111 if:”
  - “you've coughed up a few small spots, flecks or streaks of blood, or noticed blood in your phlegm or handkerchief”
  - “you're coughing up more than just a few spots or streaks of blood”
  - “you're coughing up blood and finding it hard to breathe, have a very fast heartbeat or have pain in your chest or upper back”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-18"></a>
### Rule 18. Black stools, bloody diarrhoea or bleeding in the gut

| Level | Identifier | Checked in position |
|---|---|---:|
| **Urgent** | `urg.draft.black_or_bloody_stools` | 18 of 20 |

**Fires when**

- any one of: “melena”; “Have you recently had stools that were black (like coal)?”; “bloody diarrhea”; “gi bleeding”; “stomach bleeding”

**The person is shown**

> Black or dark red stools, or bloody diarrhoea, should be checked urgently. Please see a doctor today. Call 112 at once if you are bleeding non-stop or there is a lot of blood.

**Why this level.** The published advice for black or dark red stools and for bloody diarrhoea is an urgent appointment.

**Checked with two cases**

- Fires: recorded as present “melena”.
- Does not fire: recorded as present “headache”; recorded as absent “melena”; “bloody diarrhea”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Bleeding from the bottom (rectal bleeding)](https://www.nhs.uk/symptoms/bleeding-from-the-bottom-rectal-bleeding/), page last reviewed 12 April 2023:
  - “Ask for an urgent GP appointment or get help from NHS 111 if:”
  - “your poo is black or dark red”
  - “you have bloody diarrhoea”
  - “Go to A&E or call 999 if:”
  - “you're bleeding non-stop”
  - “there's a lot of blood – for example, the toilet water turns red or you see large blood clots”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-19"></a>
### Rule 19. Confusion

| Level | Identifier | Checked in position |
|---|---|---:|
| **Urgent** | `urg.draft.confusion` | 19 of 20 |

**Fires when**

- any one of: “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”

**The person is shown**

> New confusion should be checked by a doctor. Please see a doctor today. If the confusion came on suddenly, call 112 now or go to the nearest hospital emergency department.

**Why this level.** The published advice is an ambulance for sudden confusion and a doctor for gradual confusion. The vocabulary cannot say which it is, so the draft asks for the same day and names the sudden case.

**Checked with two cases**

- Fires: recorded as present “confusion symptom”.
- Does not fire: recorded as present “headache”; recorded as absent “confusion symptom”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Sudden confusion (delirium)](https://www.nhs.uk/symptoms/confusion/), page last reviewed 28 May 2024:
  - “Go to A&E or call 999 if:”
  - “someone suddenly becomes confused”
  - “Many causes of sudden confusion need to be assessed and treated as soon as possible. Sometimes it may be life threatening.”
  - “you're worried that you or a relative have gradually become more forgetful or confused”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

<a id="rule-20"></a>
### Rule 20. Bleeding or spotting in pregnancy

| Level | Identifier | Checked in position |
|---|---|---:|
| **Urgent** | `urg.draft.pregnancy_bleeding` | 20 of 20 |

**Fires when**

- “spotting or bleeding during pregnancy”

**The person is shown**

> Bleeding or spotting in pregnancy should be checked urgently. Please contact your doctor or maternity hospital today. Call 112 at once if the bleeding is heavy, or if you have severe tummy pain, shoulder pain, or feel faint or dizzy.

**Why this level.** The published advice for light bleeding in pregnancy is urgent help the same day.

**Checked with two cases**

- Fires: recorded as present “spotting or bleeding during pregnancy”.
- Does not fire: recorded as present “headache”; recorded as absent “spotting or bleeding during pregnancy”.

**Basis, quoted word for word**

- NHS (National Health Service, England), [Vaginal bleeding in pregnancy](https://www.nhs.uk/pregnancy/related-conditions/common-symptoms/vaginal-bleeding/), page last reviewed 17 February 2026:
  - “You're pregnant and have light bleeding or spotting with:”
  - “You're pregnant and bleeding and:”
  - “you feel sick, faint, dizzy or lose consciousness”
  - “the bleeding is heavy (soaking a period pad soon after putting it on)”
- Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
  - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”
  - “to establish a single emergency number "112" all over the country, integrating all existing emergency numbers”

## 9. Sources and licences

| Source | Used by rules | Licence and attribution |
|---|---|---|
| NHS (National Health Service, England): [Chest pain](https://www.nhs.uk/symptoms/chest-pain/) | 1, 13 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Heart attack: symptoms](https://www.nhs.uk/conditions/heart-attack/symptoms/) | 1 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Symptoms of a stroke](https://www.nhs.uk/conditions/stroke/symptoms/) | 3 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Shortness of breath](https://www.nhs.uk/symptoms/shortness-of-breath/) | 2, 14 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Fainting](https://www.nhs.uk/symptoms/fainting/) | 5, 15 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [What to do if someone has a seizure (fit)](https://www.nhs.uk/symptoms/what-to-do-if-someone-has-a-seizure-fit/) | 4 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Vomiting blood](https://www.nhs.uk/symptoms/vomiting-blood/) | 7, 16 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Coughing up blood (blood in phlegm)](https://www.nhs.uk/symptoms/coughing-up-blood/) | 8, 17 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Bleeding from the bottom (rectal bleeding)](https://www.nhs.uk/symptoms/bleeding-from-the-bottom-rectal-bleeding/) | 6, 18 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Anaphylaxis](https://www.nhs.uk/conditions/anaphylaxis/) | 9 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Help for suicidal thoughts](https://www.nhs.uk/mental-health/feelings-symptoms-behaviours/behaviours/help-for-suicidal-thoughts/) | 10 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Sudden confusion (delirium)](https://www.nhs.uk/symptoms/confusion/) | 19 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Meningitis: symptoms](https://www.nhs.uk/conditions/meningitis/symptoms/) | 11 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Headaches](https://www.nhs.uk/symptoms/headaches/) | 11 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Vaginal bleeding in pregnancy](https://www.nhs.uk/pregnancy/related-conditions/common-symptoms/vaginal-bleeding/) | 12, 20 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Cuts and grazes](https://www.nhs.uk/conditions/cuts-and-grazes/) | 6 | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| Kerala Police (Government of Kerala): [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10) | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20 | Government page; only the fact of the number is used. Read on 20 November 2026. |
| Dhubri Medical College & Hospital (Government of Assam): [TELE MANAS (Call 14416 | 24×7 Mental Health Helpline)](https://dhubri-mch.assam.gov.in/services/tele-manas-call-14416-24%C3%977-mental-health-helpline) | 10 | Government page; only the fact of the number is used. Read on 20 November 2026. |
| JIPMER (an institute of the Government of India): [Tele MANAS](https://jipmer.edu.in/Tele-MANAS) | 10 | Government institute page; only the fact of the number is used. Read on 20 November 2026. |

Information from the NHS website is licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). The rules and the texts shown are this project's own wording and are not NHS content.

## 10. Features the rules use

A feature is a symptom or an answer in the vocabulary. Where the feature is a question of a source, the question is shown. Features of different sources that mean the same thing are listed separately, because no synonym has been approved yet.

| Feature | Identifier | Used by rules |
|---|---|---|
| allergic reaction | `feat_f102837d3818427c` | 9 |
| altered sensorium | `feat_c025ada340213a6e` | 2, 7, 9, 11, 19 |
| Are you experiencing shortness of breath or difficulty breathing in a significant way? | `feat_6fd851f57d693514` | 1, 2, 5, 8, 9, 14 |
| Are you feeling nauseous or do you feel like vomiting? | `feat_db0323a965ed43f8` | 1 |
| arm pain | `feat_18bd94be679aa75f` | 1, 2 |
| arm weakness | `feat_bf1362ce30aced52` | 3, 5 |
| blood in sputum | `feat_c0764eaa0d4d4359` | 8, 17 |
| bloody diarrhea | `feat_87d932aa318aca3f` | 18 |
| breathing fast | `feat_b105a962ed12e68a` | 7 |
| breathlessness | `feat_8aa757ecf0b9f5a1` | 1, 2, 5, 8, 9, 14 |
| burning chest pain | `feat_b8da6b9cc18eda60` | 1, 5, 8, 13 |
| chest pain | `feat_1bce3b700f26488e` | 1, 5, 8, 13 |
| chest pain with pressure | `feat_78ccf4d93a6afbd2` | 1, 2, 5, 8, 13 |
| chest tightness | `feat_ebf04f43774b7e3c` | 1, 2, 13 |
| clammy skin | `feat_3f2ba6c5e7f25f8f` | 7 |
| coma | `feat_b477cc5dc15d0c0f` | 5 |
| confusion symptom | `feat_feba6db2bf4f3885` | 2, 7, 9, 11, 19 |
| coughing blood | `feat_bfdb9e0934144f9a` | 8, 17 |
| cyanosis | `feat_9ec57aff72e3d05a` | 2, 9 |
| Did you lose consciousness? | `feat_fc1576878fb13487` | 5, 7, 9, 12, 15 |
| Did you previously, or do you currently, have any weakness/paralysis in one or more of your limbs or in your face? | `feat_0a46fc9ac61c1f88` | 3, 5 |
| difficulty breathing | `feat_0e83bbeb2c44d545` | 1, 2, 5, 8, 9, 14 |
| difficulty in swallowing | `feat_08776c52f04facce` | 9 |
| difficulty swallowing | `feat_56690981e533f44b` | 9 |
| Do you feel lightheaded and dizzy or do you feel like you are about to faint? | `feat_6f29a2ae0f3f0bec` | 1, 7, 9, 12 |
| Do you feel like you are (or were) choking or suffocating? | `feat_cffc65f56f48fd1d` | 2, 8, 9 |
| Do you feel slightly dizzy or lightheaded? | `feat_1c96062288fbc89c` | 1, 7, 9, 12 |
| Do you feel your heart is beating fast (racing), irregularly (missing a beat) or do you feel palpitations? | `feat_4454e9a3f95b108b` | 5, 8 |
| Do you have chest pain even at rest? | `feat_8e05c05545bb2540` | 1, 5, 8, 13 |
| Do you have difficulty articulating words/speaking? | `feat_1233a39e6499bb50` | 3, 5 |
| Do you have difficulty swallowing, or have a feeling of discomfort/blockage when swallowing? | `feat_662698008d49940d` | 9 |
| excessive bleeding | `feat_2ab8c0a709b94cbf` | 6 |
| exertional chest pain | `feat_395e34c1ec226830` | 1, 5, 8, 13 |
| facial droop | `feat_b959ff4df97acbe6` | 3, 5 |
| fainting | `feat_f99bdee4af7edc21` | 5, 7, 9, 12, 15 |
| fast heart rate | `feat_3a659497500a481d` | 5, 8 |
| focal weakness | `feat_d9f09a91be3e4be8` | 3, 5 |
| frontal headache | `feat_287cfd2e943eed33` | 11 |
| gi bleeding | `feat_948b23ec9fe9d8b7` | 18 |
| Have you been coughing up blood? | `feat_67d232146bf4b879` | 8, 17 |
| Have you been in contact with or ate something that you have an allergy to? | `feat_9d633014cd900a18` | 9 |
| Have you felt confused or disorientated lately? | `feat_6be86b723c44550a` | 2, 7, 9, 11, 19 |
| Have you had significantly increased sweating? | `feat_bdf5241bd01f14de` | 1 |
| Have you had weakness or paralysis on one side of the face, which may still be present or completely resolved? | `feat_82c5355f67db7093` | 3, 5 |
| Have you lost consciousness associated with violent and sustained muscle contractions or had an absence episode? | `feat_6b4502089a785b3a` | 4, 5 |
| Have you recently had stools that were black (like coal)? | `feat_4134661fdbaad8af` | 7, 18 |
| Have you recently thrown up blood or something resembling coffee beans? | `feat_6c69c76f2054996e` | 7, 16 |
| headache | `feat_cfa9ac1e084975b5` | 11 |
| hematemesis | `feat_8d48d8d10c60df07` | 7, 16 |
| hemoptysis | `feat_3c93e1dee24f988d` | 8, 17 |
| high fever | `feat_7f148d05bbfe51b6` | 11 |
| irregular heartbeat | `feat_c9a1db87eb937e51` | 5, 8 |
| Is your skin much paler than usual? | `feat_bb56f4da7abf1bf1` | 2 |
| jaw pain | `feat_c8d19d17af22d111` | 1, 2 |
| lip swelling | `feat_bc3bdde05d094430` | 9 |
| loss of consciousness | `feat_e61a05ca1b6576be` | 5, 7, 9, 12, 15 |
| melena | `feat_238e886048083080` | 7, 18 |
| nausea | `feat_e31040de4051bb5c` | 1 |
| neck pain | `feat_9e3b5c92b94f2970` | 1, 2 |
| neck stiffness or tightness | `feat_8308d54d3de1ef3b` | 11 |
| palpitations | `feat_de9e44d049057cdb` | 5, 8 |
| paralysed body | `feat_17b101e41b98b0a9` | 3, 5 |
| paralysis | `feat_638a53a83c43d5c3` | 3, 5 |
| photophobia | `feat_312b0e05eaae3112` | 11 |
| pleuritic chest pain | `feat_01cb6f6ed4073705` | 1, 5, 8, 13 |
| prolonged bleeding | `feat_c2ebae0b48d3986a` | 6 |
| rapid breathing | `feat_3db1fa92a3cbe852` | 7 |
| seizures | `feat_14a329d678cf228a` | 4, 5 |
| seizures symptom | `feat_0d661e4d15abd702` | 4, 5 |
| sensitivity to light | `feat_ee38b36fc7b92ee3` | 11 |
| sharp chest pain | `feat_4deb5e4901555ec2` | 1, 5, 8, 13 |
| shortness of breath | `feat_8e11ac43dbca88a2` | 1, 2, 5, 8, 9, 14 |
| slurred speech | `feat_1c9594a508588fcd` | 3, 5 |
| slurring words | `feat_d8c8d400493d26cd` | 3, 5 |
| speech difficulty | `feat_b5926ba67bca6d17` | 3, 5 |
| spotting or bleeding during pregnancy | `feat_72389d820e0e6a53` | 12, 20 |
| stiff neck | `feat_90878ed71c7cfa3e` | 11 |
| stomach bleeding | `feat_7ae86609f09a5426` | 18 |
| sudden uncontrolled electrical disturbances in the brain | `feat_a2e8fb96182df1ff` | 4, 5 |
| suicidal ideation | `feat_f87ea35d110410ca` | 10 |
| sweating | `feat_082c8ca10d0dcda4` | 1 |
| syncope | `feat_b3805932f54c0119` | 5, 7, 9, 12, 15 |
| throat swelling | `feat_776ca07cbcfabc51` | 9 |
| vomiting | `feat_c629da3c8da3dc80` | 1 |
| vomiting blood | `feat_e95a6589eafaf491` | 7, 16 |

## 11. History

| Date | Change |
|---|---|
| 2026-11-20 | First draft: 20 rules (12 emergency, 8 urgent), stored pending. |
| 2026-11-23 | Review document enlarged and the final text for approval prepared. No rule, level or text shown was changed. Added: the list of telephone numbers with their confirmation status, the known weaknesses, and a second quoted sentence for 112. |
| 2026-11-23 | The owner approved all 20 rules and confirmed the two telephone numbers. The owner's words, in reply to the note that no rule was decided and both numbers were unconfirmed: "This is decided by me and approved. 20 rules are approved." No rule, level or text shown was changed. |
