# Urgency rules: draft for the owner's review

**Unreviewed draft. Written by the engineering assistant on the owner's instruction (decision E39), not by a clinician. It is not a validated triage protocol and is not served to anyone until the owner approves it.**

Version `urgency-draft-1`, written 2026-11-20, for India. Status: `pending`. This document is generated from `packages/clinical/feeltriva_clinical/drafts/urgency_draft.json`; change the file, not this text.

## How to read it

- A rule fires only when the answers given so far make its condition true. A symptom nobody has asked about counts as unknown, never as absent.
- **Emergency** rules are checked before **urgent** ones, and the first rule that fires decides the text shown.
- The words in quotation marks are features of the vocabulary; a question is shown where the feature is one.
- Each basis is quoted word for word from the page named, with the date the page says it was last reviewed.

## Open points for the owner

1. The warning signs are taken from the NHS website (England). No Indian clinical source was used. A doctor practising in India should review the rules before they are approved.
2. The numbers 112 and 14416 could not be read on the central government's own pages (112.gov.in, mha.gov.in, telemanas.mohfw.gov.in, pib.gov.in refused automated reading). They are taken from a Kerala Police page, a Government of Assam hospital page and a JIPMER page. The owner should open the official pages and confirm both numbers before approval.
3. The ambulance number 108 is not used: no official page stating it could be read, and it differs between states.
4. Each urgency level is the assistant's choice within the published advice. Where the vocabulary cannot tell a severe or sudden case from a mild one, the draft escalates.
5. The rules have not been tried on real cases. No urgency labels exist to measure how often they would fire wrongly or miss.

## Warning signs the draft does not cover

| Published warning sign | Why there is no rule |
|---|---|
| How severe or how sudden a symptom is (severe pain, sudden headache, sudden swelling) | the feature vocabulary records that a symptom is present, not its severity or onset |
| Choking on food or an object, serious injury, burns, poisoning or overdose | no feature in the vocabulary |
| A rash that does not fade when pressed; the other signs of sepsis | no feature in the vocabulary |
| Weakness or numbness down one side of the body; sudden loss of vision | the vocabulary has only general weakness, numbness and vision features, which are common without a stroke |
| Labour and childbirth; warning signs in babies and children | outside what the product assesses (adults; no pregnancy flows) |
| Blood in the stool that is not black, dark red or with diarrhoea | the published advice is a routine appointment, not an urgent one |

## The rules

### 1. Chest pain with signs of a heart attack

- **Rule:** `urg.draft.chest_pain_emergency`, level **emergency**, priority 10, status `pending`
- **Fires when:** (“chest pain with pressure”) OR ((any of: “chest pain”; “Do you have chest pain even at rest?”; “sharp chest pain”; “burning chest pain”; “exertional chest pain”; “pleuritic chest pain”; “chest pain with pressure”) AND (any of: “chest tightness”; “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”; “sweating”; “Have you had significantly increased sweating?”; “nausea”; “vomiting”; “Are you feeling nauseous or do you feel like vomiting?”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “Do you feel slightly dizzy or lightheaded?”; “arm pain”; “jaw pain”; “neck pain”))
- **Text shown:** Chest pain that feels like pressure or tightness, or chest pain together with breathlessness, sweating, feeling sick or light-headed, or pain in an arm, the neck or the jaw, can be a sign of a heart attack. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** The published advice is to call an ambulance straight away for exactly these combinations.
- **Basis:**
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

### 2. Severe breathing difficulty

- **Rule:** `urg.draft.breathing_emergency`, level **emergency**, priority 11, status `pending`
- **Fires when:** (any of: “Do you feel like you are (or were) choking or suffocating?”; “cyanosis”) OR ((any of: “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”) AND (any of: “chest tightness”; “chest pain with pressure”; “Is your skin much paler than usual?”; “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”; “arm pain”; “jaw pain”; “neck pain”))
- **Text shown:** A feeling of choking or suffocating, blue lips or skin, or breathing difficulty together with a tight or heavy chest, very pale skin, sudden confusion or pain in an arm, the neck or the jaw, needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** Published as reasons to call an ambulance. The vocabulary has no feature for how severe the breathlessness is, so breathlessness alone is placed one level lower (see the rule on breathing difficulty).
- **Basis:**
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

### 3. Signs of a stroke

- **Rule:** `urg.draft.stroke_signs`, level **emergency**, priority 12, status `pending`
- **Fires when:** any of: “facial droop”; “Have you had weakness or paralysis on one side of the face, which may still be present or completely resolved?”; “arm weakness”; “slurred speech”; “slurring words”; “speech difficulty”; “Do you have difficulty articulating words/speaking?”; “focal weakness”; “paralysis”; “paralysed body”; “Did you previously, or do you currently, have any weakness/paralysis in one or more of your limbs or in your face?”
- **Text shown:** Weakness or drooping on one side of the face, weakness in an arm or a leg, or slurred or difficult speech can be signs of a stroke, even if they have now stopped. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** The published advice is to call an ambulance for any of these signs, also when they have stopped. The vocabulary cannot say whether a weakness is new, so any report of one of these signs escalates.
- **Basis:**
  - NHS (National Health Service, England), [Symptoms of a stroke](https://www.nhs.uk/conditions/stroke/symptoms/), page last reviewed 12 September 2024:
    - “face weakness – one side of your face may droop (fall) and it might be hard to smile”
    - “arm weakness – you may not be able to fully lift both arms and keep them there because of weakness or numbness in 1 arm”
    - “speech problems – you may slur your words or sound confused”
    - “weakness or numbness down 1 side of your body”
    - “you've had signs of a stroke within the last 24 hours even if they've now stopped”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

### 4. Seizure (fit)

- **Rule:** `urg.draft.seizure`, level **emergency**, priority 13, status `pending`
- **Fires when:** any of: “seizures”; “seizures symptom”; “Have you lost consciousness associated with violent and sustained muscle contractions or had an absence episode?”; “sudden uncontrolled electrical disturbances in the brain”
- **Text shown:** A seizure (fit) needs emergency help when it is a first seizure, lasts more than 5 minutes, repeats, or the person does not fully recover. If you are not sure, treat it as an emergency. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** The published advice is an ambulance for a first seizure. The vocabulary cannot say whether a seizure is the first one, so every reported seizure escalates. People with known epilepsy do not always need an ambulance.
- **Basis:**
  - NHS (National Health Service, England), [What to do if someone has a seizure (fit)](https://www.nhs.uk/symptoms/what-to-do-if-someone-has-a-seizure-fit/), page last reviewed 19 December 2023:
    - “Call 999 and ask for an ambulance if:”
    - “it's the first time someone has had a seizure”
    - “the seizure lasts more than 5 minutes, if you do not know how long their seizures usually last”
    - “the person does not regain full consciousness, or has several seizures without regaining consciousness”
    - “People with epilepsy do not always need an ambulance or to go to hospital every time they have a seizure.”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

### 5. Loss of consciousness with other warning signs

- **Rule:** `urg.draft.loss_of_consciousness_emergency`, level **emergency**, priority 14, status `pending`
- **Fires when:** (“coma”) OR ((any of: “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”) AND (any of: “chest pain”; “Do you have chest pain even at rest?”; “sharp chest pain”; “burning chest pain”; “exertional chest pain”; “pleuritic chest pain”; “chest pain with pressure”; “palpitations”; “Do you feel your heart is beating fast (racing), irregularly (missing a beat) or do you feel palpitations?”; “irregular heartbeat”; “fast heart rate”; “seizures”; “seizures symptom”; “Have you lost consciousness associated with violent and sustained muscle contractions or had an absence episode?”; “sudden uncontrolled electrical disturbances in the brain”; “facial droop”; “Have you had weakness or paralysis on one side of the face, which may still be present or completely resolved?”; “arm weakness”; “slurred speech”; “slurring words”; “speech difficulty”; “Do you have difficulty articulating words/speaking?”; “focal weakness”; “paralysis”; “paralysed body”; “Did you previously, or do you currently, have any weakness/paralysis in one or more of your limbs or in your face?”; “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”))
- **Text shown:** Losing consciousness together with chest pain, a racing or irregular heartbeat, a seizure, difficulty with speech or movement, or breathing difficulty needs immediate help. So does anyone who cannot be woken. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** Published as reasons to call an ambulance after a faint.
- **Basis:**
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

### 6. Bleeding that is heavy or will not stop

- **Rule:** `urg.draft.heavy_bleeding`, level **emergency**, priority 15, status `pending`
- **Fires when:** any of: “excessive bleeding”; “prolonged bleeding”
- **Text shown:** Bleeding that is heavy or that you cannot stop needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** Published as a reason to call an ambulance or go to an emergency department.
- **Basis:**
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

### 7. Vomiting blood with other warning signs

- **Rule:** `urg.draft.vomiting_blood_emergency`, level **emergency**, priority 16, status `pending`
- **Fires when:** (any of: “vomiting blood”; “hematemesis”; “Have you recently thrown up blood or something resembling coffee beans?”) AND (any of: “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “Do you feel slightly dizzy or lightheaded?”; “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”; “clammy skin”; “rapid breathing”; “breathing fast”; “melena”; “Have you recently had stools that were black (like coal)?”)
- **Text shown:** Vomiting blood together with feeling faint, dizzy or confused, fast breathing, cold clammy skin or black stools needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** Published as reasons to call an ambulance when someone is vomiting blood.
- **Basis:**
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

### 8. Coughing up blood with other warning signs

- **Rule:** `urg.draft.coughing_blood_emergency`, level **emergency**, priority 17, status `pending`
- **Fires when:** (any of: “coughing blood”; “hemoptysis”; “blood in sputum”; “Have you been coughing up blood?”) AND (any of: “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”; “Do you feel like you are (or were) choking or suffocating?”; “chest pain”; “Do you have chest pain even at rest?”; “sharp chest pain”; “burning chest pain”; “exertional chest pain”; “pleuritic chest pain”; “chest pain with pressure”; “palpitations”; “Do you feel your heart is beating fast (racing), irregularly (missing a beat) or do you feel palpitations?”; “irregular heartbeat”; “fast heart rate”)
- **Text shown:** Coughing up blood together with difficulty breathing, a very fast heartbeat or chest pain needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** Published as reasons to call an ambulance when someone is coughing up blood.
- **Basis:**
  - NHS (National Health Service, England), [Coughing up blood (blood in phlegm)](https://www.nhs.uk/symptoms/coughing-up-blood/), page last reviewed 13 June 2024:
    - “Ask for an urgent GP appointment or get help from NHS 111 if:”
    - “you've coughed up a few small spots, flecks or streaks of blood, or noticed blood in your phlegm or handkerchief”
    - “you're coughing up more than just a few spots or streaks of blood”
    - “you're coughing up blood and finding it hard to breathe, have a very fast heartbeat or have pain in your chest or upper back”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

### 9. Signs of a severe allergic reaction

- **Rule:** `urg.draft.severe_allergic_reaction`, level **emergency**, priority 18, status `pending`
- **Fires when:** (any of: “lip swelling”; “throat swelling”) OR ((any of: “allergic reaction”; “Have you been in contact with or ate something that you have an allergy to?”) AND (any of: “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”; “Do you feel like you are (or were) choking or suffocating?”; “difficulty in swallowing”; “difficulty swallowing”; “Do you have difficulty swallowing, or have a feeling of discomfort/blockage when swallowing?”; “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “Do you feel slightly dizzy or lightheaded?”; “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”; “cyanosis”))
- **Text shown:** Swelling of the lips or throat, or an allergic reaction together with difficulty breathing or swallowing, confusion, dizziness or fainting, can be a severe allergic reaction. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** Published as reasons to call an ambulance. The vocabulary cannot say whether a swelling is sudden, so any reported swelling of the lips or throat escalates.
- **Basis:**
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

### 10. Thoughts of suicide or self-harm

- **Rule:** `urg.draft.thoughts_of_self_harm`, level **emergency**, priority 19, status `pending`
- **Fires when:** “suicidal ideation”
- **Text shown:** You do not have to face this alone, and help is available right now. If you have harmed yourself or feel you may be about to, call 112 now or go to the nearest hospital emergency department, or ask someone to take you. You can also speak to a trained counsellor free of charge at any time on Tele MANAS: call 14416.
- **Why this level:** The published advice is to tell someone and, where there is harm or a risk of it, to call an ambulance. The highest level is used so that this text is shown before anything else.
- **Basis:**
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

### 11. Stiff neck or headache with signs of a serious infection

- **Rule:** `urg.draft.meningitis_signs`, level **emergency**, priority 20, status `pending`
- **Fires when:** ((any of: “stiff neck”; “neck stiffness or tightness”) AND (any of: “photophobia”; “sensitivity to light”)) OR ((any of: “headache”; “frontal headache”) AND (any of: “stiff neck”; “neck stiffness or tightness”; “photophobia”; “sensitivity to light”; “high fever”; “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”))
- **Text shown:** A stiff neck with a dislike of bright lights, or a headache together with a stiff neck, a dislike of bright lights, a very high temperature or confusion, can be signs of a serious infection. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** Published as reasons to call an ambulance or go to an emergency department.
- **Basis:**
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

### 12. Bleeding in pregnancy with fainting or dizziness

- **Rule:** `urg.draft.pregnancy_bleeding_emergency`, level **emergency**, priority 21, status `pending`
- **Fires when:** (“spotting or bleeding during pregnancy”) AND (any of: “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”; “Do you feel lightheaded and dizzy or do you feel like you are about to faint?”; “Do you feel slightly dizzy or lightheaded?”)
- **Text shown:** Bleeding in pregnancy together with feeling faint or dizzy, or losing consciousness, needs immediate treatment. Call 112 now or go to the nearest hospital emergency department. Do not drive yourself: ask someone to take you or ask for an ambulance. This is not a diagnosis.
- **Why this level:** Published as a reason to call an ambulance. Pregnancy is outside what the product assesses, but an escalation is still shown.
- **Basis:**
  - NHS (National Health Service, England), [Vaginal bleeding in pregnancy](https://www.nhs.uk/pregnancy/related-conditions/common-symptoms/vaginal-bleeding/), page last reviewed 17 February 2026:
    - “You're pregnant and have light bleeding or spotting with:”
    - “You're pregnant and bleeding and:”
    - “you feel sick, faint, dizzy or lose consciousness”
    - “the bleeding is heavy (soaking a period pad soon after putting it on)”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

### 13. Chest pain or chest tightness

- **Rule:** `urg.draft.chest_pain`, level **urgent**, priority 100, status `pending`
- **Fires when:** any of: “chest pain”; “Do you have chest pain even at rest?”; “sharp chest pain”; “burning chest pain”; “exertional chest pain”; “pleuritic chest pain”; “chest pain with pressure”; “chest tightness”
- **Text shown:** Chest pain should be checked by a doctor even when it is probably nothing serious. Please see a doctor today. Call 112 at once if the pain does not go away, feels like pressure or tightness, spreads to an arm, the neck or the jaw, or comes with breathlessness, sweating or feeling sick.
- **Why this level:** The published advice for chest pain without the heart-attack signs is to see a doctor, not an ambulance. The draft asks for the same day and names the signs that need 112.
- **Basis:**
  - NHS (National Health Service, England), [Chest pain](https://www.nhs.uk/symptoms/chest-pain/), page last reviewed 08 August 2023:
    - “Call 999 if:”
    - “you get sudden pain or discomfort in your chest that does not go away – the pain can feel like squeezing or pressure inside your chest, burning or indigestion”
    - “you get pain that spreads to your left or right arm, or your neck, jaw, stomach or back”
    - “you have chest pain and you feel sweaty, sick, light headed or short of breath”
    - “You could be having a heart attack. Call 999 straight away as you need immediate treatment in hospital.”
    - “Most chest pain is not a sign of anything serious but get medical advice just in case.”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

### 14. Breathing difficulty

- **Rule:** `urg.draft.breathing_difficulty`, level **urgent**, priority 101, status `pending`
- **Fires when:** any of: “shortness of breath”; “breathlessness”; “difficulty breathing”; “Are you experiencing shortness of breath or difficulty breathing in a significant way?”
- **Text shown:** Difficulty breathing, or being more short of breath than usual, should be checked today. Please see a doctor today. Call 112 at once if you are gasping, cannot get words out, your chest feels tight or heavy, your lips or skin turn blue or very pale, or you feel suddenly confused.
- **Why this level:** The published advice for breathing difficulty without the severe signs is urgent advice the same day.
- **Basis:**
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

### 15. Fainting or loss of consciousness

- **Rule:** `urg.draft.fainting`, level **urgent**, priority 102, status `pending`
- **Fires when:** any of: “loss of consciousness”; “Did you lose consciousness?”; “fainting”; “syncope”
- **Text shown:** Fainting or losing consciousness should be checked by a doctor to find out what caused it. Please see a doctor today. Call 112 at once if it comes with chest pain, a racing or irregular heartbeat, a seizure, or difficulty with speech or movement, or if you have not fully recovered.
- **Why this level:** The published advice after a simple faint is to see a doctor. The draft asks for the same day.
- **Basis:**
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

### 16. Vomiting blood

- **Rule:** `urg.draft.vomiting_blood`, level **urgent**, priority 103, status `pending`
- **Fires when:** any of: “vomiting blood”; “hematemesis”; “Have you recently thrown up blood or something resembling coffee beans?”
- **Text shown:** Vomiting blood needs to be assessed urgently, even if it has stopped. Please see a doctor today. Call 112 at once if you feel faint, dizzy, confused or generally unwell, or have black stools.
- **Why this level:** The published advice when the vomiting has stopped and there are no other symptoms is an urgent appointment.
- **Basis:**
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

### 17. Coughing up blood

- **Rule:** `urg.draft.coughing_blood`, level **urgent**, priority 104, status `pending`
- **Fires when:** any of: “coughing blood”; “hemoptysis”; “blood in sputum”; “Have you been coughing up blood?”
- **Text shown:** Coughing up blood, even a small amount, should be checked urgently. Please see a doctor today. Call 112 at once if it is more than a few spots or streaks, or if you also find it hard to breathe, have a very fast heartbeat or have chest pain.
- **Why this level:** The published advice for a few spots or streaks of blood is an urgent appointment.
- **Basis:**
  - NHS (National Health Service, England), [Coughing up blood (blood in phlegm)](https://www.nhs.uk/symptoms/coughing-up-blood/), page last reviewed 13 June 2024:
    - “Ask for an urgent GP appointment or get help from NHS 111 if:”
    - “you've coughed up a few small spots, flecks or streaks of blood, or noticed blood in your phlegm or handkerchief”
    - “you're coughing up more than just a few spots or streaks of blood”
    - “you're coughing up blood and finding it hard to breathe, have a very fast heartbeat or have pain in your chest or upper back”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

### 18. Black stools, bloody diarrhoea or bleeding in the gut

- **Rule:** `urg.draft.black_or_bloody_stools`, level **urgent**, priority 105, status `pending`
- **Fires when:** any of: “melena”; “Have you recently had stools that were black (like coal)?”; “bloody diarrhea”; “gi bleeding”; “stomach bleeding”
- **Text shown:** Black or dark red stools, or bloody diarrhoea, should be checked urgently. Please see a doctor today. Call 112 at once if you are bleeding non-stop or there is a lot of blood.
- **Why this level:** The published advice for black or dark red stools and for bloody diarrhoea is an urgent appointment.
- **Basis:**
  - NHS (National Health Service, England), [Bleeding from the bottom (rectal bleeding)](https://www.nhs.uk/symptoms/bleeding-from-the-bottom-rectal-bleeding/), page last reviewed 12 April 2023:
    - “Ask for an urgent GP appointment or get help from NHS 111 if:”
    - “your poo is black or dark red”
    - “you have bloody diarrhoea”
    - “Go to A&E or call 999 if:”
    - “you're bleeding non-stop”
    - “there's a lot of blood – for example, the toilet water turns red or you see large blood clots”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

### 19. Confusion

- **Rule:** `urg.draft.confusion`, level **urgent**, priority 106, status `pending`
- **Fires when:** any of: “confusion symptom”; “Have you felt confused or disorientated lately?”; “altered sensorium”
- **Text shown:** New confusion should be checked by a doctor. Please see a doctor today. If the confusion came on suddenly, call 112 now or go to the nearest hospital emergency department.
- **Why this level:** The published advice is an ambulance for sudden confusion and a doctor for gradual confusion. The vocabulary cannot say which it is, so the draft asks for the same day and names the sudden case.
- **Basis:**
  - NHS (National Health Service, England), [Sudden confusion (delirium)](https://www.nhs.uk/symptoms/confusion/), page last reviewed 28 May 2024:
    - “Go to A&E or call 999 if:”
    - “someone suddenly becomes confused”
    - “Many causes of sudden confusion need to be assessed and treated as soon as possible. Sometimes it may be life threatening.”
    - “you're worried that you or a relative have gradually become more forgetful or confused”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

### 20. Bleeding or spotting in pregnancy

- **Rule:** `urg.draft.pregnancy_bleeding`, level **urgent**, priority 107, status `pending`
- **Fires when:** “spotting or bleeding during pregnancy”
- **Text shown:** Bleeding or spotting in pregnancy should be checked urgently. Please contact your doctor or maternity hospital today. Call 112 at once if the bleeding is heavy, or if you have severe tummy pain, shoulder pain, or feel faint or dizzy.
- **Why this level:** The published advice for light bleeding in pregnancy is urgent help the same day.
- **Basis:**
  - NHS (National Health Service, England), [Vaginal bleeding in pregnancy](https://www.nhs.uk/pregnancy/related-conditions/common-symptoms/vaginal-bleeding/), page last reviewed 17 February 2026:
    - “You're pregnant and have light bleeding or spotting with:”
    - “You're pregnant and bleeding and:”
    - “you feel sick, faint, dizzy or lose consciousness”
    - “the bleeding is heavy (soaking a period pad soon after putting it on)”
  - Kerala Police (Government of Kerala), [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10):
    - “ERSS is an emergency response system wherein the citizen can seek support from police in cases of emergency. All they need is to call 112.”

## Sources and licences

| Source | Licence and attribution |
|---|---|
| NHS (National Health Service, England): [Chest pain](https://www.nhs.uk/symptoms/chest-pain/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Heart attack: symptoms](https://www.nhs.uk/conditions/heart-attack/symptoms/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Symptoms of a stroke](https://www.nhs.uk/conditions/stroke/symptoms/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Shortness of breath](https://www.nhs.uk/symptoms/shortness-of-breath/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Fainting](https://www.nhs.uk/symptoms/fainting/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [What to do if someone has a seizure (fit)](https://www.nhs.uk/symptoms/what-to-do-if-someone-has-a-seizure-fit/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Vomiting blood](https://www.nhs.uk/symptoms/vomiting-blood/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Coughing up blood (blood in phlegm)](https://www.nhs.uk/symptoms/coughing-up-blood/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Bleeding from the bottom (rectal bleeding)](https://www.nhs.uk/symptoms/bleeding-from-the-bottom-rectal-bleeding/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Anaphylaxis](https://www.nhs.uk/conditions/anaphylaxis/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Help for suicidal thoughts](https://www.nhs.uk/mental-health/feelings-symptoms-behaviours/behaviours/help-for-suicidal-thoughts/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Sudden confusion (delirium)](https://www.nhs.uk/symptoms/confusion/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Meningitis: symptoms](https://www.nhs.uk/conditions/meningitis/symptoms/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Headaches](https://www.nhs.uk/symptoms/headaches/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Vaginal bleeding in pregnancy](https://www.nhs.uk/pregnancy/related-conditions/common-symptoms/vaginal-bleeding/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| NHS (National Health Service, England): [Cuts and grazes](https://www.nhs.uk/conditions/cuts-and-grazes/) | Open Government Licence v3.0. Information from the NHS website, as at 20 November 2026. |
| Kerala Police (Government of Kerala): [Emergency Response Support System (ERSS)](https://keralapolice.gov.in/home/page/award/10) | Government page; only the fact of the number is used. Read on 20 November 2026. |
| Dhubri Medical College & Hospital (Government of Assam): [TELE MANAS (Call 14416 | 24×7 Mental Health Helpline)](https://dhubri-mch.assam.gov.in/services/tele-manas-call-14416-24%C3%977-mental-health-helpline) | Government page; only the fact of the number is used. Read on 20 November 2026. |
| JIPMER (an institute of the Government of India): [Tele MANAS](https://jipmer.edu.in/Tele-MANAS) | Government institute page; only the fact of the number is used. Read on 20 November 2026. |

Information from the NHS website is licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). The rules and the texts shown are this project's own wording and are not NHS content.
