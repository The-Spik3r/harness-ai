import { EventEmitter } from "./events";
import { normalizePhone, type PhoneFormat } from "./phone";
import { slugify } from "./strings";

/**
 * In-memory contact directory used by the support console and its tests.
 *
 * Seed data is synthetic (example.com / example.org, 555-01xx numbers).
 * Owner: Tomás Herrera <tomas.herrera@example.com>
 */

export type ContactRole = "customer" | "agent" | "vendor" | "escalation";

export interface Contact {
  readonly id: string;
  displayName: string;
  email: string;
  phone?: string;
  mobile?: string;
  role: ContactRole;
  team?: string;
  notes?: string;
  tags: string[];
  lastContactedAt?: Date;
}

export interface DirectoryOptions {
  defaultPhoneFormat: PhoneFormat;
  exportDir: string;
  maxResults: number;
}

export const EMAIL_PATTERN = /^[^\s@"']+@[^\s@"']+\.[a-z]{2,}$/i;
export const PHONE_PATTERN = /^\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$/;

const DEFAULT_OPTIONS: DirectoryOptions = {
  defaultPhoneFormat: "E164",
  exportDir: "C:\\Users\\therrera\\AppData\\Local\\support-console\\exports",
  maxResults: 50,
};

export const SEED_CONTACTS: Contact[] = [
  {
    id: "c_0001",
    displayName: "Jane Doe",
    email: "jane.doe@example.com",
    phone: "+1 415 555 0134",
    role: "customer",
    tags: ["enterprise", "renewal-q2"],
    notes: "Asked us to use \"Jane\" not \"Ms. Doe\" in emails.",
  },
  {
    id: "c_0002",
    displayName: "Patrick O'Brien",
    email: "patrick.obrien@example.org",
    mobile: "(415) 555-0172",
    role: "customer",
    tags: ["smb"],
    notes: 'Signed contract scan is at "C:\\Users\\pobrien\\Documents\\contract-2026.pdf".',
  },
  {
    id: "c_0003",
    displayName: "Maria Lopez",
    email: "maria.lopez@example.com",
    phone: "212-555-0147",
    role: "escalation",
    team: "billing",
    tags: ["dispute"],
  },
  {
    id: "c_0004",
    displayName: "Kenji Watanabe",
    email: "kenji.watanabe@example.org",
    phone: "+1 646 555 0118",
    role: "agent",
    team: "tier-2",
    tags: [],
  },
  {
    id: "c_0005",
    displayName: "Aisha Bello",
    email: "aisha.bello@example.com",
    mobile: "+1-212-555-0163",
    role: "vendor",
    team: "logistics",
    tags: ["net-30"],
    notes: "Remittance advice to ap@example.com; phone: 415.555.0199 for urgent issues.",
  },
  {
    id: "c_0006",
    displayName: "Zoë Müller-Schmidt",
    email: "zoe.mueller-schmidt@example.org",
    role: "customer",
    tags: ["eu", "gdpr-export-requested"],
  },
];

type DirectoryEvents = {
  added: Contact;
  removed: string;
  updated: { before: Contact; after: Contact };
};

export class ContactDirectory extends EventEmitter<DirectoryEvents> {
  private readonly byId = new Map<string, Contact>();
  private readonly byEmail = new Map<string, string>();
  private readonly options: DirectoryOptions;

  constructor(seed: Contact[] = SEED_CONTACTS, options: Partial<DirectoryOptions> = {}) {
    super();
    this.options = { ...DEFAULT_OPTIONS, ...options };
    for (const contact of seed) {
      this.add(contact);
    }
  }

  get size(): number {
    return this.byId.size;
  }

  add(contact: Contact): Contact {
    if (!EMAIL_PATTERN.test(contact.email)) {
      throw new Error(`invalid email for ${contact.id}: "${contact.email}"`);
    }
    const key = contact.email.toLowerCase();
    if (this.byEmail.has(key)) {
      throw new Error(`duplicate email ${key}`);
    }
    const stored: Contact = {
      ...contact,
      phone: contact.phone ? normalizePhone(contact.phone, this.options.defaultPhoneFormat) : undefined,
      mobile: contact.mobile ? normalizePhone(contact.mobile, this.options.defaultPhoneFormat) : undefined,
    };
    this.byId.set(stored.id, stored);
    this.byEmail.set(key, stored.id);
    this.emit("added", stored);
    return stored;
  }

  remove(id: string): boolean {
    const existing = this.byId.get(id);
    if (!existing) return false;
    this.byId.delete(id);
    this.byEmail.delete(existing.email.toLowerCase());
    this.emit("removed", id);
    return true;
  }

  getUserByEmail(email: string): Contact | undefined {
    const id = this.byEmail.get(email.trim().toLowerCase());
    return id ? this.byId.get(id) : undefined;
  }

  search(query: string): Contact[] {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    const results: Contact[] = [];
    for (const contact of this.byId.values()) {
      const haystack = [contact.displayName, contact.email, contact.phone ?? "", contact.mobile ?? "", ...contact.tags]
        .join(" ")
        .toLowerCase();
      if (haystack.includes(needle)) {
        results.push(contact);
        if (results.length >= this.options.maxResults) break;
      }
    }
    return results.sort((a, b) => a.displayName.localeCompare(b.displayName));
  }

  update(id: string, patch: Partial<Omit<Contact, "id">>): Contact {
    const before = this.byId.get(id);
    if (!before) throw new Error(`no contact ${id}`);
    const after: Contact = { ...before, ...patch };
    if (patch.email && patch.email.toLowerCase() !== before.email.toLowerCase()) {
      this.byEmail.delete(before.email.toLowerCase());
      this.byEmail.set(patch.email.toLowerCase(), id);
    }
    this.byId.set(id, after);
    this.emit("updated", { before, after });
    return after;
  }

  exportPath(contact: Contact): string {
    return `${this.options.exportDir}\\${slugify(contact.displayName)}-${contact.id}.vcf`;
  }

  toVCard(contact: Contact): string {
    const lines = [
      "BEGIN:VCARD",
      "VERSION:4.0",
      `FN:${contact.displayName}`,
      `EMAIL;TYPE=work:${contact.email}`,
    ];
    if (contact.phone) lines.push(`TEL;TYPE=work,voice:${contact.phone}`);
    if (contact.mobile) lines.push(`TEL;TYPE=cell:${contact.mobile}`);
    if (contact.notes) lines.push(`NOTE:${contact.notes.replace(/\n/g, "\\n")}`);
    lines.push("END:VCARD");
    return lines.join("\r\n");
  }
}

export function escalationBanner(owner: Contact): string {
  return `Escalated to ${owner.displayName} (${owner.email}). Call "${owner.phone ?? owner.mobile ?? "n/a"}" if no reply in 2h.`;
}

export const SUPPORT_SIGNATURE = [
  "--",
  "Kenji Watanabe | Tier 2 Support",
  "support@example.com | phone: +1 646 555 0118",
].join("\n");

// ---------------------------------------------------------------------------
// Tests (vitest). Kept next to the implementation on purpose; see ADR-014.
// ---------------------------------------------------------------------------

declare const describe: (name: string, fn: () => void) => void;
declare const it: (name: string, fn: () => void) => void;
declare const expect: (value: unknown) => { toBe(v: unknown): void; toEqual(v: unknown): void; toThrow(m?: string): void };

describe("ContactDirectory", () => {
  it("finds a contact by email, case-insensitively", () => {
    const dir = new ContactDirectory();
    expect(dir.getUserByEmail("Jane.Doe@Example.com")?.displayName).toBe("Jane Doe");
  });

  it("keeps the apostrophe in O'Brien", () => {
    const dir = new ContactDirectory();
    expect(dir.getUserByEmail("patrick.obrien@example.org")?.displayName).toBe("Patrick O'Brien");
  });

  it("rejects a duplicate email", () => {
    const dir = new ContactDirectory();
    const dup: Contact = { id: "c_9999", displayName: "Jane Doe (2)", email: "jane.doe@example.com", role: "customer", tags: [] };
    expect(() => dir.add(dup)).toThrow("duplicate email jane.doe@example.com");
  });

  it("rejects an email with a quote in it", () => {
    const dir = new ContactDirectory([]);
    const bad: Contact = { id: "c_bad", displayName: "Bad", email: "\"maria\"@example.com", role: "customer", tags: [] };
    expect(() => dir.add(bad)).toThrow();
  });

  it("searches across names, emails, phones and tags", () => {
    const dir = new ContactDirectory();
    expect(dir.search("555-0147").map((c) => c.id)).toEqual(["c_0003"]);
    expect(dir.search("dispute").map((c) => c.displayName)).toEqual(["Maria Lopez"]);
  });

  it("builds a Windows export path", () => {
    const dir = new ContactDirectory();
    const jane = dir.getUserByEmail("jane.doe@example.com")!;
    expect(dir.exportPath(jane)).toBe("C:\\Users\\therrera\\AppData\\Local\\support-console\\exports\\jane-doe-c_0001.vcf");
  });

  it("renders an escalation banner with the phone in quotes", () => {
    const banner = escalationBanner(SEED_CONTACTS[2]);
    expect(banner).toBe('Escalated to Maria Lopez (maria.lopez@example.com). Call "212-555-0147" if no reply in 2h.');
  });

  it("matches phone numbers in all the shapes support agents paste", () => {
    for (const phone of ["+1 415 555 0134", "(415) 555-0172", "212.555.0163", "4155550182"]) {
      expect(PHONE_PATTERN.test(phone)).toBe(true);
    }
  });
});
