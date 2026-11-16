// Regenerates src/fixtures/reviewAudit.generated.ts from the repository's dataset audit
// (data_audit/*). Run with `pnpm gen:review-fixtures` from apps/web.
//
// The output holds audit facts about imported source files: lexical candidates and repeated
// header names. None of it is clinically reviewed content and none of it reaches
// patient-facing screens.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const auditDir = resolve(here, '../../../data_audit');
const outFile = resolve(here, '../src/fixtures/reviewAudit.generated.ts');

/** Minimal RFC 4180 parser (quoted fields, escaped quotes, CRLF). */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      row.push(field);
      field = '';
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i += 1;
      row.push(field);
      field = '';
      if (row.length > 1 || row[0] !== '') rows.push(row);
      row = [];
    } else {
      field += char;
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  const [header, ...body] = rows;
  return body.map((cells) => Object.fromEntries(header.map((name, index) => [name, cells[index] ?? ''])));
}

const audit = JSON.parse(readFileSync(resolve(auditDir, 'audit.json'), 'utf8'));
const featureRows = parseCsv(readFileSync(resolve(auditDir, 'feature_column_mappings.csv'), 'utf8'));
const diseaseRows = parseCsv(readFileSync(resolve(auditDir, 'disease_mappings.csv'), 'utf8'));

// --- Repeated header names (data quality) -----------------------------------------------
const repeatedFile = audit.files.find((file) => file.duplicate_header_count > 0);
const disagreement = repeatedFile.duplicate_column_disagreement_rows;
const inRepeatedFile = featureRows.filter(
  (row) => row.archive === repeatedFile.archive && row.file === repeatedFile.file,
);
const repeatedHeaders = Object.entries(disagreement).map(([term, conflictingRows]) => {
  const columns = inRepeatedFile
    .filter((row) => row.candidate_term === term)
    .map((row) => ({ columnIndex: Number(row.column_index), originalHeader: row.original_header }))
    .sort((a, b) => a.columnIndex - b.columnIndex);
  const first = inRepeatedFile.find((row) => row.candidate_term === term);
  return {
    candidateTerm: term,
    candidateFeatureId: first.candidate_feature_id,
    mappingStatus: first.mapping_status,
    columns,
    conflictingRows,
  };
});

// --- Feature mapping sample ---------------------------------------------------------------
const featureSample = [];
const perArchive = new Map();
for (const row of featureRows) {
  const count = perArchive.get(row.archive) ?? 0;
  if (count < 4) {
    perArchive.set(row.archive, count + 1);
    featureSample.push({
      archive: row.archive,
      file: row.file,
      columnIndex: Number(row.column_index),
      originalHeader: row.original_header,
      candidateTerm: row.candidate_term,
      candidateFeatureId: row.candidate_feature_id,
      mappingStatus: row.mapping_status,
    });
  }
}

// --- Disease mapping sample: the lexical groups that span the most source files -----------
const byCandidate = new Map();
for (const row of diseaseRows) {
  const list = byCandidate.get(row.candidate_disease_id) ?? [];
  list.push(row);
  byCandidate.set(row.candidate_disease_id, list);
}
const widest = [...byCandidate.entries()]
  .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
  .slice(0, 3);
const diseaseSample = widest.flatMap(([candidateId, rows]) => {
  const spellings = new Set(rows.map((row) => row.source_label));
  return rows.map((row) => ({
    archive: row.archive,
    file: row.file,
    sourceLabel: row.source_label,
    normalizedLabel: row.normalized_label,
    candidateDiseaseId: candidateId,
    mappingStatus: row.mapping_status,
    sourceFilesInGroup: rows.length,
    spellingsInGroup: spellings.size,
  }));
});

const facts = {
  sourceArchives: Object.keys(audit.source_sha256).length,
  sourceFiles: audit.files.length,
  lexicalDiseaseCandidates: audit.union_lexical_disease_labels,
  repeatedHeaderNames: repeatedFile.duplicate_header_count,
  repeatedHeaderFile: `${repeatedFile.archive} / ${repeatedFile.file}`,
  sharedArchive15ProfileSignatures: audit.archive15_train_test_shared_profiles_excluding_patient_id,
  positionalFeatureMappings: featureRows.length,
  diseaseMappingRows: diseaseRows.length,
  normalization: audit.normalization,
  clinicalDedupStatus: audit.clinical_dedup_status,
};

const banner = `/**
 * GENERATED by scripts/gen-review-fixtures.mjs from data_audit/ — do not edit by hand.
 *
 * Imported dataset audit facts for the internal reviewer console. These are lexical
 * candidates and header statistics from the supplied archives. They are not clinically
 * approved conditions, not verified symptoms and not counts of unique patients.
 */
`;
const body = [
  `export const AUDIT_FACTS = ${JSON.stringify(facts, null, 2)} as const;`,
  `export const REPEATED_HEADERS = ${JSON.stringify(repeatedHeaders, null, 2)} as const;`,
  `export const FEATURE_MAPPING_SAMPLE = ${JSON.stringify(featureSample, null, 2)} as const;`,
  `export const DISEASE_MAPPING_SAMPLE = ${JSON.stringify(diseaseSample, null, 2)} as const;`,
].join('\n\n');

writeFileSync(outFile, `${banner}\n${body}\n`);
console.log(
  `Wrote ${outFile}: ${repeatedHeaders.length} repeated headers, ${featureSample.length} feature rows, ${diseaseSample.length} disease rows.`,
);
