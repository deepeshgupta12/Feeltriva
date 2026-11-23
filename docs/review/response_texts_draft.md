# Response texts: draft for the owner's approval

> **Not approved. Not shown to anyone.**
> Draft written by the engineering assistant on the owner's instruction (decision E81), not by a clinician. Not approved. These texts are shown to nobody until the owner approves them and a release is served.

Draft `response-texts-draft-1` for India, written 2026-11-23. This document is generated from `packages/clinical/feeltriva_clinical/drafts/response_texts_draft.json`: change the file, not this text.

## What these texts are

Every release carries four texts that a person is shown outside the urgency rules. The service never writes such a text itself: it shows exactly these words. None of them names an illness, a medicine or a percentage. The only telephone number they name is one the owner has confirmed.

| No. | Text | Shown when |
|---:|---|---|
| 1 | `confirm_details` | The service has understood something from the person's own words and it has not yet been confirmed. The assessment goes no further until the person has checked it. |
| 2 | `provisional_next_step` | The assessment has found one or more possible explanations and shows them. This text stands above them as the next step. |
| 3 | `insufficient_information` | The assessment has finished and no possible explanation can be given from reviewed information. |
| 4 | `system_unavailable` | A technical problem keeps the assessment from being completed. The person sees this instead of a result. |

## The texts

### 1. `confirm_details`

**Shown when.** The service has understood something from the person's own words and it has not yet been confirmed. The assessment goes no further until the person has checked it.

**The person is shown**

> Before we continue, please check what we understood from your description. Confirm each detail that is right and correct anything that is wrong.

**Why it is worded so.** The handoff requires that what is understood from free text is confirmed by the person before it is used. The text asks for exactly that and says nothing about health.

**Owner's decision:** approve / change / reject. Note:

### 2. `provisional_next_step`

**Shown when.** The assessment has found one or more possible explanations and shows them. This text stands above them as the next step.

**The person is shown**

> These are possible explanations for what you described. They are not a diagnosis. Please show this summary to a doctor, who can examine you and decide what it is. If your symptoms get worse or new symptoms appear, do not wait to see a doctor. In an emergency call 112 or go to the nearest hospital emergency department.

**Why it is worded so.** The handoff allows provisional possible explanations only, never a diagnosis, and wants the next step shown first. The text names no illness, medicine or number, sends the person to a doctor, and says what to do if things get worse.

**Owner's decision:** approve / change / reject. Note:

### 3. `insufficient_information`

**Shown when.** The assessment has finished and no possible explanation can be given from reviewed information.

**The person is shown**

> We do not have enough reviewed information to suggest a possible explanation for what you described. This does not mean that nothing is wrong. If you are worried, or your symptoms continue or get worse, please see a doctor. In an emergency call 112 or go to the nearest hospital emergency department. You can also add more details and try again.

**Why it is worded so.** Finding nothing must not read as reassurance: the text says so in its second sentence. It gives a way forward (a doctor, or more details) and the emergency route.

**Owner's decision:** approve / change / reject. Note:

### 4. `system_unavailable`

**Shown when.** A technical problem keeps the assessment from being completed. The person sees this instead of a result.

**The person is shown**

> We could not complete this assessment because of a technical problem. Nothing has been concluded about your symptoms. Please try again in a little while. If you need help now, please see a doctor. In an emergency call 112 or go to the nearest hospital emergency department.

**Why it is worded so.** A failure must not look like a result. The text says that nothing was concluded, and does not leave a person who needs help with only an error.

**Owner's decision:** approve / change / reject. Note:

## Still open

- The owner's approval of each text. Nothing here is used before it.
- No doctor has read the texts. They give no medical advice beyond seeing a doctor and the emergency number, but a review is still advised with the rules.
- The texts are in English only, as the product's first scope is.
- Where the approved texts are stored and how the approval is recorded is built with the serving bundle (M2.5f).
