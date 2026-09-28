# PII corpus: sources

Checked-in samples for PRD-012 (PII redaction for code). `tests/test_pii_corpus_files.py`
proves that they exist, parse and declare what they contain. Later stories use
them:
- STORY-003 counts false positives over `code/` and times redaction over
  conversations built from it.
- STORY-008 and STORY-013 assert redaction behaviour over all three
  directories.

Every file here except this one is a sample and is discovered from disk. To
add a sample, drop the file in and add a section below. The test refuses a
sample this file does not name.

**Every value in this corpus is synthetic.** No real person's data is in the
repository. All samples were written for this corpus on **2026-09-23**. None is
copied from an upstream project, so there is no upstream commit or licence to
record. The table below says where each class of value comes from, so a
reviewer can check that none of it is real.

---

## Value classes

| Class | What is used | Why it cannot be real |
|---|---|---|
| Email | `*@example.com`, `*@example.org` only | RFC 2606 reserves both domains. A test (`test_every_email_in_the_corpus_is_on_a_reserved_domain`) enforces it |
| US phone | `NPA-555-0100` to `NPA-555-0199`, e.g. `+1 415 555 0134`, `(212) 555-0147`, `14155550134` | NANP reserves `555-0100`–`555-0199` for fictional use |
| Payment card | `4111 1111 1111 1111` (Visa), `5555 5555 5555 4444` (Mastercard) | Published processor test PANs. They pass Luhn and are never issued |
| IBAN | `GB82 WEST 1234 5698 7654 32`, `DE89 3704 0044 0532 0130 00` | The standard published example IBANs. They pass mod-97 |
| US SSN | `219-09-9999` (declared) and `078-05-1120` (a deliberate non-match) | `219-09-9999` is a widely published example. `078-05-1120` is the 1938 wallet-insert number, which the SSA voided |
| Names | The cast below | Invented for this corpus |
| Other | Hosts on `example.com`, IPs from `203.0.113.0/24` (RFC 5737), invented order numbers, UUIDs and paths | Reserved or made up |

**Cast.** Every code sample names at least one of these, and the loader test
checks that it does: Jane Doe, Patrick O'Brien, Maria Lopez, Priya
Raghunathan, Kenji Watanabe, Aisha Bello, Tomás Herrera, Zoë Müller-Schmidt.
`crm-contact-search.json` adds sixteen more invented names so that a search
result has a realistic size: Daniel Okafor, Ingrid Larsen, Samuel Whitaker,
Lucía Fernández, Wei Zhang, Fatima Haddad, Oliver Bennett, Hannah Kowalski,
Rahul Mehta, Grace Adeyemi, Mateo Rossi, Chloe Martin, Yusuf Demir, Emily
Nguyen, Sean Gallagher and Nadia Petrova.

## What Presidio does with these values

These are the settings that shaped the files. They were measured with the
analyzer `app/services/pii_redactor.py` builds: presidio-analyzer 2.2.364,
spaCy 3.8.16 with `en_core_web_lg`, and phonenumbers 9.0.38.

- A `555-01xx` number with its area code scores **0.40** as `PHONE_NUMBER`
  with no context word nearby. With `phone`, `mobile`, `cell` or `telephone`
  within a few tokens it scores **0.75**. The word `call` does not raise the
  score. A bare seven-digit `555-0142` is not detected at all.
- Today's `chat` threshold is 0.35. The provisional `code` threshold is 0.5.
  So **every phone number in `prose/` carries a context word**, and `code/`
  deliberately mixes both shapes for STORY-003 to measure.
- Phone and card numbers written as JSON number tokens (`"phone": 14155550134`,
  `"number": 4111111111111111`) are detected at ≥ 0.5.
- The word `IBAN` is itself tagged `LOCATION` (0.85), a false positive worth
  knowing about.

## The `prose/` header

Line 1 of every `prose/` file is:

    # expect: <ENTITY>, <ENTITY>, ...

The names come from the seven configured in `app/config.py` (`PII_ENTITIES`).
The header lists the entity types **present** in the file and is a lower
bound. It does not say which types every profile masks. Under the `code`
profile, `PERSON` is not detected by default (PRD-012 D7), so consumers assert
`declared ∩ policy.entities ⊆ found`. `prose/` files contain no code fences,
so everything declared sits in prose, which both profiles analyze.

---

## `code/`

### `CustomerFixtures.java`

- **Shape**: a JUnit-style fixture class for a billing module: builders,
  test cards, CSV and email templates, nested constant holders.
- **Contains**: emails, cast names, phones in five shapes, both test cards,
  an IBAN, `078-05-1120`, and near-misses such as `JaneDoeFixture` and
  `PHONE_REGEX`.
- **Edge cases**: `"Patrick O'Brien"` and the SQL-escaped `O''Brien`. PII
  right against quotes (`"jane.doe@example.com"`). An escaped quote
  (`\"call me on 415-555-0199 ...\"`). Backslash paths (`"C:\\Users\\..."`,
  UNC `"\\\\fileserver\\..."`). JSON inside a Java string.
- **Why it is here**: Java is the language the PRD's user story names
  (`UserFixtures.java`).

### `contact-directory.ts`

- **Shape**: a TypeScript contact store with seed data, email and phone
  regexes, vCard export and inline vitest tests.
- **Contains**: every cast member, context-boosted and bare phones, template
  literals interpolating PII.
- **Edge cases**: `O'Brien`, PII against quotes, escaped quotes in `"..."`,
  a single-quoted string wrapping a double-quoted path, and Windows paths.
- **Why it is here**: TypeScript is AC 1's `.ts`. Template literals and regex
  literals are structure a redactor must not break.

### `billing_seed.py`

- **Shape**: a database seed script with dataclasses, dict literals, SQL,
  CSV export and argparse.
- **Contains**: emails, names, phones, both cards, both IBANs, a US SSN
  non-match.
- **Edge cases**: `"Patrick O'Brien"` and `'Patrick O\'Brien'` (the escaped
  apostrophe in a single-quoted string, PRD Risk 4). A raw path
  `r"C:\Users\jdoe\exports"`, an escaped path, a UNC path, and `\"` inside
  strings.
- **Why it is here**: AC 1's `.py`. It must still pass `ast.parse`. It is
  deliberately **not** named `test_*.py`, so pytest never collects it.

### `staging-values.yaml`

- **Shape**: Helm values for a billing service: on-call contacts, SMTP,
  alertmanager receivers, cron jobs.
- **Contains**: emails and names in plain, single-quoted and double-quoted
  scalars. Phones in E.164 (`+14155550134`) and national shapes. A test card
  and an IBAN.
- **Edge cases**: `\\` and `\"` in double-quoted scalars, and `O'Brien`
  inside a double-quoted scalar.
- **Why it is here**: AC 1's `.yaml`. Config files are what agents edit most.

### `seed-users.json`

- **Shape**: a repository fixture file: users, roles, billing accounts,
  notes.
- **Contains**: PII in string values, nested three or more levels deep.
  Phones as strings. A test card and an IBAN as strings.
- **Edge cases**: `\"` and `\\` escapes, and `O'Brien`.
- **Why it is here**: AC 1's `.json`, the repo-fixture kind. The tool-result
  kind, with number tokens and PII keys, is in `json/`.

### `onboarding-runbook.md`

- **Shape**: an on-call runbook a user pastes into an assistant.
- **Contains**:
  - PII in prose and in a table.
  - ```` ``` ```` fences (`text`, `json`, `python`), `~~~` fences (`sql`,
    `bash`) and a `~~~~` fence.
  - A four-backtick fence whose content includes a ```` ``` ```` line.
  - **Unfenced** code: a `curl` line and two Java lines.
  - An inline span holding an email (`` `ops@example.org` ``), which PRD D2
    says must still be masked.
- **Why it is here**: AC 1's Markdown sample, and the D2 fence-skipping cases
  for STORY-008.

### `handoff-unterminated.md`

- **Shape**: a shift-handoff note whose final ```` ```yaml ```` fence is
  never closed.
- **Contains**: PII in prose, in a closed fence, and after the unterminated
  opener through to the end of the file.
- **Edge cases**: the unterminated fence (AC 2). Under PRD-011's parser it
  runs to the end of the text.
- **Why it is here**: PRD Section 11, "an unterminated fence skips to end of
  text".

## `prose/`

### `support-refund-request.txt`

- **Shape**: a customer's refund email.
- **Declares**: `EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, PERSON`.
- **Why it is here**: a card number typed into prose.

### `payroll-bank-change.txt`

- **Shape**: an employee asking HR to change their salary account.
- **Declares**: `IBAN_CODE, EMAIL_ADDRESS, PERSON`.
- **Why it is here**: two IBANs in grouped form, and an apostrophe name.

### `vendor-onboarding.md`

- **Shape**: a procurement note setting up a vendor.
- **Declares**: `PERSON, EMAIL_ADDRESS, PHONE_NUMBER, IBAN_CODE`.
- **Why it is here**: an ungrouped IBAN and several phone shapes.

### `benefits-enrollment.txt`

- **Shape**: a new hire typing a benefits form into chat.
- **Declares**: `PERSON, US_SSN, PHONE_NUMBER`.
- **Why it is here**: the only `US_SSN` sample.

### `agent-task-with-contacts.md`

- **Shape**: a developer instructing a coding agent: "email the diff to …
  and call … on …".
- **Declares**: `EMAIL_ADDRESS, PHONE_NUMBER`.
- **Why it is here**: PRD user story 3. It has no `PERSON`, so it is fully
  masked under both default profiles.

### `escalation-thread.txt`

- **Shape**: a forwarded email chain.
- **Declares**: `PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD`.
- **Why it is here**: headers in `Name <email>` form, several people, two
  cards.

## `json/`

### `crm-contact-search.json`

- **Shape**: a CRM search tool's result: 24 contacts, each with a nested
  `address.geo`.
- **Contains**: PII in string values, and **every phone as a JSON number
  token** (`"phone": 14155550134`). Also `true`/`false`/`null`, floats and
  integer ids beside the PII. Generated once by script, then checked in.
- **Why it is here**: AC 4's phone-as-number and nesting cases, at a size
  that means something for the benchmark.

### `payment-webhook.json`

- **Shape**: a payment processor's `charge.dispute.created` event.
- **Contains**: **card numbers as number tokens** (`"number":
  4111111111111111`, `5555555555554444`), a phone number token, an IBAN
  string, and PII in `metadata` and `evidence`.
- **Edge cases**: `\"` in a note, and `\\` in Windows and UNC paths.
- **Why it is here**: AC 4's card-as-number case.

### `directory-index-by-email.json`

- **Shape**: a directory export keyed by email address.
- **Contains**: **PII in keys**, and emails as values that refer to other
  keys.
- **Why it is here**: AC 4's PII-in-keys case.

### `ticket-thread-export.json`

- **Shape**: a help-desk ticket thread export.
- **Contains**: long `body` strings with `\n`, `\"quoted speech\"`, and
  `\\` Windows and UNC paths. PII inside those strings.
- **Why it is here**: AC 4's escapes case. PII sits next to escape sequences
  inside strings.

### `build-log-escapes.json`

- **Shape**: a CI run's tool result: run metadata, notification settings,
  per-step logs and artifact paths.
- **Contains**: default `code` entities (email, phone, IBAN, card) placed
  **directly after** an escape sequence: `\njane.doe@example.com`,
  `\t+1 415 555 0134`, `\"maria.lopez@example.org\"`, `\nGB82 WEST ...`, and
  emails as path segments right after `\`. Also `true`/`null`, a float and
  integer ids beside them. Added on 2026-09-25 by STORY-013.
- **Why it is here**: STORY-008 finding M1. With escape handling removed from
  `redact_for_policy`, no other corpus file failed to parse, because the only
  PII after an escape was a `PERSON` (off under `code`). Here a default-entity
  span starts inside the escape (`\n` + `jane...` matches as `njane...`), so
  the JSON post-condition fails unless the escape is kept whole.
