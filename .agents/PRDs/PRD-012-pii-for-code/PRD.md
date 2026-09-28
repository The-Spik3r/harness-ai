---
id: PRD-012
slug: pii-for-code
title: PII Redaction for Code — Policy by Profile, Role and Direction, Within a Latency Budget
status: draft
base_branch: main
epic_branch: epic/PRD-012-pii-for-code
created: 2026-09-23
updated: 2026-09-25
---

## 1. Executive Summary

PII redaction in this harness is one function applied the same way to everything. [app/services/pii_redactor.py](../../../app/services/pii_redactor.py) runs Presidio's `AnalyzerEngine` over `en_core_web_lg` with `PII_SCORE_THRESHOLD=0.35` and seven entity types, two of which (`PERSON`, `LOCATION`) come from spaCy's named-entity recognizer. Since PRD-010, [app/services/query_pipeline.py](../../../app/services/query_pipeline.py) calls it on **every message of the conversation** at step 6 and on **the model's response** at step 8. For a person typing prose into the chat UI, that is the intended control. For a coding agent it is harmful in four separate ways:

- **It corrupts code.** The NER model tags identifiers, class names and string literals as `PERSON` or `LOCATION`. Example emails, phone-shaped numbers and names in fixtures, tests and configs are real matches. Masking the **response** means an agent that writes a file writes `<EMAIL_ADDRESS>` into the user's repository. Masking the **input** is not harmless either: an agent that reads `author = "Jane Doe"` and is asked to edit that line sees `author = "<PERSON>"`, and either its search-and-replace fails to match or its whole-file write puts the placeholder on disk.
- **It breaks structure.** A span that swallows a closing quote breaks a string literal. A phone number that is a JSON number turns into `<PHONE_NUMBER>` outside any string, and the document stops parsing.
- **It is too slow at agent sizes.** The README measures ~0.93 s added per chat send at ~19k characters, almost all of it re-redaction, growing ~23 ms per message. `CONTEXT_MAX_CHARACTERS` admits 200,000 characters (≈50k tokens). Extrapolated linearly, that is on the order of 10 s of CPU-bound spaCy work per request, on a thread pool that shares one GIL.
- **Its policy is undefined for anything but a human user turn.** PRD-010 made redaction per message but left the per-role policy to this PRD (PRD-010 D7). PRD-011 introduced `chat` and `code` profiles for patterns only.

This PRD makes PII redaction a **policy selected by the same profile PRD-011 introduced**. `chat` is today's behaviour, byte for byte. `code` is input-only, skips fenced code blocks, does not redact `system` turns, uses pattern recognizers only (email, phone, card, SSN, IBAN — no NER), and replaces spans in a way that cannot break quoting or JSON. A benchmark story comes first and produces the numbers that fix the `code` threshold, the size limit and the latency budget. A spike decides between fixed and reversible placeholders and records the decision. As with PRD-011, `code` has no HTTP ingress until PRD-014. It is reachable through `run_conversation(profile="code")` and tested there.

**MVP goal:** a corpus of Java, TypeScript, Python, JSON and YAML files containing example emails, names and phone-shaped numbers passes through the `code` profile with no syntax-breaking change, and every JSON file still parses. A prose corpus with real PII is still masked under both profiles. `/query` and the chat UI pass the characterization suite with no assertion changed. The `code` profile's p95 redaction latency at 200,000 characters is under the budget the benchmark story records.

## 2. Mission

Protect personal data in what humans write without corrupting the code agents read, and prove both halves with a corpus and a benchmark rather than asserting them.

Core principles:

- **`chat` does not move.** Every existing prompt, reply, audit row and `/stats` figure under the default configuration is identical after this PRD. It is pinned by characterization tests before anything changes.
- **Direction matters.** Input redaction protects data leaving for the provider. Output redaction protects the reader, and for a coding agent the reader is a compiler. They are separate switches.
- **The role decides the policy.** The same principle as PRD-011, with the same `Role` vocabulary from `app/models/messages.py`. No second vocabulary.
- **Never break structure.** A redaction may lose information. It may never produce a string literal missing its quote, or JSON that no longer parses. If it would, the request fails closed.
- **Measured, not guessed.** The `code` threshold, the size limit and the latency budget are set by a checked-in benchmark, and the numbers are in the story report.
- **Fail closed at the edges.** Over the size limit, the request is refused, not forwarded unmasked. An unknown profile falls back to the strictest policy (`chat`), never to the most permissive one.
- **The server chooses the profile.** It is the same call-site argument PRD-011 added (`run_conversation(profile=...)`). No request field can select it.

## 3. Target Users

**Integrating Developer (coding agent).** Will point OpenCode, Cline, Continue or Aider at the harness once PRD-014 lands. Their traffic is source code, JSON tool results and file reads. They need the model to see their code as written, the files the agent writes to be free of placeholders, and each request to take seconds of model time, not seconds of NER on top.

**Security/Compliance Admin.** Owns the claim that personal data does not reach the model provider. They need the trade-offs of the `code` profile written down, not inferred from code: which roles are masked, what is skipped inside code blocks, which entity types are not detected, and why the output is not masked. They also need the audit to say which profile ran, so a `pii_detected_output = 0` under `code` is not read as "clean".

**Platform Operator.** Owns `.env`. They need to move the `code` profile's defaults (turn output redaction back on, add `PERSON` back, redact `system`) without a code change, and they need a mis-set value to stop the boot with a message naming it.

**End User (Employee).** Chats in the Reflex UI under `chat`. Nothing they see changes.

**PRD-014 / PRD-016 implementers** (internal). PRD-014 passes `profile="code"` on `/v1/chat/completions` and needs PII policy to follow from that one argument. PRD-016 admits `tool` turns and `tool_calls`, and needs a written rule that tool-call arguments are never redacted, plus a redaction primitive that already keeps JSON valid.

## 4. MVP Scope

### In Scope

**Benchmark and baseline**
- [ ] `scripts/measure_pii_latency.py`: p50/p95 redaction time per profile at 40k / 200k / 400k characters (≈10k / 50k / 100k tokens) of real code-agent context, plus the false-positive count per entity type over the code corpus
- [ ] Baseline report under today's code, before any change, recorded in the story report
- [ ] Characterization tests of today's `redact()` and today's pipeline steps 6 and 8, green on untouched code

**Policy (`app/services/pii_policy.py`, new)**
- [ ] `PiiPolicy` per profile: input roles, output on/off, code-block skipping, entity list, threshold, size limit
- [ ] Built-in `chat`: every role redacted, output on, no code-block skipping, `PII_ENTITIES`, `PII_SCORE_THRESHOLD`, no PII-specific size limit. This is today's behaviour
- [ ] Built-in `code`: `user`, `assistant` and `tool` redacted, `system` not, output off, fenced blocks skipped, `PII_ENTITIES_CODE`, `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`
- [ ] Resolution by the same `profile` name `run_conversation` already takes. A name with no PII policy resolves to `chat`, logged once at startup per name

**Redaction (`app/services/pii_redactor.py`, extended)**
- [ ] `redact()` unchanged in signature and behaviour; it remains the `chat` path
- [ ] `redact_for_policy(text, policy) -> RedactionResult`: fenced-block skipping, structure-safe replacement, JSON-aware mode
- [ ] A second analyzer for entity lists with no NER type: pattern recognizers over a tokenizer-only spaCy pipeline, lazily built, singleton like the first
- [ ] Structure-safe replacement: quotes, backticks, backslashes and line breaks are never replaced; spans are split around them
- [ ] JSON-aware mode: when a message's content parses as a JSON object or array, spans are confined to string interiors and number tokens, and the result must parse or the request fails closed

**Shared primitive (`app/services/pattern_detector.py`)**
- [ ] `strip_fenced_blocks(text)` split out of `strip_code_spans`, with `strip_code_spans` rebuilt on it and its behaviour unchanged (PRD-011's tests are the proof)

**Pipeline (`app/services/query_pipeline.py`)**
- [ ] Step 6 redacts per the resolved policy's role map; step 8 redacts only when the policy's output switch is on
- [ ] Size limit per policy: over it, `BLOCKED` with the existing context-limit shape and `limit: "redaction_characters"`, audited with `success=False`
- [ ] A `PiiRedactorError` from the JSON post-condition goes through the existing redaction-error arm (audited, 500)

**Audit**
- [ ] `audit_logs.profile TEXT`, nullable, added through the existing additive-column convergence; set on every arm `run_conversation` writes
- [ ] `pii_detected_input` / `pii_detected_output` / `pii_entities` keep PRD-010 D7's meaning; under `code`, `pii_detected_output` is `0` because the output was not analyzed, and `profile` says so

**Settings (`app/config.py`)**
- [ ] `PII_ENTITIES_CODE`, `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, `PII_CODE_REDACT_OUTPUT`, `PII_CODE_REDACT_SYSTEM`, `PII_CODE_SKIP_CODE_BLOCKS`, with startup validators

**Corpora (`tests/corpora/pii/`, new)**
- [ ] `code/`: source and config files with example PII that must round-trip without a syntax-breaking change
- [ ] `prose/`: messages with real-looking PII that must still be masked under both profiles
- [ ] `json/`: tool-result-shaped JSON with PII in string values and number tokens, which must still parse after redaction

**Decision record**
- [ ] `decisions/D5-placeholders.md` in this PRD's directory: fixed vs indexed vs reversible placeholders, with the spike's evidence

**Documentation**
- [ ] README: PII section rewritten around profiles, the `code` role table, the trade-offs, the new latency figures; `.env.example`: six settings

### Out of Scope

- [ ] Non-English models or recognizers
- [ ] Secret detection (API keys, tokens, private keys). This belongs with action policy / patterns (PRD-015)
- [ ] An HTTP ingress that selects `code`. PRD-014 owns it; this PRD tests by direct call, as PRD-011 did
- [ ] `tool` turns and `tool_calls` reaching the pipeline. Step 0 still refuses them (PRD-016). The `tool` cell of the policy is defined and tested at the function level
- [ ] Skip-and-flag when over the size limit. Deferred; see D4 and Section 13
- [ ] Reversible placeholders with a stored mapping, unless the spike (D5) shows fixed placeholders make agents unusable
- [ ] A PII configuration file. The policy is built in and tuned by settings; a file (in the PRD-011 shape) is a future consideration
- [ ] Moving Presidio off the GIL (process pool). Measured here, not solved
- [ ] Changing the `chat` profile's entities, threshold or behaviour in any way

## 5. User Stories

1. **As an integrating developer, I want my source files to reach the model as I wrote them, so that the agent's edits apply to the code that is actually on disk.**
   *Example:* a `tool` turn containing `UserFixtures.java` with `new User("Jane Doe", "jane@example.com")` inside a fenced block reaches the model byte-identical under `code`.

2. **As an integrating developer, I want the model's output not to be masked, so that the files my agent writes contain no `<EMAIL_ADDRESS>` placeholders.**
   *Example:* the model answers with a test fixture containing `alice@example.com`; under `code` the response is returned unchanged and `pii_detected_output` is `0` with `profile = 'code'`.

3. **As a security admin, I want personal data a person types in prose to be masked even under `code`, so that the coding profile is not a way around the control.**
   *Example:* "email the diff to maria.lopez@corp.com and call her on +1 415 555 0134" outside any fence goes upstream as "email the diff to `<EMAIL_ADDRESS>` and call her on `<PHONE_NUMBER>`".

4. **As an integrating developer, I want JSON tool results to stay valid JSON, so that the model is not reasoning about a document that cannot be parsed.**
   *Example:* `{"id": 7, "contact": "bob@x.io", "phone": 4155550134}` becomes `{"id": 7, "contact": "<EMAIL_ADDRESS>", "phone": "<PHONE_NUMBER>"}`. It still parses. The phone changes from a number to a string, and that is the documented cost.

5. **As a platform operator, I want redaction on a large coding context to stay within a known latency, so that PII protection does not add seconds to every agent step.**
   *Example:* at 200,000 characters, `code` redaction p95 is under the budget in the benchmark report, and the README states both numbers, `chat` and `code`.

6. **As a security admin, I want an oversized request refused rather than forwarded unmasked, so that size is never a bypass.**
   *Example:* a `code` conversation with more analyzable characters than `PII_MAX_CHARACTERS_CODE` gets `BLOCKED`, `limit: "redaction_characters"`, and an audit row with `success=0`.

7. **As a security admin, I want the audit to record which profile ran, so that a zero in `pii_detected_output` is not read as "the model returned no PII".**
   *Example:* the Register shows `profile = code` on the row, and the README states that under `code` the output is not analyzed.

8. **As an end user, I want the chat to behave exactly as it does today, so that this change is invisible to me.**
   *Example:* the chat characterization suite, `test_pii_redaction_integration.py` and the seven-outcome regression pass with no assertion changed.

## 6. Core Architecture & Patterns

### 6.1 Where redaction sits

The check order from PRD-010 Section 6.1 and PRD-011 Section 6.1 is unchanged. Steps 6 and 8 change their inputs, not their positions:

```
0. structural validation (no audit row)
1. dedup_key over the raw conversation
2. authorize / model / BYOK
3. context limits
4. duplicate
5. patterns: inspect(messages, profile)
6. REDACT INPUT  <-- was: redact(m.content) for every m
                     now: policy = get_pii_policy(profile)
                          size check → redaction_characters refusal (row, success=0)
                          redact_for_policy(m, policy) for m whose role the policy covers
7. upstream (redacted messages)
8. REDACT OUTPUT <-- was: always
                     now: only if policy.output
   audit (+ profile); return
```

Redaction still runs **after** patterns, so the pattern detector sees raw text (PRD-011 Section 6.1). The size check is at the head of step 6, not in step 3, because what it measures depends on the policy: which roles are covered and how much is inside fences. Placing it at step 6 means a conversation that is refused for size has already passed authorization, the duplicate check and patterns. Its row carries `success=0`, so it never counts as a prior query (PRD-009 Section 6.3).

### 6.2 The policy model

```python
@dataclass(frozen=True)
class PiiPolicy:
    name: str                              # "chat" | "code"
    input_roles: frozenset[Role]           # roles whose content is redacted at step 6
    output: bool                           # redact the response at step 8
    skip_fenced_blocks: bool               # analyze prose only; fenced blocks pass untouched
    entities: tuple[str, ...]              # Presidio entity types
    threshold: float
    max_characters: Optional[int]          # analyzable characters per request; None = no PII-specific limit
    structure_safe: bool                   # quote/backslash/newline-preserving replacement + JSON-aware mode
```

| Field | `chat` (built in, = today) | `code` (built in) |
|---|---|---|
| `input_roles` | `system`, `user`, `assistant`, `tool` | `user`, `assistant`, `tool` (+ `system` if `PII_CODE_REDACT_SYSTEM`) |
| `output` | `True` | `PII_CODE_REDACT_OUTPUT` (default `False`) |
| `skip_fenced_blocks` | `False` | `PII_CODE_SKIP_CODE_BLOCKS` (default `True`) |
| `entities` | `PII_ENTITIES` | `PII_ENTITIES_CODE` (default `EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE`) |
| `threshold` | `PII_SCORE_THRESHOLD` (0.35) | `PII_SCORE_THRESHOLD_CODE` (set by the benchmark; provisional 0.5) |
| `max_characters` | `None` (`CONTEXT_MAX_CHARACTERS` already bounds it) | `PII_MAX_CHARACTERS_CODE` (set by the benchmark; provisional 200,000) |
| `structure_safe` | `False`, which keeps today's exact output | `True` |

`chat` lists `tool` for completeness only. Step 0 refuses `tool` turns, so no `chat` request carries one. It lists `system` because today every message is redacted, whatever its role, and `chat` must stay today's behaviour.

**Resolution.** `get_pii_policy(profile_name)` returns the policy of that name. A PRD-011 patterns file can define profiles with any name, and a name with no PII policy resolves to **`chat`**, the strictest one. `pii_policy.load()` logs this once per name at startup, beside `pattern_config.load()` in both lifespans. It is a fallback, not an error, on purpose. Making every custom pattern profile also declare PII policy would couple two configurations that PRD-011 kept apart. And the fallback moves toward more masking, never less.

### 6.3 The `code` role matrix (Decisions D1, D3)

| | `system` | `user` | `assistant` | `tool` | Output |
|---|---|---|---|---|---|
| `chat` | redact | redact | redact | redact (unreachable) | **redact** |
| `code` | not redacted | redact prose | redact prose | redact prose | **not redacted** |

Why each `code` cell:

- **Output is not redacted (D1).** The reader of a coding agent's output is the file system. A placeholder in a response becomes a placeholder in a file. The model can only return PII it was given, which is what input redaction masks, or PII it produced itself, which is not the user's data leaving to the provider. An operator who prefers placeholders in files to any unmasked output sets `PII_CODE_REDACT_OUTPUT=true`.
- **`system` is not redacted (D3).** It is the client's own prompt (OpenCode's, Cline's), the same argument as PRD-011 Section 6.4. It is also the largest fixed cost per request: re-analyzing an agent's multi-kilobyte system prompt on every step spends latency on text with no user data in it. It is configurable.
- **`user` is redacted, prose only.** This is the person speaking. Fenced blocks are skipped (D2). Prose around them is analyzed.
- **`assistant` is redacted, prose only.** It differs from the brief's proposal ("already redacted, PRD-010 D5"), which is true for the chat UI and false for PRD-014. A `/v1` client sends its own history. With output off, that history contains raw model output, and nothing stops a caller from writing arbitrary text into an `assistant` turn. PRD-010 D5, "history never leaves the process unmasked, whatever its source", is kept as the rule. The cost is bounded because fenced blocks, where an agent's assistant turns carry most of their bulk, are skipped.
- **`tool` is redacted, prose only.** It is the file reads, command output and fetched pages, and the largest volume. The entity list, not fence skipping, keeps it from corrupting code: tool results are usually unfenced, so the NER types that tag identifiers are simply not run (Section 6.4). This cell is tested at the function level only until PRD-016 admits `tool` turns.

### 6.4 Pattern recognizers only under `code` (Decision D7, new)

The two entity types the brief names as code-noisy, `PERSON` and `LOCATION`, are the two that come from spaCy's NER. The other five come from Presidio's pattern recognizers: regex plus checksums, with Luhn for cards and IBAN's mod-97. Dropping NER from `code` removes the main false-positive source. It also removes most of the cost, provided the analyzer does not run `en_core_web_lg` at all.

So when a policy's entity list contains no NER type, `pii_redactor` builds a **second analyzer** whose NLP engine is a tokenizer-only English pipeline (`spacy.blank("en")`) with no tagger, parser or NER. Presidio's pattern recognizers only need tokens for context-word enhancement. The analyzer is lazily built and cached as a singleton, like the first one. If `PII_ENTITIES_CODE` includes `PERSON` or `LOCATION`, the `code` policy uses the full analyzer, and the operator gets NER at NER's cost.

**What this gives up, stated plainly:** a name or a city written in prose under `code` is **not** masked by default. An email, phone, card, SSN or IBAN is. That is the trade the benchmark is asked to justify. The benchmark story reports `PERSON`'s false-positive count on the code corpus and its cost at 200k characters. If both the round-trip corpus and the latency budget still pass with `PERSON` included at `PII_SCORE_THRESHOLD_CODE`, the decision record puts it back in the default. The default is set from that data, not by preference.

**To verify in STORY-003, not assumed:** that Presidio's `AnalyzerEngine.analyze` accepts a tokenizer-only spaCy engine through `NlpEngineProvider` (or a thin `SpacyNlpEngine` subclass) with the pattern recognizers intact, and how much of today's cost is NLP processing rather than recognition. If the tokenizer-only engine does not work, the fallback is the same entity list on the full engine, and the benchmark measures that instead.

### 6.5 Fenced-block skipping (Decision D2)

PRD-011's `strip_code_spans` blanks fenced blocks **and** inline backtick spans, replacing each character with a newline so lengths and offsets are preserved. PII skipping uses **fenced blocks only**:

```python
# app/services/pattern_detector.py
def strip_fenced_blocks(text: str) -> str: ...      # NEW: the first pass of strip_code_spans, extracted
def strip_code_spans(text: str) -> str:              # unchanged behaviour: inline pass over strip_fenced_blocks(text)
```

- **Fences only, not inline spans.** An inline span is short, is where people put an address they are pointing at ("send it to `ops@corp.com`"), and is almost never code whose syntax a placeholder would break. Skipping inline spans would buy nothing for code and would hide real PII.
- **Analyze the blanked text, replace in the original.** The analyzer runs over `strip_fenced_blocks(content)`. Blanking preserves length, so every span offset it returns is an offset into the original, and replacement happens on the original. Nothing inside a fence can be matched, because it is all newlines. Analyzing runs of newlines is close to free, which is where much of the `code` saving on fenced content comes from.
- **Heuristic, stated as one.** It is PRD-011's parser, with PRD-011's limits (no indented code blocks, unterminated fence runs to the end). Unfenced code falls back on the entity list (6.4) and on structure-safe replacement (6.6). PII inside a fenced block reaches the provider. That is the trade-off the brief names and Risk 1 records.

### 6.6 Structure-safe replacement (the structured-content guard)

Under `structure_safe`, the analyzer's spans are post-processed before replacement:

1. **Never replace structural characters.** `"`, `'`, `` ` ``, `\` and line breaks inside a span are kept, and the span is split into maximal runs without them. Each run with at least one alphanumeric character is replaced by the placeholder. Outside JSON mode, when a pattern entity's span splits into several runs, only the runs holding its anchor (`@` for an email, a digit for the others) are replaced, and all of them if none does; Presidio's email local part admits `'` and `=`, so `email='jane@example.com'` would otherwise lose its keyword (STORY-013). So a span that swallowed a closing quote can no longer delete it, and a placeholder can never introduce one. The placeholder alphabet (`<`, `>`, `A–Z`, `_`) contains no character that is special inside a string literal in JSON, Python, Java, JavaScript, TypeScript, C#, Kotlin or YAML's double-quoted style.
2. **JSON-aware mode.** If a message's stripped content starts with `{` or `[` and `json.loads` accepts it, the analyzer sees every escape sequence as spaces of the same length, so `"payout:\nGB82 …"` is not read as `nGB82` and missed (STORY-013); and spans are clipped to the tokens they fall in, using a scan of the original text's JSON tokens:
   - a span inside a **string** token is replaced as in rule 1, limited to that string's interior;
   - a span covering a **number** token replaces the whole token with `"<TYPE>"`, quoted, so a phone or card number that is a JSON number becomes a string rather than a syntax error;
   - a span touching only punctuation, `true`/`false`/`null` or whitespace is dropped.
3. **Post-condition.** In JSON-aware mode, `json.loads(result)` must succeed. If it fails, `redact_for_policy` raises `PiiRedactorError("redaction would produce invalid JSON")`, and the pipeline takes its existing redaction-error arm: audited, `500`, nothing sent upstream. That is fail closed. The corpus story is what keeps this path unreached.

**Tool-call arguments are never redacted.** In this PRD that holds by construction: `Message` has no `tool_calls` field, `normalize_message` refuses `tool_calls` (PRD-010), and `redact_for_policy` takes a string. The rule is written here, and repeated in the `redact_for_policy` docstring, as the contract PRD-016 must keep when it widens `Message`: arguments go upstream untouched, and only `content` goes through policy. This PRD's JSON-aware mode is what makes a `tool` turn's *result* safe to redact once PRD-016 admits it.

`chat` keeps `structure_safe=False` and today's `AnonymizerEngine` path, so its output does not change by a byte. Moving `chat` to structure-safe replacement is a Future Consideration, because it would change what chat users see.

### 6.7 The size limit (Decision D4)

```python
analyzable = sum(
    len(strip_fenced_blocks(m.content) if policy.skip_fenced_blocks else m.content)   # counted without newline runs
    for m in messages if m.role in policy.input_roles
)
```

The limit counts **non-whitespace-run characters the analyzer will actually process**. Blanked fences cost almost nothing to analyze and should not count toward it. Over `policy.max_characters`:

```json
{
  "status": "BLOCKED",
  "reason": "Conversation exceeds redaction limit",
  "limit": "redaction_characters",
  "maximum": 200000,
  "actual": 231554
}
```

This is PRD-010's `QueryBlockedContextLimitResponse` with its `limit` literal widened by one value. There is no new response class, and the chat UI's context-limit bubble already renders the shape. Audited with `success=False`, `error_message="redaction limit: characters 231554 > 200000"`, the non-NULL `dedup_key`, and `profile`. `chat` has `max_characters=None`, so this arm cannot fire under `chat`, and `CONTEXT_MAX_CHARACTERS` (checked at step 3) stays the only size refusal a chat user can meet.

**Skip-and-flag is deferred.** The brief proposed making the over-limit behaviour configurable to "skip-and-flag". Skipping means forwarding unmasked text, which is a fail-open switch. Recording that it happened needs an audit field that says **which** messages went out unmasked, and PRD-013 is redesigning per-request telemetry. This PRD ships the fail-closed half only (Section 13).

### 6.8 Audit semantics (PRD-010 D7 kept; `profile` added)

- `pii_detected_input` and `pii_entities` keep PRD-010 D7's meaning: entities in **the last user turn**, plus the output. Entities found in history, `assistant` or `tool` turns are masked but not recorded, for D7's reason: counting them would mark every later row of a session as a PII event. This PRD does not revisit that. Per-role PII telemetry goes with PRD-013.
- Under `code`, the output is not analyzed, so `pii_detected_output` is `0`. That is why the row needs to say which policy ran.
- **`audit_logs.profile TEXT`**, nullable, via `AUDIT_LOGS_ADDED_COLUMNS` and `CREATE_AUDIT_LOGS_TABLE` both, with no backfill (PRD-009's choice for `dedup_key`). It is set on **every** arm `run_conversation` writes, forbidden and duplicate included, as a required keyword on each `log_query` call (the PRD-008 STORY-009 pattern). The value is the name the call site passed after default resolution (`chat` for `/query` and the chat UI). It is carried through `AuditLog`, `AuditQueryEntry` and the admin Register row. It also gives PRD-011's pattern rows the profile they were missing.

### 6.9 Directory structure (files touched)

```
app/
├── config.py                         # + 6 settings, validators
├── main.py                           # pii_policy.load() beside pattern_config.load()
├── models/schemas.py                 # limit literal + "redaction_characters"; AuditQueryEntry.profile
├── routers/admin.py                  # entry carries profile
├── db/
│   ├── models.py                     # + audit_logs.profile (CREATE + added-columns)
│   └── database.py                   # writes/reads profile; snapshot field
└── services/
    ├── pii_policy.py                 # NEW: PiiPolicy, built-in chat/code, get_pii_policy(), load()
    ├── pii_redactor.py               # + redact_for_policy, pattern-only analyzer, structure-safe + JSON mode
    ├── pattern_detector.py           # strip_fenced_blocks extracted; strip_code_spans rebuilt on it
    ├── audit_logger.py               # + profile
    └── query_pipeline.py             # step 6 per policy + size arm; step 8 gated; profile on every arm
chat_ui/chat_ui/chat_ui.py            # pii_policy.load() in the mounted lifespan too
scripts/measure_pii_latency.py        # NEW: benchmark, beside measure_history_latency.py
.agents/PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md   # NEW: spike decision record
tests/
├── corpora/pii/
│   ├── code/                         # NEW: .java .ts .py .yaml .json with example PII
│   ├── prose/                        # NEW: real-looking PII that must be masked
│   └── json/                         # NEW: tool-result-shaped JSON, strings and numbers
├── test_pii_characterization.py      # NEW: today's redact() and steps 6/8, before anything moves
├── test_pii_policy.py                # NEW
├── test_pii_structure_safe.py        # NEW: quote/backslash/newline and JSON-aware mode
├── test_pii_code_corpus.py           # NEW: round-trip, prose masking, JSON validity, latency budget
├── test_query_pipeline_pii_profiles.py   # NEW: step 6/8 per profile, size arm, profile column
├── test_pii_redactor.py              # unchanged assertions
└── test_pii_redaction_integration.py # unchanged assertions
```

### 6.10 Patterns followed

- **Characterization first.** Today's `redact()` and steps 6/8 are pinned green on untouched code before anything moves (PRD-009 STORY-001, PRD-011 STORY-001).
- **Built-in default, server-selected profile.** The same `profile` argument as PRD-011 Section 6.6, and no request field.
- **Loaded once at startup in both lifespans.** `app/main.py` *and* `chat_ui/chat_ui/chat_ui.py`, because of the `api_transformer` lifespan bypass (PRD-007, PRD-011 Section 6.9).
- **Settings validated at startup with instructive errors.** The `CHAT_SESSION_LIMIT` / `_RESOURCE_BOUNDS` style in [app/config.py](../../../app/config.py).
- **Additive column convergence.** One entry in `AUDIT_LOGS_ADDED_COLUMNS` *and* the `CREATE_AUDIT_LOGS_TABLE` declaration, per the comment in [app/db/models.py](../../../app/db/models.py).
- **Required keyword on every audit arm.** `profile` is passed explicitly, like `session_id` and `dedup_key`.
- **Corpora as checked-in files.** The PRD-011 `tests/corpora/` layout, so a reviewer reads them as code.
- **Measured with a script in `scripts/`.** The `measure_history_latency.py` precedent, with its numbers quoted in the README.

## 7. Tools/Features

### F1 — Benchmark harness
`scripts/measure_pii_latency.py --profile chat|code --sizes 40000,200000,400000 --runs N`. It builds conversations from the code corpus plus a prose filler, in agent-shaped proportions (one system prompt, alternating user/assistant/tool-shaped turns, with the tool-shaped ones as `user` turns while step 0 refuses `tool`). It times `redact_for_policy` / `redact` only, not the pipeline, and prints p50/p95 per size and per-entity false-positive counts over `tests/corpora/pii/code/`. The 400k size exceeds `CONTEXT_MAX_CHARACTERS` on purpose, to measure the analyzer and not the limit. The resolved Presidio and spaCy versions go in the report and are pinned in `requirements.txt`, which currently leaves them unpinned.

### F2 — Characterization
It pins `redact()` output for a fixed set of prompts, and the exact `Message` list `call_openrouter` receives, plus the audit PII fields, for a chat conversation. It is green on untouched code, and no assertion changes afterwards.

### F3 — `strip_fenced_blocks`
The fence pass of `strip_code_spans` is extracted as a public pure function. `strip_code_spans(text) == _inline_pass(strip_fenced_blocks(text))`. PRD-011's `test_pattern_matching.py` / `test_pattern_corpus.py` must stay green unchanged.

### F4 — Settings
The six settings in Section 9.3. `PII_ENTITIES_CODE` is validated against the known entity names. The two thresholds are validated in `[0, 1]`. `PII_MAX_CHARACTERS_CODE` is `≥ 1` and in `_RESOURCE_BOUNDS`.

### F5 — `pii_policy`
`PiiPolicy`, the two built-in policies built from settings, `get_pii_policy(name)` with the `chat` fallback, and `load()`, which builds both, logs fallbacks for every profile name the loaded patterns policy defines, and raises `PiiConfigError` on an inconsistent combination (for example `skip_fenced_blocks` with `structure_safe=False`, reserved for a future file format).

### F6 — Pattern-only analyzer
`_get_analyzer(entities)` returns the full or the tokenizer-only analyzer depending on whether `entities` contains an NER type. Both are lazy singletons. `load()` prebuilds the ones the configured policies need, so neither is built on a request.

### F7 — `redact_for_policy`
`redact_for_policy(text, policy) -> RedactionResult(text, entities)` runs fence blanking → analyze → structure-safe span post-processing → JSON-aware clipping → replacement → post-condition. Pure apart from the analyzer call. It raises `PiiRedactorError` on analysis failure (the existing contract) and on the JSON post-condition.

### F8 — Pipeline integration
Step 6 iterates messages, redacting those whose role is in `policy.input_roles` and passing the rest through unchanged. `chat` calls `redact()` exactly as today. Step 8 is gated on `policy.output`. The size arm is at the head of step 6. `profile` is passed on every `log_query` call.

### F9 — Audit `profile` column
Convergence, writer, reader, `AuditQueryEntry.profile`, admin Register column, snapshot field.

### F10 — Placeholder spike (D5)
It compares three options on scripted agent tasks run through `run_conversation(profile="code")` against a real model, outside CI:
- (a) fixed `<TYPE>`, today's behaviour;
- (b) **indexed per request** `<EMAIL_ADDRESS_1>`, numbered by first appearance across the whole conversation. There is no stored mapping. Numbering is deterministic because the whole conversation is re-redacted on every send;
- (c) reversible, with a per-conversation mapping stored server-side and placeholders restored in output.

It measures how often placeholders leak into the model's output and whether the tasks complete. The result goes in `decisions/D5-placeholders.md`. The default stays (a) unless the evidence shows (a) makes agents unusable. (c) is ruled out in this PRD unless (a) and (b) both fail, because a stored mapping is PII at rest.

### F11 — Corpora and the round-trip suite
`code/` is Java, TypeScript, Python, YAML and JSON with example emails, names and phone-shaped numbers, fenced and unfenced. Under `code`, every fenced sample is byte-identical after redaction. Every unfenced sample keeps its quotes, backslashes and line structure, and every `.py` file still passes `ast.parse`. `prose/` samples are masked under both profiles with declared expected entities. `json/` samples still pass `json.loads` after redaction, with number-token PII quoted.

### F12 — Documentation
README: PII section around profiles, the Section 6.3 table, the Section 6.4 trade-off, new latency figures beside the existing ~0.93 s figure, the audit `profile` field, and the `redaction_characters` refusal. `.env.example`: six settings. The pre-PRD is marked promoted and its row in `pre-prds/README.md` is updated.

## 8. Technology Stack

| Layer | Choice | Note |
|---|---|---|
| Detection | Presidio `AnalyzerEngine` (existing) | Pattern recognizers for `code`; the full NER analyzer stays for `chat`. Versions currently unpinned in `requirements.txt`; STORY-003 records and pins them |
| NLP | spaCy `en_core_web_lg` (existing, `chat`); `spacy.blank("en")` (new, `code`) | The blank pipeline ships with the `spacy` package: no new download, no image size change |
| Replacement | `AnonymizerEngine` (existing, `chat`); own span replacement (new, `code`) | Structure-safe splitting and JSON clipping need control over spans that the anonymizer's operators do not give |
| JSON | stdlib `json` + a small token scanner | The scanner locates string and number tokens by offset; `json.loads` is the post-condition |
| Settings | `pydantic-settings` | Existing `Settings` class and validator style |
| Storage | libSQL / Turso | One additive nullable `TEXT` column, no index |
| Tests | `pytest`; corpora under `tests/corpora/pii/` | The PII tests load the real model (README, *Tests*); the tokenizer-only analyzer needs nothing extra |

No new third-party dependency.

## 9. Security & Configuration

### 9.1 Authentication & authorization
Unchanged. Redaction runs after all authorization arms. The profile is a call-site argument and no schema accepts it (PRD-011 T1), so a chat user cannot choose `code`.

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **`code` as a bypass**: a chat user gets the permissive policy | The profile is server-selected (PRD-011 Section 6.6). Unknown profile names fall back to `chat`, the strictest. A test asserts `/query` and `ChatState` produce `profile='chat'` rows |
| T2 | **PII inside a fenced block reaches the provider** | **Accepted**, the brief's documented trade-off (D2). A person who fences a customer list gets no masking of it under `code`. Configurable (`PII_CODE_SKIP_CODE_BLOCKS=false`). Stated in the README |
| T3 | **Names and places in prose are not masked under `code`** (D7) | **Accepted by default**, with the benchmark's evidence behind it; an operator adds `PERSON,LOCATION` back to `PII_ENTITIES_CODE` and pays NER's cost. Stated in the README |
| T4 | **Unmasked model output** under `code` (D1) | The model only has what input redaction released, plus what it produced itself. Configurable (`PII_CODE_REDACT_OUTPUT=true`) |
| T5 | **Size as a bypass**: a request too large to analyze goes out unmasked | Fail closed: over `PII_MAX_CHARACTERS_CODE` is refused and audited. Skip-and-flag is deliberately not shipped (D4) |
| T6 | **Redaction corrupts a tool result into invalid JSON** | JSON-aware clipping, with `json.loads` as a post-condition that fails closed (Section 6.6) |
| T7 | **A forged `assistant` turn carries PII past redaction** | `assistant` is redacted under `code` (Section 6.3), unlike the brief's proposal, because a `/v1` caller writes its own history |
| T8 | **Reversible mapping creates a new store of PII at rest** | Not built unless the spike's evidence requires it (D5). Option (b), indexed placeholders, needs no store |
| T9 | **Placeholder-shaped text written by a user** (`<PERSON>`) is later confused with a redaction | Unchanged from today: Presidio does not re-detect it, and it is not an escape of anything. Recorded, not mitigated |
| T10 | **CPU exhaustion**: many large requests pin the pipeline workers under the GIL | Bounded by `CONTEXT_MAX_*`, `PII_MAX_CHARACTERS_CODE` and `PIPELINE_MAX_WORKERS`. The benchmark measures throughput at concurrency 1 and 4. A process pool is Future Consideration |

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `PII_ENTITIES_CODE` | `EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE` | Non-empty; every name a known Presidio entity | Entity types under `code`. No NER type selects the tokenizer-only analyzer |
| `PII_SCORE_THRESHOLD_CODE` | provisional `0.5`, fixed by STORY-003 | `0 ≤ x ≤ 1` | Confidence threshold under `code` (D6) |
| `PII_MAX_CHARACTERS_CODE` | provisional `200000`, fixed by STORY-003 | `≥ 1` | Analyzable characters per request under `code`; over it is refused (D4) |
| `PII_CODE_REDACT_OUTPUT` | `false` | — | Redact the response under `code` (D1) |
| `PII_CODE_REDACT_SYSTEM` | `false` | — | Redact `system` turns under `code` (D3) |
| `PII_CODE_SKIP_CODE_BLOCKS` | `true` | — | Skip fenced blocks under `code` (D2) |

The four existing `PII_*` settings keep their meaning and apply to `chat` only. `PII_REDACTION_ENABLED=false` still turns off every policy. It is the master switch.

### 9.4 Out of scope (security)
Secret detection (PRD-015). Per-role PII telemetry and a record of what was skipped (PRD-013). Tool-call arguments beyond the stated contract (PRD-016). Non-English text, which passes the English recognizers largely unmasked, as today.

## 10. API Specification

**No change on any endpoint under the default configuration**, apart from one additive audit field:

| Endpoint | Change |
|---|---|
| `POST /query` | None. Runs `chat`. `redaction_characters` is unreachable (`chat.max_characters is None`) |
| Chat UI | None |
| `GET /audit` | `AuditQueryEntry.profile`, nullable. Additive |
| `GET /stats` | None. `pii_detected_queries` counts rows as before; `code` rows do not exist until PRD-014 |
| Admin console · Register | Shows `profile` |

`QueryBlockedContextLimitResponse.limit` widens from `Literal["messages", "characters"]` to add `"redaction_characters"`. This is additive, and only a `code` call site can produce it.

Internal API (Python):

```python
pii_policy.load() -> None                                   # startup only; raises PiiConfigError
pii_policy.get_pii_policy(name: str) -> PiiPolicy           # unknown name -> chat
pii_redactor.redact(text: str) -> tuple[str, list[str]]     # unchanged; the chat path
pii_redactor.redact_for_policy(text: str, policy: PiiPolicy) -> RedactionResult   # raises PiiRedactorError
pattern_detector.strip_fenced_blocks(text: str) -> str      # new, pure
run_conversation(identity, messages, device, model, openrouter_api_key,
                 params=None, call_openrouter=call_openrouter,
                 session_id=None, *, profile=None) -> QueryPipelineResult   # signature unchanged
```

## 11. Success Criteria

### MVP definition
Every file in `tests/corpora/pii/code/` round-trips through `code` with fenced samples byte-identical and unfenced samples structurally intact (`.py` parses, `.json` parses, quote and line counts equal). Every file in `tests/corpora/pii/prose/` is masked with its declared entities under both profiles. Every file in `tests/corpora/pii/json/` parses after redaction. The chat characterization suite, `test_pii_redactor.py`, `test_pii_redaction_integration.py` and the seven-outcome regression pass with no assertion changed. `code` p95 at 200,000 characters is under the budget STORY-003 recorded.

### Functional requirements
- [ ] `chat` produces byte-identical upstream messages, response and audit PII fields to today, for every characterization case
- [ ] `code` does not redact the output unless `PII_CODE_REDACT_OUTPUT=true`; `pii_detected_output` is `0` on those rows
- [ ] `code` does not redact `system` unless `PII_CODE_REDACT_SYSTEM=true`
- [ ] `code` redacts `user`, `assistant` and `tool` content (the last tested by direct call to `redact_for_policy`)
- [ ] Under `code`, an email inside a ``` or `~~~` fence is unchanged; the same email in prose around it is masked; an email in an inline backtick span **is** masked
- [ ] An unterminated fence skips to end of text
- [ ] Under `code` with the default entities, `Jane Doe` in prose is **not** masked and `jane@corp.com` is. With `PERSON` added to `PII_ENTITIES_CODE`, both are masked and the full analyzer is used
- [ ] With the default `PII_ENTITIES_CODE`, `en_core_web_lg` is never invoked on a `code` request (asserted via the analyzer selection, not timing)
- [ ] Structure-safe: a span covering `"Jane Doe"` including its quotes leaves both quotes in place; no `\`, quote, backtick or line break is ever removed or added
- [ ] JSON-aware: PII in a string value is replaced inside the quotes; PII that is a number token becomes `"<TYPE>"`; the result parses
- [ ] JSON post-condition failure raises `PiiRedactorError`, writes the existing redaction-error row, and makes no upstream call (forced with a stub analyzer)
- [ ] Over `PII_MAX_CHARACTERS_CODE`: `BLOCKED` with `limit="redaction_characters"`, one row with `success=0`, non-NULL `dedup_key`, `profile='code'`, no upstream call; fenced content does not count toward the limit
- [ ] A profile name with no PII policy resolves to `chat`, logged once at startup
- [ ] Every row `run_conversation` writes carries `profile`; `/query` and the chat UI write `profile='chat'`
- [ ] `init_db()` converges `audit_logs.profile` on a pre-existing database and backfills nothing
- [ ] Each of the six settings rejects an invalid value at startup with a message naming it
- [ ] `strip_code_spans` behaviour unchanged: PRD-011's pattern tests pass without modification

### Benchmark criteria (STORY-003 and STORY-013)
- [ ] Baseline numbers for today's code at 40k / 200k / 400k characters are recorded before any change
- [ ] Per-entity false-positive counts over the code corpus are recorded under today's settings and under `code`
- [ ] `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE` and the p95 budget at 200k are fixed from those numbers, and the report states how
- [ ] The corpus story re-runs the benchmark and asserts `code` p95 at 200k is under the budget; the README quotes both profiles' figures

### Refinement of the brief's criteria
- The brief's "p95 under a set budget at 50k tokens" is measured at **200,000 characters**, the harness's own unit (`CONTEXT_MAX_CHARACTERS`, PRD-010 used characters as the documented proxy).
- The brief's "a source file … round-trips … without syntax-breaking changes" is made testable as: fenced samples byte-identical; unfenced samples keep every quote, backslash and line break, and `.py` / `.json` still parse. An unfenced `"jane@example.com"` **does** become `"<EMAIL_ADDRESS>"`. That is not syntax-breaking, and it is the intended mask.

### Quality indicators
- [ ] Full suite green. Mass fixture errors mean restart the libSQL dev container, not bisect code
- [ ] No assertion changed in `test_pii_redactor.py`, `test_pii_redaction_integration.py`, `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`
- [ ] Every modified pre-existing test carries a comment citing PRD-012 and its decision
- [ ] The decision record for D5 exists and is linked from Section 15

## 12. Implementation Phases

### Phase 1 — Measure and pin (Stories 1–3)
**Goal:** today's behaviour and cost are recorded, and the corpus exists, before anything changes.
**Deliverables:** `tests/corpora/pii/` with `code/`, `prose/`, `json/`; characterization tests of `redact()` and steps 6/8; benchmark script and baseline report over that corpus, with Presidio/spaCy versions pinned.
**Validation:** characterization green on untouched code; the report shows the baseline and the false-positive counts that motivate D6/D7.

### Phase 2 — Primitives (Stories 4–8)
**Goal:** a policy-driven redaction function exists and is correct in isolation.
**Deliverables:** `strip_fenced_blocks` extracted; six settings with validators; tokenizer-only analyzer and analyzer selection; `pii_policy` with built-ins, fallback and `load()` in both lifespans; `redact_for_policy` with structure-safe replacement and JSON-aware mode.
**Validation:** PRD-011 pattern tests unchanged and green; structure-safe and JSON tests green; `chat` characterization still green.

### Phase 3 — Policy into the pipeline (Stories 9–11)
**Goal:** the pipeline redacts per profile, refuses over the limit, and records which profile ran.
**Deliverables:** steps 6/8 per policy; `redaction_characters` arm; `audit_logs.profile` through writer, reader, `/audit` and the Register.
**Validation:** seven-outcome regression and chat regression unchanged; `run_conversation(profile="code")` tests green.

### Phase 4 — Decide and prove (Stories 12–14)
**Goal:** the placeholder question is decided on evidence, the success criteria are demonstrated, and the docs say what `code` gives up.
**Deliverables:** D5 spike and decision record; the corpus round-trip suite with the latency-budget assertion; README, `.env.example`, pre-PRD promoted.
**Validation:** full suite green; benchmark rerun under budget; README figures match the report.

## 13. Future Considerations

- **Skip-and-flag over the size limit** (D4's deferred half), once PRD-013 provides a place to record which messages went out unmasked.
- **Per-role PII telemetry**: entities found per role, not only in the last user turn. PRD-010 D7 is kept here and revisited with PRD-013.
- **A PII policy file** in the PRD-011 patterns-file shape (or a `pii:` block in it), if operators need more than two built-in policies.
- **Structure-safe replacement for `chat`**: harmless for prose, but it changes what chat users see, so it is a separate, announced change.
- **Reversible placeholders** (D5: justified by STORY-012's spike, not adopted). Entry criteria are the at-rest requirements in [decisions/D5-placeholders.md](./decisions/D5-placeholders.md): a shared per-conversation store with retention, deletion, access control and exclusion from logs and audit. Indexed placeholders are dropped; they did no better than fixed ones.
- **A process pool for Presidio** if `chat`'s NER cost at agent scale turns out to matter, since the GIL caps thread concurrency.
- **Merge PII and pattern corpora** under one `tests/corpora/` taxonomy (PRD-011 Section 13 suggested this).
- **Secret detection** as its own recognizer set, with PRD-015.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Skipping fenced blocks lets real PII through** inside code a person pasted | High / Medium | Accepted and documented (T2). It is configurable, the profile is per ingress and not per caller, and prose around the block is still masked |
| 2 | **Presidio does not accept a tokenizer-only engine**, or its NLP step is not where the cost is | Medium / High | Verified first, in STORY-003, before anything depends on it. The fallback is the same pattern-only entity list on the full engine, with the budget set from what that measures. If even that misses any reasonable budget, the fallback is regex recognizers called directly, without `AnalyzerEngine` (the brief's fallback) |
| 3 | **Dropping `PERSON`/`LOCATION` under `code` is read as weakening the control** | Medium / Medium | It is a stated default (D7) backed by the benchmark's false-positive numbers; one setting restores it; the README says what `code` does not detect |
| 4 | **Structure-safe splitting under-masks**: a name split around an apostrophe (`O'Brien`) masks as `<PERSON>'<PERSON>` | Medium / Low | Only under `code`, where `PERSON` is off by default. Runs without an alphanumeric character are left alone. The corpus includes the case |
| 5 | **JSON post-condition fires in production** and turns requests into `500`s | Low / Medium | The JSON corpus covers strings, numbers, nesting and escapes; the post-condition is a backstop and fails closed rather than forwarding broken or unmasked JSON |
| 6 | **Chat behaviour drifts** through a shared helper | Low / High | `chat` keeps `redact()` and `AnonymizerEngine` untouched; characterization is pinned first; four named test files may not change an assertion |
| 7 | **The spike needs a live model** and cannot run in CI | High / Low | It is a decision story with a checked-in script and a written record, not a CI test. The default (fixed placeholders) needs no spike result to ship |

## 15. Appendix

### Source
- Pre-PRD brief: [pre-prds/PRE-PRD-012-pii-for-code.md](../../../pre-prds/PRE-PRD-012-pii-for-code.md)
- Track overview: [pre-prds/README.md](../../../pre-prds/README.md). Depends on PRD-010; uses PRD-011's profile argument and code-span parser; blocks PRD-014.

### Decisions (resolved from the brief's open decisions)

| # | Question | Decision |
|---|---|---|
| D1 | Output redaction under `code`? | **Off**, configurable (`PII_CODE_REDACT_OUTPUT`). As proposed |
| D2 | Code blocks under `code`? | **Fenced blocks skipped** for input; prose around them redacted; inline backtick spans **not** skipped. As proposed, narrowed to fences (Section 6.5) |
| D3 | Which roles are redacted? | `code`: **`user`, `assistant`, `tool`**; `system` configurable, off. *Deviation:* the brief treated `assistant` as already redacted. That holds for the chat UI, not for a `/v1` caller who writes its own history (Section 6.3, T7). `chat`: every role, as today |
| D4 | Over the size limit? | **Refuse, fail closed**, with `limit: "redaction_characters"`. *Partial deviation:* skip-and-flag is **deferred**. It is fail-open, and recording it needs PRD-013's telemetry (Section 6.7) |
| D5 | Reversible placeholders? | **Fixed by default**; a spike compares fixed, indexed-per-request and reversible, and writes `decisions/D5-placeholders.md`. Reversible only if both others fail. As proposed, with option (b) added. **Outcome (STORY-012):** (a) and (b) both failed and (c) matched the control, so (c) is justified but not adopted in this PRD because its mapping is PII at rest; fixed stays the default → [decisions/D5-placeholders.md](./decisions/D5-placeholders.md) |
| D6 | Separate threshold for `code`? | **Yes**, `PII_SCORE_THRESHOLD_CODE`, fixed from STORY-003's data. As proposed |
| D7 | *(new)* Entities under `code`? | **Pattern recognizers only** by default (`PII_ENTITIES_CODE` without `PERSON`/`LOCATION`), run on a tokenizer-only analyzer; restored if the benchmark shows both corpus and budget still pass with them (Section 6.4) |
| D8 | *(new)* How is the PII policy selected? | **By the PRD-011 profile name**; unknown names fall back to `chat`, the strictest (Section 6.2) |
| D9 | *(new)* How does the audit say which policy ran? | **`audit_logs.profile`**, nullable, on every arm, no backfill (Section 6.8) |

### Evidence (verified against `epic/PRD-011-pattern-policy` @ `82b3f3d`)
- `app/services/pii_redactor.py`: one lazily built `AnalyzerEngine` over `PII_NLP_MODEL`; `redact(text) -> (text, sorted entity types)`; default `AnonymizerEngine` operator, which writes `<ENTITY_TYPE>`.
- `app/config.py`: `PII_SCORE_THRESHOLD = 0.35`; `PII_ENTITIES` includes `PERSON` and `LOCATION`; `CONTEXT_MAX_CHARACTERS = 200_000`; `PIPELINE_MAX_WORKERS = 32`; `_RESOURCE_BOUNDS` for validator messages.
- `app/services/query_pipeline.py`: step 6 calls `redact(message.content)` for every message and keeps only the last message's entities (PRD-010 D7); step 8 calls `redact(openrouter_result.response)`; `run_conversation(..., *, profile=None)` resolves to `PATTERN_PROFILE_DEFAULT`; `_validate_conversation` refuses `tool` turns.
- `app/models/messages.py`: `Role = Literal["system", "user", "assistant", "tool"]`; `normalize_message` refuses `tool_calls`.
- `app/services/pattern_detector.py`: `strip_code_spans` does a fence pass then an inline pass, and blanks spans with newlines to preserve length and offsets.
- `app/db/models.py`: `audit_logs` has `pii_detected_input`, `pii_detected_output`, `pii_entities`, `pattern_role`, `pattern_action`; no profile column; `AUDIT_LOGS_ADDED_COLUMNS` is the convergence path.
- `README.md`: re-redaction is ~97% of ~0.93 s added per chat send at 41 messages / ~19k characters, ~23 ms per message (`scripts/measure_history_latency.py`).
- `requirements.txt`: `presidio-analyzer`, `presidio-anonymizer` and `spacy` unpinned.
- `pre-prds/PRE-PRD-016-tool-calling.md`: "Tool-call arguments never PII-redacted; JSON validity guaranteed (PRD-012)."
- Branch state: `main` is at the PRD-009 merge; `epic/PRD-011-pattern-policy` contains PRD-010 and all 13 PRD-011 stories, unmerged.

### Story breakdown (generated by `/create-stories`, see [index.md](./index.md))
Reordered from the tentative list: the corpus comes before the benchmark, which counts false positives over it, and `pii_policy` comes before `redact_for_policy`, which takes a policy.

1. STORY-001 PII corpora: `code/`, `prose/`, `json/` (brief 11)
2. STORY-002 Characterization of today's `redact()` and pipeline steps 6/8 (brief 12)
3. STORY-003 Benchmark harness, baseline numbers, Presidio/spaCy pinned, tokenizer-only analyzer feasibility (brief 1; D6, D7)
4. STORY-004 `strip_fenced_blocks` extracted; `strip_code_spans` rebuilt on it (brief 4)
5. STORY-005 Six settings with startup validators (brief 2, 7)
6. STORY-006 Pattern-only analyzer and analyzer selection by entity list (D7)
7. STORY-007 `pii_policy`: built-in `chat`/`code`, fallback, `load()` in both lifespans (brief 2, 3; D8)
8. STORY-008 `redact_for_policy`: fence skipping, structure-safe replacement, JSON-aware mode and post-condition (brief 4, 5)
9. STORY-009 Pipeline steps 6/8 per policy (brief 9)
10. STORY-010 Size limit and the `redaction_characters` refusal arm (brief 6; D4)
11. STORY-011 `audit_logs.profile` column, `/audit` and Register; PII telemetry regression (brief 10; D9)
12. STORY-012 Placeholder spike and `decisions/D5-placeholders.md` (brief 8; D5)
13. STORY-013 Code round-trip suite with the latency-budget assertion (brief 11)
14. STORY-014 `chat` regression sweep, README and `.env` docs, pre-PRD promoted (brief 12, 13)

### Related documents
- PRD-003 (PII redaction): the original Presidio integration and its `PII_*` settings
- PRD-009 (duplicate rescoping): `success=0` rows never count as prior queries; nullable columns without backfill
- PRD-010 (multi-turn pipeline): `Message`, `Role`, step 6 "redact every message" (D5), audit PII semantics (D7), the context-limit response shape
- PRD-011 (pattern policy): the `profile` argument, `strip_code_spans`, the corpus layout, the `pattern_config.load()` startup pattern
- [decisions/D5-placeholders.md](./decisions/D5-placeholders.md): the placeholder spike (STORY-012) — method, raw results, decision

### Dependencies
- Depends on: PRD-010 (done), PRD-011 (done, unmerged). The epic branch must be cut from `main` **after** PRD-010 and PRD-011 are merged, or from the tip of `epic/PRD-011-pattern-policy`. Cut from today's `main`, it lacks `Message`, `run_conversation` and `profile`.
- Blocks: PRD-014; its JSON-aware mode is also what PRD-016 relies on.

**Skills referenced:** none. `.agents/skills/` contains only `frontend-design`, whose description scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This PRD's only UI change is one nullable `profile` field on the existing admin Register row, so no rule from it applies to Sections 6, 8, 9 or 11.
