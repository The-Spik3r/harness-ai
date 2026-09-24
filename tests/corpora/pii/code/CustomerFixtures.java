package com.example.billing.testsupport;

import java.math.BigDecimal;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;

import com.example.billing.domain.Address;
import com.example.billing.domain.Customer;
import com.example.billing.domain.CustomerStatus;
import com.example.billing.domain.Invoice;
import com.example.billing.domain.InvoiceLine;
import com.example.billing.domain.PaymentMethod;

/**
 * Deterministic fixtures for the billing module's integration tests.
 *
 * <p>Every value here is synthetic: emails use the reserved example.com and
 * example.org domains, phone numbers sit in the 555-0100..555-0199 block, and
 * card numbers are the processors' published test PANs. Do not replace them
 * with anything copied from production, even "anonymised" rows.
 *
 * @author Jane Doe (jane.doe@example.com)
 * @author Patrick O'Brien
 * @since 2.4.0
 */
public final class CustomerFixtures {

    /** Matches the validation used by {@code CustomerValidator#isValidEmail}. */
    public static final Pattern EMAIL_REGEX =
            Pattern.compile("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");

    /** North American numbers only; the international path lives in PhoneNormalizer. */
    public static final Pattern PHONE_REGEX =
            Pattern.compile("^\\+?1?[ .-]?\\(?\\d{3}\\)?[ .-]?\\d{3}[ .-]?\\d{4}$");

    public static final Clock FIXED_CLOCK =
            Clock.fixed(Instant.parse("2026-03-14T09:30:00Z"), ZoneOffset.UTC);

    public static final String EXPORT_DIR = "C:\\Users\\pobrien\\Documents\\invoices";
    public static final String SHARED_DROP = "\\\\fileserver\\finance\\exports\\2026-Q1";
    public static final int SMTP_PORT = 2525;
    public static final long ORDER_NUMBER_SEED = 4_000_812_377L;

    private static final UUID TENANT_ID = UUID.fromString("7d1c2b8e-4f3a-4c21-9e55-0a6b1f2c3d4e");

    private CustomerFixtures() {
        throw new AssertionError("no instances");
    }

    // ---------------------------------------------------------------- customers

    public static Customer janeDoe() {
        return new Customer.Builder()
                .id(1001L)
                .tenantId(TENANT_ID)
                .displayName("Jane Doe")
                .email("jane.doe@example.com")
                .phone("+1 415 555 0134")
                .status(CustomerStatus.ACTIVE)
                .createdAt(Instant.parse("2025-11-02T14:05:00Z"))
                .billingAddress(new Address("221 Market Street", "Suite 400", "San Francisco", "CA", "94105", "US"))
                .build();
    }

    public static Customer patrickOBrien() {
        // The apostrophe is deliberate: it has broken CSV export twice (BILL-812, BILL-977).
        return new Customer.Builder()
                .id(1002L)
                .tenantId(TENANT_ID)
                .displayName("Patrick O'Brien")
                .email("patrick.obrien@example.org")
                .phone("+1-415-555-0134")
                .status(CustomerStatus.ACTIVE)
                .createdAt(Instant.parse("2025-12-19T08:00:00Z"))
                .billingAddress(new Address("9 Harbour Road", null, "Oakland", "CA", "94607", "US"))
                .build();
    }

    public static Customer mariaLopez() {
        return new Customer.Builder()
                .id(1003L)
                .tenantId(TENANT_ID)
                .displayName("Maria Lopez")
                .email("maria.lopez@example.com")
                .phone("(212) 555-0147")
                .status(CustomerStatus.SUSPENDED)
                .createdAt(Instant.parse("2026-01-07T17:45:00Z"))
                .billingAddress(new Address("48 Grand Avenue", "Apt 3B", "New York", "NY", "10013", "US"))
                .build();
    }

    public static Customer priyaRaghunathan() {
        return new Customer.Builder()
                .id(1004L)
                .tenantId(TENANT_ID)
                .displayName("Priya Raghunathan")
                .email("priya.raghunathan@example.org")
                .phone("415.555.0199")
                .status(CustomerStatus.PENDING_VERIFICATION)
                .createdAt(Instant.parse("2026-02-11T11:20:00Z"))
                .build();
    }

    /** A customer with no contact details at all, for the "missing fields" paths. */
    public static Customer anonymousWalkIn() {
        return new Customer.Builder()
                .id(1999L)
                .tenantId(TENANT_ID)
                .displayName("Walk-in")
                .status(CustomerStatus.ACTIVE)
                .createdAt(Instant.parse("2026-02-28T23:59:59Z"))
                .build();
    }

    public static List<Customer> allCustomers() {
        List<Customer> customers = new ArrayList<>();
        customers.add(janeDoe());
        customers.add(patrickOBrien());
        customers.add(mariaLopez());
        customers.add(priyaRaghunathan());
        customers.add(anonymousWalkIn());
        return Collections.unmodifiableList(customers);
    }

    // ----------------------------------------------------------- payment methods

    public static PaymentMethod visaTestCard(Customer owner) {
        return PaymentMethod.card(owner.getId(), "4111111111111111", "12/29", "Jane Doe");
    }

    public static PaymentMethod mastercardTestCard(Customer owner) {
        return PaymentMethod.card(owner.getId(), "5555 5555 5555 4444", "07/28", owner.getDisplayName());
    }

    public static PaymentMethod sepaMandate(Customer owner) {
        // ECBS example IBAN; never a real account.
        return PaymentMethod.sepa(owner.getId(), "GB82WEST12345698765432", "Patrick O'Brien");
    }

    /**
     * Legacy US tax-id field. 078-05-1120 is the famous wallet-insert number and
     * is rejected by every validator we ship; it exists to exercise that branch.
     */
    public static final String REJECTED_TAX_ID = "078-05-1120";

    // ------------------------------------------------------------------ invoices

    public static Invoice openInvoiceFor(Customer customer) {
        Invoice invoice = new Invoice(
                ORDER_NUMBER_SEED + customer.getId(),
                customer.getId(),
                LocalDate.of(2026, 3, 1),
                LocalDate.of(2026, 3, 31));
        invoice.addLine(new InvoiceLine("SKU-10442", "Annual support plan", 1, new BigDecimal("1200.00")));
        invoice.addLine(new InvoiceLine("SKU-20017", "Extra seats (5)", 5, new BigDecimal("39.00")));
        invoice.setNotes("Contact " + customer.getDisplayName() + " at " + customer.getEmail() + " before dunning.");
        return invoice;
    }

    public static Invoice disputedInvoice() {
        Invoice invoice = openInvoiceFor(mariaLopez());
        invoice.setNotes("Customer said \"call me on 415-555-0199 before you charge the card\" and hung up.");
        invoice.markDisputed("Duplicate charge reported by maria.lopez@example.com on 2026-03-09");
        return invoice;
    }

    public static Map<String, String> csvRow(Customer customer) {
        Map<String, String> row = new LinkedHashMap<>();
        row.put("customer_id", String.valueOf(customer.getId()));
        row.put("display_name", customer.getDisplayName());
        row.put("email", Optional.ofNullable(customer.getEmail()).orElse(""));
        row.put("phone", Optional.ofNullable(customer.getPhone()).orElse(""));
        row.put("status", customer.getStatus().name());
        return row;
    }

    public static Path exportPathFor(Customer customer) {
        String safeName = customer.getDisplayName().replace("'", "").replace(' ', '_').toLowerCase();
        return Paths.get(EXPORT_DIR, safeName + "-" + customer.getId() + ".csv");
    }

    // ------------------------------------------------------------ support emails

    public static String welcomeEmailBody(Customer customer) {
        return String.join("\n",
                "Hi " + customer.getDisplayName() + ",",
                "",
                "Your billing account is ready. Reply to billing@example.com with any questions,",
                "or call our billing desk on +1 212 555 0163 (Mon-Fri, 9-5 ET).",
                "",
                "Kenji Watanabe",
                "Customer Success, Example Corp");
    }

    public static String escalationTemplate() {
        return "Escalate to \"Aisha Bello\" <aisha.bello@example.org>, phone: (415) 555-0172.\n"
                + "Attach the export from C:\\Users\\abello\\Downloads\\dispute-pack.zip";
    }

    // ------------------------------------------------------------------- helpers

    public static boolean looksLikeEmail(String candidate) {
        return candidate != null && EMAIL_REGEX.matcher(candidate).matches();
    }

    public static boolean looksLikePhone(String candidate) {
        return candidate != null && PHONE_REGEX.matcher(candidate).matches();
    }

    public static Customer byEmail(String email) {
        Objects.requireNonNull(email, "email");
        return allCustomers().stream()
                .filter(c -> email.equalsIgnoreCase(c.getEmail()))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("no fixture customer with email " + email));
    }

    public static String maskedPhone(String phone) {
        if (phone == null || phone.length() < 4) {
            return "****";
        }
        return "***-***-" + phone.substring(phone.length() - 4);
    }

    /** Order of the fixtures matters for the pagination tests; keep it stable. */
    public static List<String> expectedEmailsInIdOrder() {
        return List.of(
                "jane.doe@example.com",
                "patrick.obrien@example.org",
                "maria.lopez@example.com",
                "priya.raghunathan@example.org");
    }

    public static final class JaneDoeFixture {
        public static final long ID = 1001L;
        public static final String EMAIL = "jane.doe@example.com";
        public static final String MOBILE = "+1 415 555 0134";
        public static final String NOTES = "Prefers email; mobile only for outages.";

        private JaneDoeFixture() {
        }
    }

    public static final class OBrienFixture {
        public static final long ID = 1002L;
        public static final String NAME = "Patrick O'Brien";
        public static final String NAME_ESCAPED_FOR_SQL = "Patrick O''Brien";
        public static final String NAME_IN_JSON = "{\"name\":\"Patrick O'Brien\",\"email\":\"patrick.obrien@example.org\"}";

        private OBrienFixture() {
        }
    }
}
