# Conversation store on Apache Cassandra — design for sub-step C1

Status: **boundary confirmed by the owner on 2026-11-16** (decisions E25, E27, E28 in
`DECISIONS.md`). Implementation has not started; the conversation data is still in PostgreSQL
(M3.3). Versions of Cassandra and its Python driver are chosen and pinned in C2, after checking
the installed packages.

## 1. What moves and what stays

Owner's instruction: user conversations are recorded in Cassandra, not PostgreSQL.

| Data | Today (PostgreSQL table) | Proposed home |
|---|---|---|
| Session header: owner, state, observation version, consent version, demographics, expiry | `sessions` | **Cassandra** |
| What the user wrote and what the assistant asked | `session_messages` | **Cassandra** |
| Interpreted observations and every correction | `session_observations` | **Cassandra** |
| Follow-up answers | `session_answers` | **Cassandra** |
| Assessments returned to the user | `assessments` | **Cassandra** |
| Replay bodies for idempotent requests (they contain the responses above) | `idempotency_keys` | **Cassandra** |
| Audit events (who did what, counts and versions, never content) | `audit_events` | PostgreSQL, without the foreign key to `sessions` |
| Reference, knowledge and review data; imported dataset cases | `sources`, `diseases`, `features`, `statements`, `dataset_cases`, … | PostgreSQL (unchanged) |

Result: after C9 no table in PostgreSQL holds anything a user said or was told.

**Confirmed.** The owner chose this strict boundary: everything in a conversation moves.

### Two sources of truth

| Store | Source of truth for | Never holds |
|---|---|---|
| PostgreSQL | Data: datasets, diseases, features, aliases, statements, evidence, rules, questions, releases, review state | Anything a user said or was told |
| Cassandra | Conversations: session header, messages, answers, observations and corrections, assessments, summaries, replay bodies | Definitions of entities; it stores their PostgreSQL IDs and the release versions in force |

A conversation record therefore says "feature `fx.signal_alpha` under rules release
`fixture-rules-0`", never the feature's name or definition. Renaming or retiring an entity
happens once, in PostgreSQL.

### New entities discovered from conversations go to PostgreSQL

When learning from conversations (step L) finds something the data does not have yet — a
symptom term nobody mapped, a new alias, a new disease label — it is added to PostgreSQL as a
**new record**, not kept in Cassandra. The flow is one-way and deliberately careful:

1. **Aggregate in Cassandra's domain.** Only consented sessions; candidates are counted by
   normalised term across distinct sessions.
2. **Threshold.** Nothing is raised below a minimum number of distinct sessions (D-L3), which
   also keeps a single user's wording from becoming a record.
3. **Strip.** Only the normalised term and counts cross to PostgreSQL. No sentence, session
   ID or user identity.
4. **De-duplicate.** The term is normalised exactly like the dataset crosswalk (casefold,
   trim, collapse whitespace). If it already exists, the existing record gains provenance;
   no second record is created.
5. **Insert as `pending`.** A new `features` / `diseases` / alias record plus a provenance row
   in the same transaction. Approved records are never changed by discovery.
6. **Review and release.** A reviewer approves; a release publishes; only then is the entity
   served or used for extraction, and later conversation records refer to it by ID.

## 2. What changes technically

| Guarantee | PostgreSQL today | Cassandra |
|---|---|---|
| A write is all-or-nothing | Multi-table transaction | Atomic only inside one partition → one session = one partition |
| Stale version rejected | Row lock + conditional `UPDATE` | Lightweight transaction: `… IF observation_version = ?` |
| Caller isolation | Forced row-level security + service filter | No row-level security. Owner is part of the partition key; service builds every query from the verified token |
| Foreign keys to features and questions | Database constraint | Validation in the service (already done before writing) |
| Correction chain cannot fork | Partial unique index on `supersedes` | Follows from the version condition: two corrections on one version cannot both apply |
| Delete | Row deletes in one transaction | Partition tombstone; data disappears from disk after compaction |
| Expiry | `expires_at` checked by the service | Same check, plus TTL so expired data is removed by the database |

## 3. Tables

One keyspace, `feeltriva_conversations`. Table design follows the queries the service runs.

```sql
-- Everything about one session, in one partition.
CREATE TABLE session (
    owner_subject       text,
    session_id          uuid,
    record_type         text,        -- 'message' | 'observation' | 'answer' | 'assessment' | 'op'
    record_id           timeuuid,    -- time-ordered within a type
    -- session header: static = stored once per partition
    state               text static,
    observation_version bigint static,
    consent_version     text static,
    demographics_enc    blob static,
    created_at          timestamp static,
    expires_at          timestamp static,
    -- one record
    observation_version_at bigint,   -- version this record was written at
    body_enc            blob,        -- encrypted JSON: message text, observation, answer or assessment
    supersedes          timeuuid,    -- observations: the record this one corrects
    idempotency_key     text,        -- 'op' records: which request produced this write
    PRIMARY KEY ((owner_subject, session_id), record_type, record_id)
);

-- Saved history: a caller's sessions, newest first. No conversation content.
CREATE TABLE session_by_owner (
    owner_subject text,
    created_at    timestamp,
    session_id    uuid,
    state         text,
    deleted_at    timestamp,
    PRIMARY KEY ((owner_subject), created_at, session_id)
) WITH CLUSTERING ORDER BY (created_at DESC, session_id ASC);

-- Reservation of an Idempotency-Key per caller. No response content here.
CREATE TABLE idempotency (
    owner_subject text,
    key           text,
    request_hash  text,
    operation     text,
    session_id    uuid,
    PRIMARY KEY ((owner_subject), key)
);
```

Why this shape:

- **A session is small** (tens to a few hundred records), so one partition per session is well
  within Cassandra's comfortable partition size and makes a whole-session read one query.
- **The owner is in the partition key.** A request for someone else's session computes a
  different partition and finds nothing: the same 404 as today, by construction.
- **Free text and structured bodies are encrypted by the service** before they are sent
  (the Fernet envelope already used), so Cassandra holds ciphertext.

## 4. How each operation maps

| Operation | Cassandra statements |
|---|---|
| Start session | Reserve key (`INSERT … IF NOT EXISTS` in `idempotency`); `INSERT` header `IF NOT EXISTS` in `session`; row in `session_by_owner` |
| Get session | One partition read; the service resolves current observations (not superseded) as it does now |
| Submit observations / answer | One **conditional batch on the session partition**: `UPDATE session SET observation_version = v+1, state = ? … IF observation_version = v`, plus the new message / observation / answer records and an `op` record carrying the idempotency key and encrypted response. Not applied → HTTP 409 |
| Next question | Partition read, then the rule engine (unchanged) |
| Assess | Partition read → rule engine → conditional batch (`IF observation_version = v`) writing the assessment and `op` record |
| Summary | Partition read → `op` record with the encrypted summary |
| Delete | Delete the partition (removes messages, records and replay bodies together); mark `session_by_owner.deleted_at` |

**Idempotent replay without a cross-table transaction.** The reservation in `idempotency`
only says "this caller used this key for this request and session". The response body is
written as an `op` record *inside the session's conditional batch*, so the write and its
replay record succeed or fail together. A retry finds the reservation, checks the request
hash (different → 409), then looks for the `op` record: present → return it; absent → the
first attempt never applied, so run it again (the version condition prevents double
application).

Consistency: `SERIAL` for the conditional statements, `LOCAL_QUORUM` for other reads and
writes.

## 5. Deletion, expiry and honesty of the receipt

- Deleting the partition removes all conversation content for that session in one statement.
  Physically the data persists as tombstoned SSTable content until compaction and
  `gc_grace_seconds` pass, and in any snapshot or backup taken earlier. The receipt therefore
  stays `deletion_scheduled` until a purge-verification job exists (C8).
- A table-level default TTL removes expired sessions without a job. The value is the
  retention decision that is still open; none is invented here.

## 6. Access control

- Cassandra authentication and authorisation enabled; the API uses a role limited to
  `SELECT`/`MODIFY` on this keyspace. Schema changes use a separate role (C2).
- Every statement is a prepared statement whose partition key comes from the verified
  principal. No tool or endpoint accepts an owner identifier (already true and tested).

## 7. Testing plan

- `ConversationStore` interface with two adapters: in-memory (unit tests, no service needed)
  and Cassandra (integration tests, CI service container).
- The existing API, MCP-parity and contract suites must pass unchanged on both.
- New Cassandra tests: six concurrent writers on one version → one succeeds; five concurrent
  identical retries apply once; another caller cannot address a partition; deleted session is
  unreadable; ciphertext only at rest; TTL expiry.

## 8. Costs and risks to accept knowingly

- **No database-enforced ownership.** PostgreSQL row-level security currently backstops a
  forgotten filter; in Cassandra the partition key and code review are the only barriers.
- **Operational weight.** Cassandra needs noticeably more memory than PostgreSQL even idle;
  this development machine is already resource-constrained (see the M1.7 log entry), and CI
  start-up will take longer.
- **Lightweight transactions are slower** than plain writes (several round trips). Fine at
  conversation rates; to be measured in C11.
- **Two databases to back up, restore and secure** instead of one.
- **Step L depends on this store**: learning events are derived from the conversation log, so
  the export path (change data capture or a scheduled reader) is designed in L1 on top of it.
