/** What the panel needs to know about the kind of name it merges: conditions (M2.5c1) or items (M2.20). */
export interface MergeKind {
  /** The word for one of them in the texts of the panel. */
  thing: 'condition' | 'item';
  idField: 'disease_id' | 'feature_id';
  /** Path of the list under the review routes; the history of one is read under it. */
  path: string;
  mergePath: string;
  splitPath: string;
  /** The field of the history answer that holds the other names kept under the same one. */
  othersField: string;
  placeholder: string;
  /** Whether the kept one may be given another name while merging. */
  canRename: boolean;
  /** One more sentence for the explanation, where the service has a rule the reviewer should know. */
  more?: string;
}

export const CONDITION_MERGE: MergeKind = {
  thing: 'condition',
  idField: 'disease_id',
  path: '/diseases',
  mergePath: '/disease-merges',
  splitPath: '/disease-splits',
  othersField: 'synonyms',
  placeholder: 'dis_…',
  canRename: true,
};

export const ITEM_MERGE: MergeKind = {
  thing: 'item',
  idField: 'feature_id',
  path: '/features',
  mergePath: '/feature-merges',
  splitPath: '/feature-splits',
  othersField: 'other_names',
  placeholder: 'feat_…',
  canRename: false,
  more: 'An item that a rule or a question names is the one to keep: the service does not merge it away.',
};
