# Shift handoff: billing on-call, 2026-03-14 (night)

From: Patrick O'Brien <patrick.obrien@example.org>
To: Maria Lopez <maria.lopez@example.com>

Quiet shift until 02:40, then the nightly invoice run failed for tenant
7d1c2b8e. I called Jane Doe on her mobile, +1 415 555 0134, because she owns
the job; she said to rerun it after the DB failover finished.

## What I ran

```bash
kubectl -n billing logs job/nightly-invoice-run-29011 --tail=200
kubectl -n billing create job --from=cronjob/nightly-invoice-run rerun-0314
```

The rerun finished at 03:22. Invoices for 1,204 customers went out. Two
customers bounced:

- priya.raghunathan@example.org (mailbox full; she is on leave, her
  delegate is Kenji Watanabe, kenji.watanabe@example.org)
- tomas.herrera@example.com (typo in the domain in the old record, fixed)

## Open items for you

1. Ticket 88213: Maria, this is your duplicate-charge customer. She called
   again at 04:05 from phone (212) 555-0147 and said "call me back on the
   mobile, 415.555.0199, not the desk line".
2. Ticket 88240: Aisha Bello (aisha.bello@example.com) wants the refund to
   go to the original card. The card on file ends 1111; it is the staging
   test card, so this is probably a QA account that leaked into prod.
3. Zoë Müller-Schmidt asked for the export path again. It is
   C:\Users\svc-billing\exports on the build agent; I have not replied yet.

## Config I was about to push

I started editing the on-call block and did not finish. Please check it
before applying anything. The fence below is left open on purpose, the way
the chat client cut it off:

```yaml
oncall:
  primary:
    name: "Maria Lopez"
    email: maria.lopez@example.com
    mobile: "(212) 555-0147"
  secondary:
    name: "Patrick O'Brien"
    email: patrick.obrien@example.org
    mobile: "+1 415 555 0172"
  escalation:
    name: Aisha Bello
    email: aisha.bello@example.com
    phone: "+1-646-555-0118"
    note: "She said \"text before you call\"."
  exports:
    path: "C:\\Users\\svc-billing\\exports"
    share: "\\\\fileserver\\finance\\billing-archive"
  notify:
    - jane.doe@example.com
    - kenji.watanabe@example.org
  smokeTestCard: "4111111111111111"
  creditorIban: "GB82WEST12345698765432"
