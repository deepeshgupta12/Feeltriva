/**
 * Plain words for the review workspace (M2.4d). The stored data holds short system codes; a
 * reviewer who is not a programmer or a clinician reads these words in their place. A code this
 * list does not know is shown as it is, with spaces for underscores, so nothing is hidden.
 */
const spaced = (code: string): string => code.replace(/_/g, ' ');

const lookup =
  (words: Record<string, string>) =>
  (code: string): string =>
    words[code] ?? spaced(code);

/** How a match to a reference list was found. */
export const howMatched = lookup({
  exact_label: 'The entry’s own name is exactly our name',
  exact_title: 'The entry’s title is exactly our name',
  exact_synonym: 'One of the entry’s other names is exactly our name',
  exact_titleofotherentity: 'Our name is exactly the name of the group this entry belongs to',
  exact_name: 'The entry’s full name is exactly our name',
  short_name_in_question: 'The entry’s short name appears in our question',
  mondo_equivalent: 'The MONDO list says this code stands for the same condition',
  source_provided: 'The data source itself gave this code',
  reviewer_confirmed: 'A reviewer confirmed it from a suggested match',
});

/** How a name from a data file was put into a group. */
export const howGrouped = lookup({
  lexical_casefold_whitespace: 'Same spelling, ignoring capital letters and extra spaces',
});

/** What a 0 in a column of a data file means. */
export const zeroMeaning = lookup({
  unknown: 'Not known',
  not_recorded: 'Nothing was recorded',
  no_answer: 'The question was not answered',
  no_per_source: 'The source’s own description says a 0 means “no”',
  absent: 'The person does not have it',
});

/** The kind of a text about a condition. */
export const kindOfText = lookup({
  description: 'Description',
  symptom: 'Symptoms',
  cause: 'Causes',
  treatment: 'Treatment',
  management: 'Care',
  prevention: 'Prevention',
});

/** A thing to check on a sentence or a list item, as a short tag. */
export const thingToCheck = lookup({
  cut_off: 'text cut short',
  first_item_preposition: 'how the list is worded',
});

/** A kind of wording that changes what a sentence says. */
export const wordingCue = lookup({
  hedge: 'Cautious wording',
  negation: 'Says that something is not so',
  population: 'Names a group of people',
  first_item_preposition: 'First item starts with shared words',
  cut_off: 'Text cut short',
});

export const kindOfName = (type: string): string => (type === 'disease' ? 'a condition' : 'a symptom or other item');
