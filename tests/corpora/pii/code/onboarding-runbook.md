# Billing service: on-call onboarding runbook

Welcome to the billing rotation. This page is what you paste into the coding
assistant when you want it to help you with a billing incident, so keep it
current. Owner: Jane Doe (jane.doe@example.com). If anything here is wrong,
tell Jane or ping Priya Raghunathan on priya.raghunathan@example.org, mobile
+1 212 555 0147, before you change it.

## 1. Who to call

| Rotation   | Person            | Email                          | Phone              |
|------------|-------------------|--------------------------------|--------------------|
| Primary    | Patrick O'Brien   | patrick.obrien@example.org     | mobile (415) 555-0172 |
| Secondary  | Maria Lopez       | maria.lopez@example.com        | phone 212-555-0147 |
| Escalation | Aisha Bello       | aisha.bello@example.com        | cell +1-646-555-0118 |

Aisha asked that we text first: "text before you call, unless payments are
down". If you cannot reach anyone, the shared inbox is `ops@example.org`; it
is read by whoever holds the pager.

## 2. First five minutes

1. Acknowledge the page.
2. Check the dashboard and the error budget.
3. Post in the incident channel with the template below.
4. If card payments are failing, page Patrick O'Brien directly on his mobile,
   +1 415 555 0134, even at night.

The incident template (copy it exactly, the bot parses it):

```text
INCIDENT: billing / <short title>
Commander: <your name> (<your email>)
Customer impact: <yes/no, who>
Contacts: Patrick O'Brien <patrick.obrien@example.org>, Maria Lopez <maria.lopez@example.com>
Bridge: +1 415 555 0199
```

## 3. Checking a customer's account

Most tickets start with "customer X says they were charged twice". Look the
customer up by email first. From a jump host you can run this directly:

curl -s -H "Authorization: Bearer $BILLING_TOKEN" "https://billing.staging.example.com/api/v2/customers?email=jane.doe@example.com" | jq '.results[0]'

The same lookup from the admin console's SQL tab:

~~~sql
SELECT customer_id, display_name, email, phone, status
FROM customers
WHERE email = 'maria.lopez@example.com'
   OR phone IN ('212-555-0147', '+1 212 555 0181');
~~~

If the customer is Patrick O'Brien (he tests in production, sorry), remember
the apostrophe: `display_name = 'Patrick O''Brien'` in SQL.

When the API returns the customer, it looks like this:

```json
{
  "id": 1003,
  "displayName": "Maria Lopez",
  "email": "maria.lopez@example.com",
  "phone": "212-555-0147",
  "status": "suspended",
  "notes": "Said \"call me on 415-555-0199 before charging\""
}
```

## 4. Refunds

Refunds over $500 need a second approver. Ask Kenji Watanabe
(kenji.watanabe@example.org, phone: +1 646 555 0118) or Tomás Herrera
(tomas.herrera@example.com). Never refund to a different card than the one
charged. In staging, the only card that works is the Visa test PAN.

~~~bash
# staging only -- the sandbox rejects every other PAN
billingctl refund create \
  --customer jane.doe@example.com \
  --amount 120.00 \
  --card 4111111111111111 \
  --reason "duplicate charge, ticket 88213" \
  --approver "Kenji Watanabe <kenji.watanabe@example.org>"
~~~

In Java, the refund client call in a quick test harness is just this, and you
will see it pasted in tickets without any formatting:

RefundClient client = new RefundClient("https://sandbox.payments.example.com/v2");
client.refund(new RefundRequest("jane.doe@example.com", new BigDecimal("120.00"), "4111111111111111"));

## 5. SEPA mandates

European customers pay by SEPA. The creditor account is our example IBAN
GB82 WEST 1234 5698 7654 32; the mandate reference is printed on the
invoice. If Zoë Müller-Schmidt (zoe.mueller-schmidt@example.org, our DPO) asks
for a data export for a SEPA customer, it goes through the GDPR queue, not
through billing.

~~~~yaml
sepa:
  creditorName: "Example Corp Ltd"
  creditorIban: "GB82WEST12345698765432"
  contact: "zoe.mueller-schmidt@example.org"
~~~~

## 6. Exports for finance

Finance wants a CSV every month. The job writes to the Windows share, and the
path has to be escaped when you put it in a config file:

````markdown
In the values file, write the share with doubled backslashes:

```yaml
BILLING_ARCHIVE_SHARE: "\\\\fileserver\\finance\\billing-archive"
```

and in a shell on the build agent it is simply \\fileserver\finance\billing-archive.
Questions go to Aisha Bello, aisha.bello@example.com.
````

If the export is late, email finance-ops@example.com and copy Maria Lopez.
Her desk phone is 212-555-0147 but she prefers email.

## 7. Handing over

At the end of your shift, write a handoff note. Include the open tickets, who
you spoke to and on which number, and anything you promised a customer. For
example: "Called Jane Doe on +1 415 555 0134 at 14:10, she confirmed the
duplicate; refund pending Kenji's approval."

```python
# handoff.py -- paste the output into the channel
HANDOFF = {
    "from": "patrick.obrien@example.org",
    "to": "maria.lopez@example.com",
    "open": ["88213", "88240"],
    "called": [("Jane Doe", "+1 415 555 0134")],
}
print(HANDOFF)
```

## 8. Useful identifiers

These look like PII to naive scanners but are not: `JaneDoeFixture` (a test
class), `getUserByEmail` (a method), order number 4000813378, tenant id
7d1c2b8e-4f3a-4c21-9e55-0a6b1f2c3d4e, and the SMTP port 2525. The tax id
078-05-1120 in the fixtures is intentionally invalid.

## 9. Changelog

- 2026-03-14: Jane Doe moved the escalation contact to Aisha Bello.
- 2026-02-20: Patrick O'Brien added the SEPA section.
- 2026-01-09: Priya Raghunathan wrote the first version.
