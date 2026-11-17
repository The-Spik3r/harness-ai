---
id: PRD-024
slug: semantic-duplicates
title: Semantic Duplicate Detection — Near-Identical Rephrasings Held Within Today's Scope, Shadowed Before Enforced
status: draft
base_branch: main
epic_branch: epic/PRD-024-semantic-duplicates
created: 2026-11-16
updated: 2026-11-16
---

> **Relation to PRD-020.** [PRD-020](../PRD-020-provider-registry/PRD.md) (provider registry, draft) defines providers with `trust: internal` / `trust: external` (its D7) and a `ProviderAdapter` protocol with `complete()` and `stream()` (its D11, Section 6.4). It has **no embeddings endpoint**. Nothing here is built on it: Section 9.3 reasons about what an embedding provider would do to the check order, and D2 keeps this PRD independent of it.

## 1. Executive Summary

Duplicate detection is exact-match. `dedup_key(user_id, turns)` ([app/services/duplicate_checker.py:78-121](../../../app/services/duplicate_checker.py)) is a SHA-256 over a version tag, the credential-resolved user id, `hash_prompt(anchor)` and a hash of the prefix. The anchor is the last `user` turn and the prefix is everything else, with the anchor's slot marked `null` once tool turns are present (PRD-017 D4). `find_duplicate_timestamp` ([app/db/database.py:857-899](../../../app/db/database.py)) matches on that key, for the same `user_id`, inside 24 h, and only against rows with a real verdict. Because the key is a hash, it is also whitespace-sensitive and case-sensitive (PRD-009 F3). `"Summarise this week's incidents"` and `"summarise this weeks incidents."` are two different queries. The chat UI's held bubble even tells the user how to get past the check: *"Change the wording before you send it again."* ([chat_ui/chat_ui/copy.py:99](../../../chat_ui/chat_ui/copy.py)).

This PRD adds a **second, optional match tier**. The context still has to match exactly, and the anchor only has to match closely. When the exact lookup misses, the anchor text is embedded **in-process** by a small pinned ONNX sentence model and compared by cosine similarity against the caller's own qualifying rows in the same exact context and the same 24 h window. A match above the profile's threshold that survives a lexical veto (different identifiers, numbers, quoted strings or negation never match) is a *semantic duplicate*. It can be recorded only (`shadow`) or held (`enforce`). A held request gets the same `BLOCKED` shape with a distinguishing reason, its own response type and its own `/v1` code. The feature is **off by default**. When it is off, the pipeline, every response and every audit row's content are what they are today, and the model is never loaded.

The main risk is false positives, not misses. `"fix the bug in foo()"` and `"fix the bug in bar()"` are close in embedding space and must never be held. So the `code` profile (all of `/v1`) is excluded by default, the identifier veto runs before any threshold is consulted, and enforcement is gated on a shadow period plus a labelled evaluation corpus with a precision target.

**MVP goal:** with `DUPLICATE_SEMANTIC_MODE=shadow`, a paraphrase on `/query` is answered and its row records which earlier row it would have matched and at what similarity. With `enforce`, the same paraphrase is held with `reason: "Similar query within 24 hours"`. `"fix the bug in foo()"` / `"…bar()"` and the rest of the hard-negative corpus are never held. With `off`, the full existing suite passes unmodified and no embedding is computed or stored.

## 2. Mission

Catch the repeat a person would call a repeat, without ever holding a request that asks for something different, and without moving a single boundary PRD-009 drew.

Core principles:

- **Fuzz the anchor, never the scope.** Same user, same exact context hash, same window, same "what counts as a prior query" predicates as PRD-009. Similarity only relaxes *how equal the last user turn must be*. A semantic match is therefore always a subset of "same caller, same conversation" (D3).
- **Precision over recall.** A missed paraphrase costs one extra model call, which usage limits already bound. A false hold costs a user their question for a day. Every tunable defaults to fewer holds (D6, D7, D8).
- **Shadow before enforce.** The first enabled mode records what it would have done and blocks nothing (D9). Enforcing is a separate, deliberate setting change, made after the shadow report has been read.
- **Text never leaves the process for this check.** The embedding is computed in-process over raw text. No prompt goes to a third party before the pattern and PII steps have decided on it (D2, Section 9.3).
- **Embeddings are personal data.** They are stored apart from the audit trail, never exposed by an API, and deleted with the window (D5).
- **Off is today.** `off` adds no round trip, no model load, no import of the inference runtime and no column value. The exact tier is untouched in every mode (D10).

## 3. Target Users

**End User (chat UI / `/query`).** Rephrases a question they already got an answer to, often without noticing, or in a fresh chat session. In `enforce` they want the hold to say *what* it matched and *when*, and to tell them how to proceed when they really mean something different. Today's copy tells them to reword, which semantic detection makes wrong advice.

**Integrating Developer / coding agent operator.** Runs `/v1` under the `code` profile. Needs the guarantee that semantic matching never holds an agent step because two prompts name different functions, files or numbers. By default the `code` profile is not checked at all (D6).

**Security/Compliance Admin.** Owns the control. Needs a shadow report of would-be holds, with the two prompt previews side by side, to judge precision on real traffic before enforcing. Needs the retention of a new kind of personal data (embeddings) bounded and documented, and the existing figures (`blocked_duplicates`, `/audit`) to stay interpretable.

**Platform Operator.** Owns `.env` and the image. Needs one mode switch, a profile list, a threshold, a measured latency cost, and a known image-size cost.

## 4. MVP Scope

### In Scope

**Settings (`app/config.py`)**
- [ ] `DUPLICATE_SEMANTIC_MODE: Literal["off","shadow","enforce"] = "off"` (D9, D10)
- [ ] `DUPLICATE_SEMANTIC_PROFILES: str = "chat"`. A comma list of profile names that are checked. Each entry is validated against the pattern profiles at startup, the way `PATTERN_PROFILE_DEFAULT` is (D6)
- [ ] `DUPLICATE_SEMANTIC_THRESHOLD: float = 0.92`, in (0, 1], with an optional per-profile override `DUPLICATE_SEMANTIC_THRESHOLD_CODE` (D7)
- [ ] `DUPLICATE_SEMANTIC_MAX_CANDIDATES: int = 200` (D4)
- [ ] `DUPLICATE_SEMANTIC_MIN_WORDS: int = 4` (D8)

**Key decomposition (`app/services/duplicate_checker.py`)**
- [ ] `dedup_parts(user_id, turns) -> DedupParts(anchor_text, prefix_hash)` factored out of `dedup_key`. `dedup_key` composes it, and every key stays byte-identical (`tests/test_dedup_key.py` unmodified)
- [ ] `dedup_context_hash(user_id, parts) -> str`, a versioned (`"s1"`) SHA-256 over `[version, user_id, prefix_hash]`. It is the semantic tier's scope key (D3)

**Embedding (`app/services/embedder.py`, new)**
- [ ] `embed(text) -> bytes`: the L2-normalised float32 vector, little-endian, from the pinned ONNX model through `onnxruntime` + `tokenizers` (D1). Lazy import, loaded only when mode ≠ `off`
- [ ] `token_count(text)`, so the pipeline can skip anchors that would be truncated (D8)
- [ ] Startup warm-up and a fixed self-test pair when mode ≠ `off`. A model that cannot load or that disagrees with the self-test stops the boot

**Matching (`app/services/semantic_duplicates.py`, new; pure except for the lookup it is handed)**
- [ ] Eligibility: mode, profile, anchor length (min words, max tokens) (D6, D8)
- [ ] Lexical veto: any difference in identifiers, numbers, quoted strings, paths/URLs or negation markers means no match, whatever the similarity (D7)
- [ ] Cosine over the candidates; the best candidate at or above the threshold that passes the veto is the match. Ties go to the earliest row, so `first_query_at` reads like the exact tier's
- [ ] No import of the PII stack (`test_duplicate_checker_has_no_redaction_dependency` is extended to this module)

**Storage (`app/db/`)**
- [ ] New table `dedup_embeddings(audit_id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, context_hash TEXT NOT NULL, timestamp TEXT NOT NULL, model_version TEXT NOT NULL, embedding BLOB NOT NULL)`, plus `idx_dedup_embeddings_scope(user_id, context_hash, timestamp)` and `idx_dedup_embeddings_ts(timestamp)` (D4, D5)
- [ ] `find_semantic_candidates(user_id, context_hash, model_version, since, limit)`, which joins `audit_logs` with exactly the predicates of `find_duplicate_timestamp` (factored into one shared SQL fragment, so the two tiers cannot drift)
- [ ] `insert_dedup_embedding(...)`, plus per-user pruning on insert, a global sweep in `init_db()`, and a full purge when mode is `off` (D5)
- [ ] `audit_logs` gains `semantic_outcome TEXT`, `semantic_match_id INTEGER` and `semantic_similarity REAL`: nullable, no default, no backfill, not indexed, `NULL` whenever mode is `off` (Section 6.5)

**Pipeline (`app/services/query_pipeline.py`)**
- [ ] Step 4b, directly after an exact miss at step 4 ([query_pipeline.py:534-562](../../../app/services/query_pipeline.py)) and before patterns (step 5). Step 4 itself is unchanged
- [ ] `enforce` + match: a hold row (`was_duplicate_blocked=1`, `semantic_outcome='blocked'`) and `QueryBlockedSemanticDuplicateResponse`
- [ ] `shadow` + match: the request continues; every row it writes carries `semantic_outcome='shadow'` plus the match fields
- [ ] Embedding stored after the success row (step 8) and after a pattern-**block** row (step 5), which are the two rows PRD-009 F4 counts. Never for failures, denials, flags, limit refusals or holds

**Responses and doors**
- [ ] `QueryBlockedSemanticDuplicateResponse(status="BLOCKED", reason="Similar query within 24 hours", first_query_at, match="semantic")` in `app/models/schemas.py`. It is **not** a subclass of `QueryBlockedDuplicateResponse` (D11)
- [ ] Added to `QueryPipelineResult` and `v1_translate.QueryBlockedResponse`. `/v1`: 400 `invalid_request_error`, code `semantic_duplicate_request` (D12)
- [ ] Chat UI: its own branch beside [state.py:1222](../../../chat_ui/chat_ui/state.py), a held bubble with new copy (Section 7, F8)

**Evaluation and operations**
- [ ] `tests/fixtures/semantic_duplicates_corpus.yaml`: labelled pairs, hard negatives first (Section 7, F6)
- [ ] `tests/test_semantic_eval.py`, marked `semantic_eval`, opt-in like `e2e`, runs the real model against the corpus and asserts the precision target
- [ ] `scripts/semantic_shadow_report.py`: would-be holds over a period, with both previews, similarity and veto results, for the admin to label
- [ ] `scripts/measure_semantic_latency.py`, in the shape of `scripts/measure_usage_latency.py`

**Documentation**
- [ ] `docs/features.md` *Duplicate detection scope* gains a *Semantic matching* subsection. `docs/roadmap.md:37` is ticked. `.env.example` lists the five settings. `docs/deployment.md` gets the image-size and CPU notes

### Out of Scope

- [ ] Embeddings from a provider, local or cloud, including anything through PRD-020 (D2, Section 9.3)
- [ ] Widening scope: cross-user matching, matching across different contexts, fuzzy matching of the prefix, or a configurable window
- [ ] libSQL native vector indexing (`libsql_vector_idx` / `vector_top_k`). Native vector functions are not used in the MVP (D4)
- [ ] Semantic matching on the `code` profile by default (it can be enabled, D6)
- [ ] Multilingual models (Open decision OD3)
- [ ] A caller-side override ("send anyway") (Open decision OD1)
- [ ] Exposing embeddings, `semantic_*` columns or `dedup_key` on `GET /audit` (PRD-009 D5 extended)
- [ ] Changing the exact tier: its key, lookup, response, reason string, `/v1` code or the storage-failure behaviour (500)

## 5. User Stories

1. **As an end user, I want an obvious rephrasing of a question I was just answered to be recognised, so that I am pointed at the answer I already have instead of paying for it twice.**
   *Example:* Juan sends `"Summarise this week's incidents"` on `/query` at 09:00 and is answered. At 09:20 he sends `"summarise the incidents from this week"`. In `enforce`, he gets `BLOCKED`, `reason: "Similar query within 24 hours"`, `first_query_at: "…T09:00:00Z"`, `match: "semantic"`.

2. **As an end user, I want a different question that merely sounds similar to be answered, so that the check never costs me a real request.**
   *Example:* `"Draft the Q3 vendor summary"` then `"Draft the Q4 vendor summary"`: the number veto fires (`3` ≠ `4`) and the request is answered. `"Enable the cache for staging"` then `"Disable the cache for staging"` has similarity above 0.9, but the negation veto (`disable`) fires and the request is answered.

3. **As an integrating developer, I want agent steps that name different symbols never to be held, so that semantic matching cannot stall a tool loop.**
   *Example:* by default `/v1` runs `code`, which is not in `DUPLICATE_SEMANTIC_PROFILES`, so nothing is checked. Even with `code` enabled, `"fix the bug in foo()"` vs `"fix the bug in bar()"` differ in their identifier sets (`foo()` / `bar()`), and the veto fires before the threshold is read.

4. **As a security admin, I want a shadow period that shows what would have been held, so that I can measure precision on our own traffic before I enforce.**
   *Example:* with `shadow` for a week, `python scripts/semantic_shadow_report.py --since 2026-12-01` lists 37 would-be holds with both previews and their similarity. The admin marks 2 as wrong, raises the threshold to 0.94, re-runs the report on the same rows (the stored similarity is re-tested against the new threshold), and then switches to `enforce`.

5. **As a security admin, I want a semantic hold never to extend or widen the window, so that the control keeps exactly the scope PRD-009 reasoned about.**
   *Example:* María's paraphrase of Juan's prompt is answered (other user). Juan's paraphrase after his own *failed* attempt is answered (failures never count). A paraphrase held at 23 h is answered at 25 h, because a hold is never a candidate.

6. **As a compliance admin, I want embeddings kept only as long as the window and never served by any API, so that a new derivative of prompt text does not become a long-lived record.**
   *Example:* a row's embedding is deleted at the next insert by the same user after 24 h, or at the next boot, whichever comes first. Switching the mode to `off` deletes every embedding at the next boot.

7. **As an operator, I want `off` to be today's harness, so that shipping the release changes nothing until I opt in.**
   *Example:* with the default `.env`, `onnxruntime` is never imported, `dedup_embeddings` stays empty, every `semantic_*` column is `NULL`, and `POST /query`, `/v1` and the chat UI return byte-identical responses.

## 6. Core Architecture & Patterns

### 6.1 Request flow

```
step 1   parts = dedup_parts(user_id, messages)     key = dedup_key(...)  (unchanged bytes)
step 2…3 authorize, break-glass, usage gate, context limits                 (unchanged)
step 4   check_duplicate(user_id, key) ──hit──► exact hold                  (unchanged)
step 4b  if mode != off and profile in PROFILES and eligible(parts.anchor_text):
           vec   = embed(anchor_text)                         in-process, raw text
           cands = find_semantic_candidates(user_id, ctx_hash, model_version, now-24h, N)
           match = best(cands, vec, threshold, veto)
           enforce + match ──► log_query(was_duplicate_blocked, semantic_outcome='blocked') ──► semantic hold
           shadow  + match ──► carry (match_id, similarity) onto every later row
step 5   patterns ──block──► row (+ insert_dedup_embedding if vec)
step 6   PII redaction                                                       (unchanged)
step 7…  upstream, charge, action policy                                     (unchanged)
step 8   success row (+ insert_dedup_embedding if vec)
```

**Why 4b sits there.** It runs after every authorization arm and the usage gate, so an unauthorized or over-budget caller never costs an inference. It runs after step 3, so the input is already bounded by `CONTEXT_MAX_CHARACTERS` (`app/config.py:256`). It runs after the exact tier, so an exact repeat is held exactly as today, with today's reason, and never reaches the model. It runs before patterns and redaction, the same position the exact check holds (PRD-009 Section 9.2 invariant). Because the embedding is in-process (D2), that position sends nothing anywhere.

### 6.2 What is compared: the anchor, inside an exact context

`dedup_key` already computes two halves: `hash_prompt(anchor)` and `prefix_hash` ([duplicate_checker.py:106-121](../../../app/services/duplicate_checker.py)). The refactor exposes them without changing a byte:

```python
@dataclass(frozen=True)
class DedupParts:
    anchor_text: str     # last turn (tool-free) or last user turn (tool-shaped, PRD-017 D4)
    prefix_hash: str     # "" for an empty prefix, as today

def dedup_key(user_id, turns) -> str:
    p = dedup_parts(user_id, turns)
    return _sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(p.anchor_text), p.prefix_hash])

SEMANTIC_CONTEXT_VERSION = "s1"
def dedup_context_hash(user_id, p: DedupParts) -> str:
    return _sha256_json([SEMANTIC_CONTEXT_VERSION, user_id, p.prefix_hash])
```

Two requests are candidates for each other only if their `context_hash` is equal. That means the same user and a byte-identical prefix (system prompt, history and tool turns, with the anchor slot marked). In practice that leaves three populations, and the PRD states them rather than oversell the feature:

1. **Single-turn `/query` and the chat UI's history-off branch** (empty prefix). This is the main population.
2. **The first message of a new chat session or a new `/v1` conversation** with the same system prompt.
3. **"Edit and resend" of the last turn** (chat UI, or a `/v1` client regenerating), where the prefix is unchanged and only the anchor differs.

A follow-up asked *after* an answer has a longer prefix (the answer is in it), so it is never compared with the original. That is the same reason PRD-017 gives for `npm test` twice in one loop not being a duplicate, and semantic matching keeps it.

### 6.3 Candidate lookup

```sql
SELECT e.audit_id, e.embedding, a.timestamp
FROM dedup_embeddings e JOIN audit_logs a ON a.id = e.audit_id
WHERE e.user_id = ? AND e.context_hash = ? AND e.model_version = ? AND e.timestamp >= ?
  AND a.user_id = e.user_id
  AND <PRIOR_QUERY_PREDICATES>          -- the exact tier's five, shared text
ORDER BY e.timestamp DESC
LIMIT ?                                  -- DUPLICATE_SEMANTIC_MAX_CANDIDATES
```

`<PRIOR_QUERY_PREDICATES>` is the block at [database.py:889-893](../../../app/db/database.py) (`success = 1`, `was_duplicate_blocked = 0`, `denied_permission IS NULL`, not a pattern flag, `limit_exceeded IS NULL`), moved into one module-level constant that both lookups interpolate. A test asserts that both queries contain it verbatim. The JOIN is what makes "failed attempts never count" automatic, including the late flip by `mark_audit_log_failed` ([database.py:902-917](../../../app/db/database.py)), which writes nothing to `dedup_embeddings`.

Cosine is computed in Python. Vectors are L2-normalised at write time, so cosine is a dot product. Each query is one round trip and transfers at most N × 1,536 bytes (384 float32), about 300 KB at N = 200. The typical case is a handful of rows.

### 6.4 The lexical veto

The veto is a pure function, `distinguishing_tokens(text) -> frozenset[str]`. Two anchors can match only if these sets are **equal**:

| Class | Extracted as | Catches |
|---|---|---|
| Identifiers | tokens with `_`, `.`, `::`, `/`, `()`, inner capitals (`fooBar`), or inside backticks | `foo()` vs `bar()`, `src/a.ts` vs `src/b.ts` |
| Numbers | digit runs, normalised (`Q3`→`3`, `1,000`→`1000`) | Q3/Q4, ticket #123/#124, `v2`/`v3` |
| Quoted strings | `"…"`, `'…'` contents, casefolded | `rename it to "alpha"` vs `"beta"` |
| URLs, e-mails | regex, casefolded | different targets |
| Negation markers | a fixed set (`not`, `no`, `never`, `don't`, `disable`, `remove`, `without`, `stop`, `un-`…) as a presence set | enable/disable, with/without |

The veto only ever *prevents* a match. A rephrasing keeps its numbers, identifiers and quotes, so recall loses little. The veto has no PII dependency: proper names (`Alice`/`Bob`) are not extracted, which is a known gap that the corpus measures and Open decision OD4 addresses.

### 6.5 Audit columns

| Column | Written when | Values |
|---|---|---|
| `semantic_outcome` | mode ≠ `off` and step 4b ran or was skipped for a reason | `blocked`, `shadow`, `vetoed`, `below`, `no_candidates`, `skipped_short`, `skipped_long`, `skipped_profile`, `error` |
| `semantic_match_id` | `blocked`, `shadow`, `vetoed` | the matched (or vetoed best) row's `audit_logs.id` |
| `semantic_similarity` | the same three | cosine, rounded to 4 places |

These columns travel the PRD-009/011/012/013 path through `AUDIT_LOGS_ADDED_COLUMNS`, with no new code in `_add_missing_columns()` ([database.py:746-799](../../../app/db/database.py)). Rows written before step 4b (denials, usage refusals, context refusals, exact holds) leave them `NULL`. `vetoed` keeps the best-but-vetoed match, so the shadow report can show that the veto is earning its keep.

### 6.6 Directory structure (files touched)

```
app/
  config.py                       # five settings + validators
  models/schemas.py               # QueryBlockedSemanticDuplicateResponse
  db/models.py                    # dedup_embeddings DDL + indexes; three audit columns; AuditLog fields
  db/database.py                  # shared predicates; find_semantic_candidates; insert/prune/purge; init_db()
  services/duplicate_checker.py   # dedup_parts, dedup_context_hash (keys unchanged)
  services/embedder.py            # new: onnxruntime + tokenizers, lazy
  services/semantic_duplicates.py # new: eligibility, veto, best match
  services/query_pipeline.py      # step 4b; embedding insert at steps 5 and 8
  services/v1_translate.py        # union member, _VERDICTS row, code
chat_ui/chat_ui/state.py, copy.py # semantic hold bubble
Dockerfile                        # model baked at build time, hash-checked
scripts/semantic_shadow_report.py, scripts/measure_semantic_latency.py
tests/  test_dedup_parts.py, test_semantic_veto.py, test_semantic_scope.py,
        test_semantic_pipeline.py, test_semantic_off_is_today.py, test_semantic_eval.py,
        fixtures/semantic_duplicates_corpus.yaml
```

### 6.7 Patterns followed

- **Pure core, injected I/O.** The same split as `action_policy.evaluate_all` (PRD-016): `semantic_duplicates.best_match(vec, candidates, threshold, anchor_text)` is pure. The pipeline does the embedding and the lookup.
- **Additive schema in the one `init_db()` block.** The new table arrives by `CREATE ... IF NOT EXISTS`, like `action_decisions` (PRD-016 STORY-015). Its position is not load-bearing.
- **Baked models.** Like `en_core_web_lg` ([Dockerfile:63](../../../Dockerfile)), the model is fetched at build time and never downloaded at runtime.
- **By-name binding for spies.** `query_pipeline` imports `embed` by name, so tests replace `query_pipeline.embed` with a deterministic fake (the rule `_redact` documents, [query_pipeline.py:225-242](../../../app/services/query_pipeline.py)).

## 7. Tools/Features

**F1 — Key decomposition.** `dedup_parts` and `dedup_context_hash`. Properties: `dedup_key` is byte-identical for every case in `tests/test_dedup_key.py` and `tests/test_query_pipeline_dedup_key.py`, which are run unmodified. The context hash differs across users and across prefixes, and is equal for two conversations that differ only in the anchor.

**F2 — Embedder.** Model: `sentence-transformers/all-MiniLM-L6-v2` exported to ONNX (384 dimensions, 256-wordpiece window), the file's SHA-256 pinned in the Dockerfile. `onnxruntime.InferenceSession` with `intra_op_num_threads=1` (the pipeline executor already runs up to `PIPELINE_MAX_WORKERS=32` threads, `app/config.py:260`, and oversubscribing cores would slow every request). Mean pooling + L2 normalisation, as the model card specifies. `MODEL_VERSION = "minilm-l6-v2@<sha256[:12]>"` is stored per row, so a model change never compares vectors across models.

**F3 — Eligibility.** Skip, and record why, when the profile is not listed, when the anchor has fewer than `DUPLICATE_SEMANTIC_MIN_WORDS` words (short turns like "yes", "go on" or "thanks" embed unstably, and the exact tier already handles them in context), or when `token_count(anchor) > 256`. In the last case the model would see only a truncated head, and two long prompts sharing an opening would look identical. Over the window, the request is exact-only.

**F4 — Match.** Best cosine among the candidates that pass the veto. The match must be `>= threshold(profile)`. Tied best similarities go to the earliest candidate. The result is `(audit_id, timestamp, similarity)` or a non-match reason.

**F5 — Storage lifecycle.** Insert after steps 5 (block) and 8 (success). The insert deletes the same user's rows older than 24 h + 1 h of slack, which the scope index serves. `init_db()` deletes all rows older than that through the timestamp index, and deletes every row when mode is `off`. An insert failure is logged at `ERROR` and the response is still delivered (fail open, like the usage charge, `docs/features.md:214`): the only loss is that the next paraphrase is not caught.

**F6 — Evaluation corpus.** YAML pairs `{a, b, label: hold|answer, profile, note}`, at least 200 pairs at merge. At least 60% are hard negatives: identifier, number, quote, negation, entity-swap (`Alice`/`Bob`), language-swap (`translate to French`/`German`), scope-swap (`summarise`/`list`), long-prefix-same-opening. The rest are paraphrases: casing, punctuation, word order, synonyms, filler. The targets are **precision 1.00 on the hard-negative subset** (no `answer` pair held) and **overall precision ≥ 0.99**. Recall is reported, not gated (D7). `test_semantic_eval.py` fails if either target is missed at the configured default threshold.

**F7 — Shadow report.** Reads `audit_logs` rows with `semantic_outcome IN ('shadow','vetoed')` in a range, joins `semantic_match_id` to the earlier row, and prints both `prompt_preview`s (already stored, 500 characters, raw, `app/services/audit_logger.py:78`), the similarity, and whether each would hold at a `--threshold` given on the command line. Output is a terminal table or `--csv`. It needs database access and never goes through the API.

**F8 — What the user sees.** `/query` returns 200 with the body in Section 10. `/v1` returns 400 `semantic_duplicate_request`. The chat UI shows a held bubble tagged `HELD` (the existing `TAG_DUPLICATE`) with new copy: *"Very close to a question you asked {relative} ({absolute})."* and, in place of the reword advice, *"If you're asking something different, say what's different — a name, a number, a file."* That advice is true by construction: any change to a distinguishing token defeats the veto. The exact hold's copy is unchanged.

## 8. Technology Stack

| Layer | Technology | Use in this PRD |
|---|---|---|
| Runtime | Python 3.11 (`Dockerfile`: `python:3.11`, `python:3.11-slim`) | unchanged |
| Inference | `onnxruntime` (CPU), `tokenizers` (Rust), `numpy` (an onnxruntime dependency) | **new pins**, exact versions chosen in STORY-001 |
| Model | `all-MiniLM-L6-v2`, ONNX, fp32 (int8 quantised as OD5) | baked at build, hash-checked |
| Storage | Turso / libSQL, `libsql==0.1.11`, test server `ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb27…` ([tests/conftest.py:47](../../../tests/conftest.py)) | a plain table with a `BLOB` column; no vector extension used |
| PII stack | Presidio `2.2.364`, spaCy `3.8.16`, `en_core_web_lg` | **not used** by this PRD (D1, D7) |
| Tests | pytest, existing `temp_db` fixtures, a deterministic fake embedder; `-m semantic_eval` for the real model | |

**Embedding source options considered (D1):**

| Option | Verdict |
|---|---|
| spaCy `en_core_web_lg` document vectors (already in the image) | **Rejected.** They are an average of static word vectors, so they ignore word order and negation. Out-of-vocabulary identifiers contribute nothing, so `fix the bug in foo()` and `…bar()` reduce to nearly the same vector: the exact false positive this PRD must not produce. The model also belongs to the PII stack, which the duplicate checker is tested never to import. |
| `sentence-transformers` in-process | **Rejected.** It pulls in PyTorch, whose CPU build is several hundred MB installed (*unverified figure*), for a 384-dimension encoder. |
| `fastembed` | **Rejected.** It downloads models at runtime by default, while this image bakes its models. It also adds a dependency surface for what is about 60 lines of `onnxruntime` + `tokenizers`. |
| **`onnxruntime` + `tokenizers` + pinned ONNX MiniLM** | **Chosen.** It is small (the model is about 90 MB fp32, about 23 MB int8, *unverified*), it has no runtime egress, and `InferenceSession.run` is expected to release the GIL (*to be confirmed in STORY-001*). |
| An embedding endpoint (OpenRouter, a PRD-020 provider) | **Out of scope** (D2, Section 9.3). PRD-020's adapter has no embeddings call |

Skill constraints: `.agents/skills/` contains only `frontend-design`, which covers UI visual design. The only UI change is a held-bubble copy variant inside the existing component, so no skill rule applies to Sections 6, 8, 9 or 11.

## 9. Security & Configuration

### 9.1 Authentication & authorization

Unchanged. `user_id` in the context hash, in the lookup's `WHERE` and in the JOIN is `identity.user_id`, resolved from the credential, as at step 4 ([query_pipeline.py:536-540](../../../app/services/query_pipeline.py)). `a.user_id = e.user_id` is defence in depth: an embedding row whose `audit_id` pointed at another user's audit row could never match.

### 9.2 Threat reasoning

| # | Change | Effect on the control | Assessment |
|---|---|---|---|
| T1 | Near-match on the anchor | **Stronger against lazy evasion**: trailing space, casing, punctuation or light rewording no longer gets a repeat through. | It is not a defence against a determined caller. Appending an unrelated sentence, changing a number or using another language drops below the threshold or trips the veto. The abuse bound stays PRD-013's usage limits. Stated in `docs/features.md`, not implied. |
| T2 | Scope is unchanged | **Neutral.** Same user, exact context, same window, same prior-query predicates (shared SQL text). | Cross-user poisoning (PRD-009 T2) cannot return: a semantic candidate is always the caller's own row. A test sends María's paraphrase of Juan's prompt and asserts it is answered. |
| T3 | False positive holds a different request | **New harm**: a legitimate request is refused for up to 24 h. | This is the main risk. It is mitigated by the `code` profile excluded by default (D6), the veto before the threshold (D7), skipping short and over-window anchors (D8), shadow before enforce (D9), the corpus precision gate (F6), and a hold that names the match time and says how to proceed (F8). |
| T4 | Poisoning one's own window | **Self-harm only.** A caller can only hold their own future paraphrases. | Accepted. |
| T5 | A hold never counts | **Unchanged semantics** (PRD-009 D3): a hold is `was_duplicate_blocked=1`, excluded by the predicates, so holds never chain the window. | Asserted at 23 h / 25 h. |
| T6 | Embeddings stored | **New personal data.** Sentence embeddings can be partially inverted to recover text (published inversion attacks; extent for this model *unverified*). | A separate table, never exposed by any API or log line, retention ≤ 24 h + 1 h + time to the next insert or boot (D5), purged entirely when `off`. The same text is already stored raw in `prompt_preview` (500 characters, indefinitely), so the embedding adds coverage beyond 500 characters for at most a day. It does not add a new class of exposure to a database reader. |
| T7 | Embedding over raw text | **Required for correctness.** Redacted text collapses distinct prompts (`tests/test_pii_dedup_isolation.py:105`, `test_two_pii_prompts_collide_after_redaction`), which here would be a false positive between two customers. | Raw text, as the exact key (PRD-009 Section 9.2 invariant). In-process only, so raw text reaching the encoder is not egress. |
| T8 | Inference before patterns | **Neutral.** An injection attempt is embedded before step 5 blocks it. | The encoder runs locally and produces numbers. Its input cannot steer anything: no tool, no network, no prompt template. A pattern-blocked row stores an embedding because PRD-009 F4 counts it as a prior query, so a paraphrased resend of an injection is held too. |
| T9 | Model or storage fault | **Choice:** a storage fault at the lookup → `DuplicateCheckError` → 500, as the exact tier (fail closed, `app/routers/query.py:31`). An inference fault → `semantic_outcome='error'`, `ERROR` log, the request continues (fail open). | Fail open on inference because the exact tier still protects and a broken encoder must not take every chat request down. The boot self-test makes runtime inference faults rare. Open decision OD2. |
| T10 | CPU as a resource | **New DoS surface**: every eligible request costs an inference. | It is bounded upstream: only authorized callers, after the per-minute rate (`USAGE_REQUESTS_PER_MINUTE`, `app/config.py:355`) and after the context limit. Inputs over 256 wordpieces are skipped before inference, apart from tokenisation. |

Invariants, each asserted by a test:

- With mode `off`, `embedder` and `onnxruntime` are never imported (`sys.modules` check), and `dedup_embeddings` has no rows after any suite scenario.
- With any mode, every exact-tier outcome is identical: the reason string, `first_query_at`, the `/v1` code `duplicate_request` and the row.
- A semantic candidate is never another user's row, never a different context, and never a non-qualifying row.
- `semantic_duplicates` and `embedder` import nothing from the PII stack.
- The check order is authorization → usage → context → exact → semantic → patterns → redaction.

### 9.3 Why not an embedding provider (PRD-020)

If step 4b called an embedding endpoint, **the raw prompt would leave the harness before step 5 (patterns) and step 6 (PII) have decided on it**. That reverses what the README promises: a blocked request never reaches a provider ("short-circuit before the provider", `README.md:146`), and redaction precedes all egress. Three ways out exist, and each costs something:

1. **Embed after redaction (move to step 6½).** The PII problem goes away, but T7 replaces it: masked customers collide into false positives. The ordering also changes, so redaction (the most expensive step) runs on requests that are then held, and a pattern-blocked row would have no embedding.
2. **Embed raw text, but only through a PRD-020 provider marked `trust: internal`** (a loopback or self-hosted endpoint inside the network, PRD-020 D7). That is the operator's assertion that data does not leave the network, which PRD-020 also relies on for `pii: relaxed`. This is equivalent to in-process in privacy terms, and adds a network hop and a new failure mode. It follows the spirit of PRD-020 Section 6.8 rule 1: raw text never flows to an `external` provider by default.
3. **Embed raw text through a cloud provider.** **Rejected**: a third party receives every eligible prompt, including the ones patterns would block and the PII the profile masks.

The MVP takes neither path (D2). Option 2 is the extension point, and it is an **addition to PRD-020**, not something it offers today. PRD-020's `ProviderAdapter` (D11) has only `complete()` and `stream()`, both chat completions. An `embed()` method, or a separate embeddings adapter for the OpenAI-compatible `/embeddings` route, plus a per-model `embeddings` capability in the registry, would have to be added there. On this side, `embedder` becomes an interface with the in-process implementation and a provider implementation, and a startup validator refuses any embedding provider that is not `trust: internal`.

### 9.4 Configuration

| Variable | Default | Notes |
|---|---|---|
| `DUPLICATE_SEMANTIC_MODE` | `off` | `off` \| `shadow` \| `enforce` |
| `DUPLICATE_SEMANTIC_PROFILES` | `chat` | Comma list. Each entry must name a pattern profile, and an empty list with mode ≠ `off` is a startup error |
| `DUPLICATE_SEMANTIC_THRESHOLD` | `0.92` | (0, 1]. Provisional: STORY-001's corpus run sets the shipped value |
| `DUPLICATE_SEMANTIC_THRESHOLD_CODE` | unset (inherits; `0.97` recommended if `code` is listed) | Per-profile override |
| `DUPLICATE_SEMANTIC_MAX_CANDIDATES` | `200` | ≥ 1 |
| `DUPLICATE_SEMANTIC_MIN_WORDS` | `4` | ≥ 1 |

Every validator error names the variable, the rule and an example, as `OPENROUTER_BASE_URL`'s does ([app/config.py:489-531](../../../app/config.py)).

### 9.5 Out of scope (security)

Provider-sourced embeddings, encryption at rest of the embedding column beyond what Turso provides, protecting embeddings against an actor with database read access (who already reads `prompt_preview`), and cross-user near-duplicate abuse detection (a usage-limits concern).

## 10. API Specification

`POST /query`, semantic hold (200):

```json
{
  "status": "BLOCKED",
  "reason": "Similar query within 24 hours",
  "first_query_at": "2026-12-01T09:00:00Z",
  "match": "semantic"
}
```

The exact hold body is unchanged: `{"status":"BLOCKED","reason":"Duplicate query within 24 hours","first_query_at":…}`, with no `match` field (D11).

`POST /v1/chat/completions`, semantic hold: 400, `x-should-retry: false`:

```json
{"error": {"type": "invalid_request_error", "code": "semantic_duplicate_request",
           "message": "Similar query within 24 hours: similar to a query first seen 2026-12-01T09:00:00Z",
           "harness": {"reason": "Similar query within 24 hours",
                       "first_query_at": "2026-12-01T09:00:00Z", "match": "semantic"}}}
```

`harness` is `model_dump(exclude={"status"})` ([v1_translate.py:709](../../../app/services/v1_translate.py)). The similarity and the matched row id are deliberately absent from both doors: they are tuning internals, and the threshold is not the caller's to probe.

| Endpoint | Change |
|---|---|
| `GET /audit` | None. The `semantic_*` columns are not exposed (OD6) |
| `GET /stats` | `blocked_duplicates` keeps counting `was_duplicate_blocked = 1`, so in `enforce` it includes semantic holds. The console label stays "Held as duplicates" (OD6) |

Internal API:

```python
dedup_parts(user_id, turns) -> DedupParts
dedup_context_hash(user_id, parts) -> str
embed(text) -> bytes ; token_count(text) -> int ; MODEL_VERSION: str
best_match(vec, candidates, threshold, anchor_text) -> SemanticMatch | SemanticMiss
find_semantic_candidates(user_id, context_hash, model_version, since, limit) -> list[Candidate]
insert_dedup_embedding(audit_id, user_id, context_hash, timestamp, model_version, embedding) -> None
```

## 11. Success Criteria

### MVP definition
With `shadow`, paraphrases are recorded and answered. With `enforce`, they are held with the semantic body and code. The hard-negative corpus is never held. With `off`, the existing suite passes with no test modified except the Section 6.6 additions, and no embedding exists.

### Functional requirements
- [ ] `dedup_key` byte-identical for every pinned case (`tests/test_dedup_key.py` unmodified)
- [ ] `off`: no import of `onnxruntime`/`embedder`; `dedup_embeddings` empty; every `semantic_*` column `NULL`; response bodies byte-identical (`tests/test_semantic_off_is_today.py` replays the six-outcome regression)
- [ ] An exact repeat in any mode → today's exact hold, reason and `/v1` code unchanged; step 4b not run (`semantic_outcome` NULL)
- [ ] `enforce`: a corpus paraphrase on `/query` → semantic hold, `first_query_at` = the earliest best-matching qualifying row
- [ ] `shadow`: the same paraphrase → answered; its success row has `semantic_outcome='shadow'`, `semantic_match_id`, `semantic_similarity`
- [ ] Another user's paraphrase → answered; a paraphrase in a different context (different system prompt or history) → answered
- [ ] A paraphrase after a failed (502), denied, limit-refused, flagged or `mark_audit_log_failed` row → answered
- [ ] A paraphrase after a pattern **block** → held (PRD-009 F4 parity)
- [ ] A semantic hold at 23 h does not hold at 25 h
- [ ] `foo()`/`bar()`, `Q3`/`Q4`, `enable`/`disable`, `"alpha"`/`"beta"` → `vetoed`, answered, even with the threshold forced to 0.5
- [ ] `/v1` (profile `code`) with default settings → `semantic_outcome='skipped_profile'`, never held
- [ ] Anchors under the minimum word count or over 256 wordpieces → skipped with the reason recorded
- [ ] A lookup `StorageError` → 500 on `/query`, retryable 500 on `/v1`; an inference error → `semantic_outcome='error'`, answered
- [ ] Embeddings older than 25 h are gone after the same user's next insert and after `init_db()`; all are gone after a boot with `off`
- [ ] `test_every_blocked_member_has_a_verdict` passes with the new member; `/v1` code is `semantic_duplicate_request`
- [ ] Chat UI renders the semantic bubble and copy; a reload restores it

### Quality indicators
- [ ] Corpus: hard-negative precision 1.00, overall precision ≥ 0.99 at the shipped threshold (`-m semantic_eval`)
- [ ] Latency of step 4b (embed + lookup) measured with `scripts/measure_semantic_latency.py`, 50 runs, local libSQL dev server, and published in `docs/features.md` the way the usage-limit figures are (`docs/features.md:222`). The **target** is p95 ≤ 30 ms on a typical (≤ 64-wordpiece) anchor, *unmeasured today*
- [ ] Image size delta recorded in `docs/deployment.md`
- [ ] No added round trip when `off`. When on: one lookup and one insert per eligible request

## 12. Implementation Phases

### Phase 1 — Spike and pin (Stories 1–3)
**Goal:** the facts this PRD marks unverified are settled, and the key is decomposed without moving a byte.
**Deliverables:** STORY-001 is a spike. It pins `onnxruntime`/`tokenizers` versions, exports or obtains the ONNX model and records its SHA-256, measures the image delta and the inference latency, confirms that `run` releases the GIL under 32 threads, checks whether the pinned libSQL server supports `vector_distance_cos` (recorded, not used), and runs a 60-pair seed corpus to set the default threshold. STORY-002 adds `dedup_parts` and `dedup_context_hash`. STORY-003 adds the settings and validators (mode `off` only reachable path).
**Validation:** full suite green; `test_dedup_key.py` unmodified.

### Phase 2 — Storage and matching (Stories 4–6)
**Goal:** the table, the lookup, the veto and the matcher exist and are tested, with nothing in the pipeline calling them.
**Deliverables:** `dedup_embeddings`, its indexes, the shared predicate constant, `find_semantic_candidates`, insert/prune/purge, and the three audit columns. `semantic_duplicates` (eligibility, veto, best match) with a fake embedder. `embedder` with boot self-test.
**Validation:** convergence on a fresh and a pre-PRD database; both lookups contain the shared predicates verbatim.

### Phase 3 — Pipeline, shadow first (Stories 7–9)
**Goal:** step 4b runs in `shadow`, then `enforce` is wired.
**Deliverables:** step 4b, embedding inserts at steps 5 and 8, shadow fields on every later row. Then the enforce arm, `QueryBlockedSemanticDuplicateResponse`, the `/v1` verdict row and the chat UI bubble. `test_semantic_scope.py` covers every row of the PRD-009 Section 6.3 table for the semantic tier.
**Validation:** all Section 11 functional requirements green; `off` regression green.

### Phase 4 — Evaluate, report, document (Stories 10–12)
**Goal:** enforcement can be justified with numbers.
**Deliverables:** the full corpus (≥ 200 pairs) and `test_semantic_eval.py`; `semantic_shadow_report.py`; `measure_semantic_latency.py`; `docs/features.md`, `docs/deployment.md`, `docs/roadmap.md`, `.env.example`.
**Validation:** precision targets met; latency and image figures published.

## 13. Future Considerations

- **Provider embeddings through PRD-020**, restricted to `trust: internal` providers. This needs an embeddings method added to PRD-020's `ProviderAdapter`, which today has only `complete()`/`stream()` (Section 9.3, option 2).
- **libSQL native vectors.** If the spike confirms support on both Turso and the pinned server, move the cosine to `vector_distance_cos` server-side (one row transferred), and later to `libsql_vector_idx` if candidate sets ever grow. Measure first: the candidate sets are per-user and per-context, so they are small.
- **Entity-aware veto** (OD4) once there is a way to use NER without making the duplicate checker depend on the PII stack.
- **Multilingual model** (OD3).
- **Per-user or per-role thresholds**, or an admin "release this hold" action in the console.
- **A normalised-exact tier** (casefold, collapse whitespace, strip punctuation) as a model-free middle step for `chat`. It is cheap and has almost no false positives, but it is mostly subsumed by the embedding tier at similarity ≈ 0.99.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **False positives** hold different requests (T3) | Medium / High | `code` excluded by default (D6); veto before threshold (D7); skip short and over-window anchors (D8); shadow first (D9); corpus gate with hard-negative precision 1.00 (F6); clear copy and a true way out (F8). |
| 2 | **Low value**: exact context is required, so paraphrases mostly occur only in populations 1–3 (Section 6.2) | Medium / Low | Stated in the PRD and the docs. The shadow report measures the actual rate before anyone enforces. If it is negligible, the feature stays `off`, which is today. |
| 3 | **CPU and latency** under 32 pipeline threads (T10) | Medium / Medium | One intra-op thread per inference, the token-window skip, measured in STORY-001 and Phase 4. If p95 misses the target, the int8 model (OD5) is the first lever. |
| 4 | **Image growth and supply chain**: a new native runtime and a model file | Certain / Low | Exact version pins, model SHA-256 checked at build, no runtime download. The delta is published. |
| 5 | **Embeddings outlive the window** for users who never send again before the next boot | Medium / Low | Global sweep in `init_db()`, which runs on every boot and Reflex hot reload (`database.py:724-743`), plus per-user pruning. OD7 offers a periodic sweep if boots are rare. |
| 6 | **Drift between the two tiers' definitions of "prior query"** | Low / High | One shared predicate constant, and a test asserting both SQL strings contain it. The JOIN makes `mark_audit_log_failed` apply to both. |
| 7 | **Model swap compares incompatible vectors** | Low / Medium | `model_version` in the lookup's `WHERE`. After a swap the semantic tier starts empty for ≤ 24 h, which is accepted and documented, like PRD-009 T8. |

## 15. Appendix

### Decisions

| # | Question | Decision | Why |
|---|---|---|---|
| D1 | Where do embeddings come from? | **In-process ONNX MiniLM via `onnxruntime` + `tokenizers`, baked into the image.** | No egress; small; no PyTorch. spaCy vectors produce the `foo()`/`bar()` false positive by construction (Section 8 table). |
| D2 | Provider embeddings (PRD-020)? | **Not in this PRD.** Later only through a PRD-020 `trust: internal` provider, over raw text, once PRD-020's adapter gains an embeddings call. | A cloud call at step 4b sends the raw prompt out before patterns and PII decide. Redacting first creates false positives between customers (Section 9.3, T7). |
| D3 | What is compared, and within what scope? | **Only the anchor, inside an exact `context_hash` (user + prefix_hash), the same 24 h window and the same prior-query predicates (shared SQL).** | Semantic matching must not widen PRD-009's scope. Tool-loop anchoring (PRD-017 D4) is inherited, because the prefix is exact. |
| D4 | Vector storage and search? | **A plain `BLOB` column, with brute-force cosine in Python over at most `MAX_CANDIDATES` (200) newest qualifying rows of the caller's context.** No native vector index. | Candidate sets are per-user and per-context, so they are small. Native libSQL vector support on the pinned client and server is unverified, and the test server is pinned by digest. One query, at most about 300 KB. |
| D5 | Retention of embeddings? | **A separate table, ≤ 24 h + 1 h slack: per-user prune on insert, global sweep at `init_db()`, full purge when `off`. Never exposed by any API.** | Embeddings are personal data and partially invertible. The window is their only purpose. |
| D6 | Profile behaviour? | **`DUPLICATE_SEMANTIC_PROFILES=chat` by default. `code` (all of `/v1`) is excluded, can be enabled, and then gets a stricter threshold.** | Code prompts differ by identifiers that embeddings barely weigh. Agent stalls are costly. |
| D7 | How are false positives prevented? | **A lexical veto (identifiers, numbers, quoted strings, URLs/e-mails, negation markers must match exactly) applied before a single threshold (provisional 0.92, set by the corpus), with a precision-gated corpus. Recall is not gated.** | Precision over recall. A vetoed pair is never held, whatever the similarity. |
| D8 | Which anchors are eligible? | **At least 4 words and at most 256 wordpieces. Otherwise exact-only, with the reason recorded.** | Short texts embed unstably, and long texts are truncated by the model, which would make two long prompts with the same opening collide. |
| D9 | How is it rolled out? | **`off` → `shadow` (records, never blocks) → `enforce`, as an explicit operator change after reading the shadow report.** | The real traffic precision is unknowable from a corpus alone. |
| D10 | What does `off` mean? | **Today's harness: no import, no inference, no round trip, no stored embedding, `NULL` columns, byte-identical responses. The exact tier is untouched in every mode, and an exact hit never runs step 4b.** | A safe default and a one-variable rollback. |
| D11 | Response shape? | **A new `QueryBlockedSemanticDuplicateResponse` with `reason: "Similar query within 24 hours"` and `match: "semantic"`. It is not a subclass of, or an added field on, the exact response.** | An optional field on the exact type would change its serialised bytes (`null`). A subclass would be caught silently by `isinstance` in `state.py:1222`. `_VERDICTS` is keyed by exact `type()` ([v1_translate.py:701](../../../app/services/v1_translate.py)), and `test_every_blocked_member_has_a_verdict` forces a row. |
| D12 | The `/v1` code? | **`semantic_duplicate_request`, 400 `invalid_request_error`, non-retryable.** | The same class as `duplicate_request` (`v1_translate.py:79`), so Aider prints it once (a 400, `docs/features.md:292`), but distinguishable by clients and logs. |
| D13 | Failure behaviour? | **Lookup storage fault → 500 (fail closed, like the exact tier). Inference fault → fail open with `semantic_outcome='error'`. Embedding insert fault → fail open with `ERROR`.** | The database is already a hard dependency. A broken encoder must not take down chat while the exact tier still protects. |

### Open decisions (proposed default)

- **OD1 — A caller override** ("send anyway", for example a chat-UI button or an `X-Harness-Allow-Similar` header). *Proposed default: none in the MVP.* Any override a caller controls makes the tier advisory. The veto already gives a true way out (F8).
- **OD2 — Fail closed on inference errors in `enforce`?** *Proposed default: fail open* (D13). A stricter operator might prefer closed.
- **OD3 — Multilingual model** (e.g. `paraphrase-multilingual-MiniLM-L12-v2`) for non-English deployments. *Proposed default: English MiniLM.* Non-English pairs are in the corpus as hard negatives, so the English model is measured not to produce false positives on them, even if it misses their paraphrases.
- **OD4 — Proper-name veto** (`Alice`/`Bob`). *Proposed default: capitalised non-sentence-initial tokens join the identifier class* if the corpus shows entity-swap false positives at the shipped threshold. Otherwise defer to NER-based work.
- **OD5 — int8-quantised model.** *Proposed default: fp32*, switching only if latency misses the target and the corpus still passes.
- **OD6 — Visibility.** *Proposed default:* `/audit` unchanged, `blocked_duplicates` includes semantic holds, and the console's Register shows "Held (similar)" for `semantic_outcome='blocked'` rows (a console copy change, needing one `GET /audit` field, `semantic_outcome`, admin-only).
- **OD7 — Periodic sweep** in addition to boot and insert. *Proposed default: no.* Revisit if deployments go weeks without a boot.
- **OD8 — Threshold default.** *Proposed default: 0.92 provisional*, replaced by the STORY-001 corpus result, never lowered below the value that meets F6.

### Evidence (verified against `main` @ `2253871`)

- `app/services/duplicate_checker.py:29-39` `check_duplicate(user_id, key)`, 24 h cutoff; `:78-121` `dedup_key`, with the tool-free path at `:106-109` and the anchor = last `user` turn at `:110-121`.
- `app/services/conversation_key.py:40-45`: reuses `_sha256_json`, raw text only (docstring `:9-10`).
- `app/db/database.py:857-899` `find_duplicate_timestamp` with its five predicates; `:902-917` `mark_audit_log_failed`; `:724-743` `init_db()` block.
- `app/services/query_pipeline.py:353` profile resolution; `:363` key computed at step 1 from raw messages; `:534-562` step 4; `:564-579` step 5; `:654-746` step 6 redaction (after the duplicate check).
- `app/routers/v1.py:318` `profile="code"`; `run_query` (`query_pipeline.py:963-985`) passes no profile → `PATTERN_PROFILE_DEFAULT="chat"` (`app/config.py:284`).
- `app/models/schemas.py:100-103` exact hold shape; `app/services/v1_translate.py:79, 640-675, 701` verdict table keyed by `type()`.
- `chat_ui/chat_ui/copy.py:99` "Change the wording before you send it again."; `state.py:1222` `isinstance` branch.
- `tests/test_pii_dedup_isolation.py:105` redacted-collision hazard; `:231` duplicate checker has no redaction dependency.
- `app/services/audit_logger.py:9, 78`: `prompt_preview` is the raw prompt's first 500 characters.
- `requirements.txt`: `libsql==0.1.11`, `spacy==3.8.16`, `presidio-*==2.2.364`; no ONNX or torch dependency today.

### Not verified (settled in STORY-001)

- Whether libSQL vector functions (`F32_BLOB`, `vector32`, `vector_distance_cos`, `libsql_vector_idx`) are available on the digest-pinned `libsql-server` and through `libsql==0.1.11`. D4 does not depend on it.
- onnxruntime / tokenizers wheel sizes, the ONNX model size, and the resulting image delta.
- `InferenceSession.run` releasing the GIL, and per-inference latency on the deployment CPU.
- The 0.92 threshold, which is a starting point and not a measured value.
- The extent to which MiniLM embeddings can be inverted.

### Related documents

- PRD-009 (duplicate rescoping): scope, prior-query predicates, raw-text invariant. This PRD extends it and changes none of it.
- PRD-011 / PRD-012: profiles `chat` / `code`.
- PRD-013: usage limits as the abuse bound (T1, T10).
- PRD-015 / PRD-017: `/v1` verdict table; tool-loop anchoring.
- PRD-020 (provider registry, draft): `trust: internal`/`external` (D7), `ProviderAdapter.complete()`/`stream()` (D11), fallback trust rules (Section 6.8). It is the Section 9.3 extension point and has no embeddings endpoint.

### Dependencies

- Depends on: none (PRD-009, -010, -013, -015, -017 are done).
- Blocks: none. PRD-020 could later supply a `trust: internal` embedding provider, after an embeddings method is added to its adapter.

**Skills referenced:** none applicable. `.agents/skills/` was scanned; its only skill, `frontend-design`, covers UI visual design, and this PRD's UI change is copy inside an existing component.
