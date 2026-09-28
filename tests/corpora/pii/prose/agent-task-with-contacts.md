# expect: EMAIL_ADDRESS, PHONE_NUMBER
Can you finish the refactor of the invoice exporter we started yesterday?
The tests in the billing module should all pass before you stop.

When you are done, email the diff to reviewers@example.org and to
release-manager@example.com, with a short summary of what changed. If the
migration step fails, do not retry it more than twice; instead tell the
on-call engineer, whose phone number this week is +1 415 555 0134.

A few constraints:
- Keep the public API of the exporter unchanged.
- Do not touch the SEPA code path, it is frozen until the audit is done.
- If you need a staging database, ask dba-requests@example.com; it usually
  takes an hour.

For anything blocking, the team lead's mobile is (212) 555-0147. Text first,
she does not answer unknown numbers.

Thanks!
