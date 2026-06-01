import { useMemo, useState } from "react";

type ModuleId = "overview" | "customers" | "ledger" | "collections" | "aging" | "restructure" | "reports" | "admin";
type AccountStatus = "Current" | "Past Due" | "Fully Paid" | "Restructured";
type LedgerCode = "SALE" | "COL" | "INT" | "REB" | "ADJ+" | "ADJ-" | "RST";

type Account = {
  accountNo: string;
  customer: string;
  branch: string;
  area: string;
  status: AccountStatus;
  term: number;
  monthly: number;
  financed: number;
  balance: number;
  deliveryDate: string;
  dueDate: string;
  lastOr: string;
  lastUpdate: string;
};

type LedgerLine = {
  accountNo: string;
  date: string;
  ref: string;
  code: LedgerCode;
  description: string;
  debit: number;
  credit: number;
  balance: number;
};

type CollectionDraft = { orNo: string; paymentDate: string; amount: number; rebate: number; penalty: number };
type NewAccountDraft = { accountNo: string; customer: string; branch: string; area: string; financed: number; downPayment: number; term: number; deliveryDate: string };
type AuditEvent = { time: string; actor: string; action: string; detail: string };

const today = "2026-05-30";

const modules: Array<{ id: ModuleId; label: string; deck: string }> = [
  { id: "overview", label: "Workspace", deck: "Control center" },
  { id: "customers", label: "Customers", deck: "Account master" },
  { id: "ledger", label: "Ledger", deck: "AR movement" },
  { id: "collections", label: "Collections", deck: "Payment posting" },
  { id: "aging", label: "Aging", deck: "Risk buckets" },
  { id: "restructure", label: "Restructure", deck: "Loan terms" },
  { id: "reports", label: "Reports", deck: "Office exports" },
  { id: "admin", label: "Admin", deck: "Controls" }
];

const seedAccounts: Account[] = [
  { accountNo: "MMC038-002911", customer: "A. Santos Trading", branch: "MMC038", area: "Pozorrubio", status: "Current", term: 18, monthly: 5620, financed: 101160, balance: 84300, deliveryDate: "2025-12-05", dueDate: "2026-06-05", lastOr: "88421", lastUpdate: "2026-05-29" },
  { accountNo: "MMC038-003104", customer: "R. Dela Cruz", branch: "MMC038", area: "Zone 2", status: "Past Due", term: 24, monthly: 4320, financed: 103680, balance: 129600, deliveryDate: "2025-10-18", dueDate: "2026-05-18", lastOr: "88394", lastUpdate: "2026-05-20" },
  { accountNo: "MMC041-001557", customer: "M. Garcia Hardware", branch: "MMC041", area: "Central", status: "Restructured", term: 12, monthly: 7100, financed: 85200, balance: 56800, deliveryDate: "2026-01-12", dueDate: "2026-06-12", lastOr: "88409", lastUpdate: "2026-05-28" },
  { accountNo: "MMC038-001822", customer: "J. Fernandez", branch: "MMC038", area: "Zone 4", status: "Fully Paid", term: 15, monthly: 3850, financed: 57750, balance: 0, deliveryDate: "2025-02-21", dueDate: "2026-02-21", lastOr: "88102", lastUpdate: "2026-04-30" }
];

const seedLedger: LedgerLine[] = [
  { accountNo: "MMC038-002911", date: "2025-12-05", ref: "LN-002911", code: "SALE", description: "Amount financed", debit: 101160, credit: 0, balance: 101160 },
  { accountNo: "MMC038-002911", date: "2026-05-29", ref: "OR-88421", code: "COL", description: "Monthly collection", debit: 0, credit: 5620, balance: 84300 },
  { accountNo: "MMC038-003104", date: "2025-10-18", ref: "LN-003104", code: "SALE", description: "Amount financed", debit: 103680, credit: 0, balance: 103680 },
  { accountNo: "MMC038-003104", date: "2026-05-20", ref: "PEN-003104", code: "INT", description: "Past due interest and penalty", debit: 25920, credit: 0, balance: 129600 },
  { accountNo: "MMC041-001557", date: "2026-05-28", ref: "RST-001557", code: "RST", description: "Restructured remaining balance", debit: 0, credit: 28400, balance: 56800 },
  { accountNo: "MMC038-001822", date: "2026-04-30", ref: "OR-88102", code: "COL", description: "Final payment", debit: 0, credit: 3850, balance: 0 }
];

const seedAudit: AuditEvent[] = [
  { time: "2026-05-30 08:35", actor: "cashier", action: "Backup verified", detail: "SIMBackup target checked before posting" },
  { time: "2026-05-30 09:10", actor: "admin", action: "Aging report opened", detail: "Branch MMC038, all areas" }
];

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP", maximumFractionDigits: 0 }).format(value);
}

function clampMoney(value: number) {
  return Math.max(0, Math.round(Number.isFinite(value) ? value : 0));
}

function addMonths(dateValue: string, months: number) {
  const date = new Date(`${dateValue}T00:00:00`);
  date.setMonth(date.getMonth() + months);
  return date.toISOString().slice(0, 10);
}

function daysPastDue(dueDate: string) {
  return Math.max(0, Math.floor((new Date(`${today}T00:00:00`).getTime() - new Date(`${dueDate}T00:00:00`).getTime()) / 86400000));
}

function agingBucket(account: Account) {
  if (account.balance <= 0) return "Paid";
  const days = daysPastDue(account.dueDate);
  if (days === 0) return "Current";
  if (days <= 30) return "1-30D";
  if (days <= 60) return "31-60D";
  if (days <= 90) return "61-90D";
  return "90D++";
}

function statusFromBalanceAndDue(balance: number, dueDate: string, fallback: AccountStatus = "Current"): AccountStatus {
  if (balance <= 0) return "Fully Paid";
  if (fallback === "Restructured") return "Restructured";
  return daysPastDue(dueDate) > 0 ? "Past Due" : "Current";
}

function makeAudit(action: string, detail: string): AuditEvent {
  return { time: `${today} 10:${String(Math.floor(Math.random() * 50) + 10).padStart(2, "0")}`, actor: "operator", action, detail };
}

function LoanStatus({ status }: { status: AccountStatus }) {
  return <span className={`loan-status loan-status-${status.toLowerCase().replaceAll(" ", "-")}`}>{status}</span>;
}

function StatCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <section className="loan-stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </section>
  );
}

function AccountTable({ accounts, selectedAccountNo, onSelect }: { accounts: Account[]; selectedAccountNo: string; onSelect: (accountNo: string) => void }) {
  return (
    <div className="loan-table-wrap">
      <table className="loan-table account-table">
        <thead>
          <tr><th>Account No</th><th>Customer</th><th>Branch / Area</th><th>Status</th><th>Monthly</th><th>Balance</th><th>Due Date</th></tr>
        </thead>
        <tbody>
          {accounts.map((account) => (
            <tr key={account.accountNo} className={account.accountNo === selectedAccountNo ? "selected-row" : ""} onClick={() => onSelect(account.accountNo)}>
              <td><strong>{account.accountNo}</strong><small>Last OR {account.lastOr || "None"}</small></td>
              <td>{account.customer}</td>
              <td>{account.branch}<small>{account.area}</small></td>
              <td><LoanStatus status={account.status} /></td>
              <td>{formatCurrency(account.monthly)}</td>
              <td>{formatCurrency(account.balance)}</td>
              <td>{account.dueDate}<small>{agingBucket(account)}</small></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LedgerTable({ lines }: { lines: LedgerLine[] }) {
  return (
    <div className="loan-table-wrap">
      <table className="loan-table">
        <thead><tr><th>Date</th><th>Reference</th><th>Code</th><th>Description</th><th>Debit</th><th>Credit</th><th>Balance</th></tr></thead>
        <tbody>
          {lines.map((line, index) => (
            <tr key={`${line.accountNo}-${line.ref}-${index}`}>
              <td>{line.date}</td><td>{line.ref}</td><td><span className="loan-code-pill">{line.code}</span></td><td>{line.description}</td>
              <td>{line.debit ? formatCurrency(line.debit) : "-"}</td><td>{line.credit ? formatCurrency(line.credit) : "-"}</td><td>{formatCurrency(line.balance)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LoanCalculator() {
  const [amount, setAmount] = useState(98000);
  const [down, setDown] = useState(12000);
  const [term, setTerm] = useState(18);
  const [rate, setRate] = useState(0.035);
  const financed = clampMoney(amount - down);
  const interest = clampMoney(financed * rate * term);
  const loanAmount = financed + interest;
  const monthly = term > 0 ? Math.ceil(loanAmount / term) : 0;
  return (
    <section className="loan-panel calculator-panel">
      <div className="loan-panel-header compact"><h2>Loan Calculator</h2><span>Factor preview</span></div>
      <div className="loan-two-col">
        <label>Cash Price<input type="number" value={amount} onChange={(event) => setAmount(Number(event.target.value))} /></label>
        <label>Down Payment<input type="number" value={down} onChange={(event) => setDown(Number(event.target.value))} /></label>
        <label>Term<input type="number" value={term} onChange={(event) => setTerm(Number(event.target.value))} /></label>
        <label>Monthly Rate<input type="number" step="0.001" value={rate} onChange={(event) => setRate(Number(event.target.value))} /></label>
      </div>
      <dl className="loan-result-grid">
        <div><dt>Amount Financed</dt><dd>{formatCurrency(financed)}</dd></div>
        <div><dt>Interest</dt><dd>{formatCurrency(interest)}</dd></div>
        <div><dt>Monthly Due</dt><dd>{formatCurrency(monthly)}</dd></div>
      </dl>
    </section>
  );
}

function AccountDetail({ account }: { account: Account }) {
  return (
    <section className="loan-panel account-detail-panel">
      <div className="loan-panel-header compact"><h2>Selected Account</h2><LoanStatus status={account.status} /></div>
      <div className="loan-detail-grid">
        <span>Account No<strong>{account.accountNo}</strong></span>
        <span>Customer<strong>{account.customer}</strong></span>
        <span>Delivery Date<strong>{account.deliveryDate}</strong></span>
        <span>Term<strong>{account.term} months</strong></span>
        <span>Monthly<strong>{formatCurrency(account.monthly)}</strong></span>
        <span>Balance<strong>{formatCurrency(account.balance)}</strong></span>
      </div>
    </section>
  );
}

function NewAccountForm({ onCreate }: { onCreate: (draft: NewAccountDraft) => string | null }) {
  const [draft, setDraft] = useState<NewAccountDraft>({ accountNo: "MMC038-003205", customer: "", branch: "MMC038", area: "Zone 1", financed: 80000, downPayment: 10000, term: 18, deliveryDate: today });
  const [message, setMessage] = useState("");
  const update = (key: keyof NewAccountDraft, value: string | number) => setDraft((current) => ({ ...current, [key]: value }));
  return (
    <section className="loan-panel">
      <div className="loan-panel-header compact"><h2>New Account Entry</h2><span>Customer AR</span></div>
      <div className="loan-form-grid">
        <label>Account No<input value={draft.accountNo} onChange={(event) => update("accountNo", event.target.value)} /></label>
        <label>Customer<input value={draft.customer} onChange={(event) => update("customer", event.target.value)} /></label>
        <label>Branch<input value={draft.branch} onChange={(event) => update("branch", event.target.value)} /></label>
        <label>Area<input value={draft.area} onChange={(event) => update("area", event.target.value)} /></label>
        <label>Financed<input type="number" value={draft.financed} onChange={(event) => update("financed", Number(event.target.value))} /></label>
        <label>Down Payment<input type="number" value={draft.downPayment} onChange={(event) => update("downPayment", Number(event.target.value))} /></label>
        <label>Term<input type="number" value={draft.term} onChange={(event) => update("term", Number(event.target.value))} /></label>
        <label>Delivery Date<input type="date" value={draft.deliveryDate} onChange={(event) => update("deliveryDate", event.target.value)} /></label>
      </div>
      {message ? <p className="form-note">{message}</p> : null}
      <button className="loan-form-submit" onClick={() => setMessage(onCreate(draft) ?? `Created ${draft.accountNo}`)}>Create Account</button>
    </section>
  );
}

function CollectionForm({ account, draft, errors, onChange, onPost }: { account: Account; draft: CollectionDraft; errors: string[]; onChange: (draft: CollectionDraft) => void; onPost: () => void }) {
  const totalCredit = clampMoney(draft.amount + draft.rebate - draft.penalty);
  return (
    <section className="loan-panel collection-post-panel">
      <div className="loan-panel-header compact"><h2>Payment Posting</h2><span>Cashier OR</span></div>
      <div className="collection-form-grid">
        <label>OR Number<input value={draft.orNo} onChange={(event) => onChange({ ...draft, orNo: event.target.value })} /></label>
        <label>Payment Date<input type="date" value={draft.paymentDate} onChange={(event) => onChange({ ...draft, paymentDate: event.target.value })} /></label>
        <label>Amount<input type="number" value={draft.amount} onChange={(event) => onChange({ ...draft, amount: Number(event.target.value) })} /></label>
        <label>Rebate<input type="number" value={draft.rebate} onChange={(event) => onChange({ ...draft, rebate: Number(event.target.value) })} /></label>
        <label>Penalty<input type="number" value={draft.penalty} onChange={(event) => onChange({ ...draft, penalty: Number(event.target.value) })} /></label>
      </div>
      <div className="collection-summary">
        <span>Account<strong>{account.accountNo}</strong></span>
        <span>Current Balance<strong>{formatCurrency(account.balance)}</strong></span>
        <span>Ledger Credit<strong>{formatCurrency(totalCredit)}</strong></span>
        <span>New Balance<strong>{formatCurrency(Math.max(0, account.balance - totalCredit))}</strong></span>
      </div>
      {errors.length ? <ul className="loan-error-list">{errors.map((error) => <li key={error}>{error}</li>)}</ul> : null}
      <button className="collection-post-button" onClick={onPost}>Post Collection</button>
    </section>
  );
}

function AgingPanel({ accounts }: { accounts: Account[] }) {
  const rows = ["Current", "1-30D", "31-60D", "61-90D", "90D++", "Paid"].map((bucket) => {
    const bucketAccounts = accounts.filter((account) => agingBucket(account) === bucket);
    return { bucket, count: bucketAccounts.length, amount: bucketAccounts.reduce((sum, account) => sum + account.balance, 0) };
  });
  return (
    <section className="loan-panel aging-mini">
      <div className="loan-panel-header compact"><h2>Aging Buckets</h2><span>As of {today}</span></div>
      {rows.map((row, index) => (
        <div className="aging-row" key={row.bucket}>
          <i className={`aging-dot ${index > 1 ? "warn" : index === 1 ? "watch" : ""}`} />
          <span>{row.bucket}</span><em>{row.count}</em><strong>{formatCurrency(row.amount)}</strong>
        </div>
      ))}
    </section>
  );
}

function ConceptsPanel() {
  return (
    <section className="loan-panel rule-panel">
      <div className="loan-panel-header compact"><h2>Posting Rules</h2><span>Business logic</span></div>
      <ol>
        <li>Every sale opens customer AR with a debit ledger balance.</li>
        <li>Collections, rebates, and adjustments are recorded as ledger movements.</li>
        <li>Past due status is derived from due date and remaining balance.</li>
        <li>Restructure keeps the account number and records a new term trail.</li>
      </ol>
    </section>
  );
}

function RestructurePanel({ account, onApply }: { account: Account; onApply: (term: number, monthly: number) => void }) {
  const [term, setTerm] = useState(Math.max(6, account.term));
  const monthly = term > 0 ? Math.ceil(account.balance / term) : account.balance;
  return (
    <section className="loan-panel restructure-panel">
      <div className="loan-panel-header compact"><h2>Loan Restructure</h2><span>{account.accountNo}</span></div>
      <div className="restructure-grid">
        <label>Remaining Balance<input readOnly value={formatCurrency(account.balance)} /></label>
        <label>New Term<input type="number" min="1" value={term} onChange={(event) => setTerm(Number(event.target.value))} /></label>
        <label>New Monthly<input readOnly value={formatCurrency(monthly)} /></label>
      </div>
      <p className="restructure-summary">Restructure preserves customer history while updating the collection schedule and adding an RST ledger line.</p>
      <button className="loan-form-submit" onClick={() => onApply(term, monthly)}>Apply Restructure</button>
    </section>
  );
}

function ReportsPanel({ accounts, ledgerLines }: { accounts: Account[]; ledgerLines: LedgerLine[] }) {
  const totalDebit = ledgerLines.reduce((sum, line) => sum + line.debit, 0);
  const totalCredit = ledgerLines.reduce((sum, line) => sum + line.credit, 0);
  return (
    <section className="loan-panel reports-panel">
      <div className="loan-panel-header"><div><h2>Office Reports</h2><p>Recreated report launcher for customer AR, ledger, collections, aging, and summary accounting.</p></div></div>
      <div className="report-grid">
        {["Customer AR", "Ledger AR", "Collection Report", "Past Due Report", "Paid-Up Report", "Trial Balance"].map((report) => <button key={report} className="report-card">{report}<span>Preview</span></button>)}
      </div>
      <div className="collection-summary">
        <span>Total Accounts<strong>{accounts.length}</strong></span>
        <span>Ledger Debit<strong>{formatCurrency(totalDebit)}</strong></span>
        <span>Ledger Credit<strong>{formatCurrency(totalCredit)}</strong></span>
      </div>
    </section>
  );
}

function AdminPanel({ audit }: { audit: AuditEvent[] }) {
  return (
    <section className="loan-panel admin-panel">
      <div className="loan-panel-header"><div><h2>Admin Controls</h2><p>Branch setup, area codes, user access, backup, restore, and audit review.</p></div></div>
      <div className="admin-grid">
        <div className="admin-list"><strong>Security Modules</strong><span>User master</span><span>Module rights</span><span>Operator audit</span></div>
        <div className="admin-list"><strong>Maintenance</strong><span>Branches</span><span>Areas and zones</span><span>Chart of accounts</span></div>
        <div className="admin-list"><strong>Database</strong><span>Backup path: D:\SIMBackup\</span><span>MySQL connection profile</span><span>Restore validation</span></div>
      </div>
      <div className="audit-list">
        {audit.map((event) => <div className="audit-row" key={`${event.time}-${event.action}`}><strong>{event.action}</strong><span>{event.time} by {event.actor}</span><p>{event.detail}</p></div>)}
      </div>
    </section>
  );
}

function MainPanel({ module, accounts, selectedAccount, selectedLines, collectionDraft, collectionErrors, audit, onCreateAccount, onCollectionChange, onPostCollection, onRestructure, onSelect }: {
  module: ModuleId;
  accounts: Account[];
  selectedAccount: Account;
  selectedLines: LedgerLine[];
  collectionDraft: CollectionDraft;
  collectionErrors: string[];
  audit: AuditEvent[];
  onCreateAccount: (draft: NewAccountDraft) => string | null;
  onCollectionChange: (draft: CollectionDraft) => void;
  onPostCollection: () => void;
  onRestructure: (term: number, monthly: number) => void;
  onSelect: (accountNo: string) => void;
}) {
  if (module === "customers") return <div className="split-panel"><NewAccountForm onCreate={onCreateAccount} /><AccountDetail account={selectedAccount} /></div>;
  if (module === "ledger") return <section className="loan-panel loan-panel-large"><div className="loan-panel-header"><div><h2>Account Ledger</h2><p>{selectedAccount.accountNo} movement history</p></div></div><LedgerTable lines={selectedLines} /></section>;
  if (module === "collections") return <div className="collection-layout"><CollectionForm account={selectedAccount} draft={collectionDraft} errors={collectionErrors} onChange={onCollectionChange} onPost={onPostCollection} /><section className="loan-panel"><div className="loan-panel-header compact"><h2>Recent Ledger</h2><span>{selectedAccount.accountNo}</span></div><LedgerTable lines={selectedLines.slice(-5)} /></section></div>;
  if (module === "aging") return <div className="split-panel"><AgingPanel accounts={accounts} /><section className="loan-panel loan-panel-large"><div className="loan-panel-header"><div><h2>Aging Detail</h2><p>Click any account to work collection or restructure.</p></div></div><AccountTable accounts={accounts} selectedAccountNo={selectedAccount.accountNo} onSelect={onSelect} /></section></div>;
  if (module === "restructure") return <div className="split-panel"><RestructurePanel account={selectedAccount} onApply={onRestructure} /><AccountDetail account={selectedAccount} /></div>;
  if (module === "reports") return <ReportsPanel accounts={accounts} ledgerLines={selectedLines} />;
  if (module === "admin") return <AdminPanel audit={audit} />;
  return (
    <div className="loan-content-grid">
      <section className="loan-panel loan-panel-large">
        <div className="loan-panel-header"><div><h2>Customer Accounts</h2><p>Recreated office workspace based on SIMLoans modules and AR workflow.</p></div></div>
        <AccountTable accounts={accounts} selectedAccountNo={selectedAccount.accountNo} onSelect={onSelect} />
      </section>
      <aside className="loan-side-stack"><AccountDetail account={selectedAccount} /><LoanCalculator /><ConceptsPanel /></aside>
    </div>
  );
}

export function LoanOfficePage() {
  const [activeModule, setActiveModule] = useState<ModuleId>("overview");
  const [accounts, setAccounts] = useState<Account[]>(seedAccounts);
  const [ledgerLines, setLedgerLines] = useState<LedgerLine[]>(seedLedger);
  const [selectedAccountNo, setSelectedAccountNo] = useState(seedAccounts[0].accountNo);
  const [search, setSearch] = useState("");
  const [collectionDraft, setCollectionDraft] = useState<CollectionDraft>({ orNo: "88431", paymentDate: today, amount: 5620, rebate: 0, penalty: 0 });
  const [collectionErrors, setCollectionErrors] = useState<string[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>(seedAudit);

  const filteredAccounts = useMemo(() => {
    const key = search.trim().toLowerCase();
    if (!key) return accounts;
    return accounts.filter((account) => [account.accountNo, account.customer, account.branch, account.area, account.status].some((part) => part.toLowerCase().includes(key)));
  }, [accounts, search]);

  const selectedAccount = accounts.find((account) => account.accountNo === selectedAccountNo) ?? accounts[0];
  const selectedLines = ledgerLines.filter((line) => line.accountNo === selectedAccount.accountNo);
  const openBalance = accounts.reduce((sum, account) => sum + account.balance, 0);
  const pastDueCount = accounts.filter((account) => account.status === "Past Due").length;
  const monthlyDue = accounts.reduce((sum, account) => sum + (account.balance > 0 ? account.monthly : 0), 0);

  const createAccount = (draft: NewAccountDraft) => {
    if (!draft.accountNo.trim() || !draft.customer.trim()) return "Account number and customer are required.";
    if (accounts.some((account) => account.accountNo === draft.accountNo.trim())) return "Account number already exists.";
    const financed = clampMoney(draft.financed);
    const term = Math.max(1, Math.round(draft.term));
    const monthly = Math.ceil(financed / term);
    const dueDate = addMonths(draft.deliveryDate, 1);
    const account: Account = {
      accountNo: draft.accountNo.trim(),
      customer: draft.customer.trim(),
      branch: draft.branch.trim() || "MAIN",
      area: draft.area.trim() || "Unassigned",
      status: statusFromBalanceAndDue(financed, dueDate),
      term,
      monthly,
      financed,
      balance: financed,
      deliveryDate: draft.deliveryDate,
      dueDate,
      lastOr: "",
      lastUpdate: today
    };
    setAccounts((current) => [account, ...current]);
    setLedgerLines((current) => [{ accountNo: account.accountNo, date: today, ref: `LN-${account.accountNo.slice(-6)}`, code: "SALE", description: "Amount financed", debit: financed, credit: 0, balance: financed }, ...current]);
    setSelectedAccountNo(account.accountNo);
    setAudit((current) => [makeAudit("Account created", `${account.accountNo} - ${account.customer}`), ...current]);
    return null;
  };

  const validateCollection = () => {
    const errors: string[] = [];
    if (!collectionDraft.orNo.trim()) errors.push("OR number is required.");
    if (ledgerLines.some((line) => line.ref === `OR-${collectionDraft.orNo.trim()}`)) errors.push("OR number already exists.");
    if (selectedAccount.balance <= 0) errors.push("Selected account is already fully paid.");
    if (collectionDraft.amount <= 0) errors.push("Payment amount must be greater than zero.");
    if (collectionDraft.amount + collectionDraft.rebate - collectionDraft.penalty <= 0) errors.push("Ledger credit must be greater than zero.");
    return errors;
  };

  const postCollection = () => {
    const errors = validateCollection();
    setCollectionErrors(errors);
    if (errors.length) return;
    const credit = clampMoney(collectionDraft.amount + collectionDraft.rebate - collectionDraft.penalty);
    const newBalance = Math.max(0, selectedAccount.balance - credit);
    const updatedDueDate = newBalance > 0 ? addMonths(selectedAccount.dueDate, credit >= selectedAccount.monthly ? 1 : 0) : selectedAccount.dueDate;
    setAccounts((current) => current.map((account) => account.accountNo === selectedAccount.accountNo ? { ...account, balance: newBalance, dueDate: updatedDueDate, status: statusFromBalanceAndDue(newBalance, updatedDueDate, account.status), lastOr: collectionDraft.orNo.trim(), lastUpdate: collectionDraft.paymentDate } : account));
    setLedgerLines((current) => [...current, { accountNo: selectedAccount.accountNo, date: collectionDraft.paymentDate, ref: `OR-${collectionDraft.orNo.trim()}`, code: "COL", description: "Collection payment", debit: collectionDraft.penalty, credit, balance: newBalance }]);
    setAudit((current) => [makeAudit("Collection posted", `${selectedAccount.accountNo} ${formatCurrency(credit)} OR ${collectionDraft.orNo}`), ...current]);
    setCollectionDraft((current) => ({ ...current, orNo: String(Number(current.orNo) + 1), amount: selectedAccount.monthly, rebate: 0, penalty: 0 }));
  };

  const applyRestructure = (term: number, monthly: number) => {
    const nextTerm = Math.max(1, Math.round(term));
    setAccounts((current) => current.map((account) => account.accountNo === selectedAccount.accountNo ? { ...account, term: nextTerm, monthly: clampMoney(monthly), status: "Restructured", dueDate: addMonths(today, 1), lastUpdate: today } : account));
    setLedgerLines((current) => [...current, { accountNo: selectedAccount.accountNo, date: today, ref: `RST-${selectedAccount.accountNo.slice(-6)}`, code: "RST", description: `Restructure to ${nextTerm} months`, debit: 0, credit: 0, balance: selectedAccount.balance }]);
    setAudit((current) => [makeAudit("Loan restructured", `${selectedAccount.accountNo} to ${nextTerm} months`), ...current]);
  };

  return (
    <main className="loan-office-shell">
      <aside className="loan-sidebar">
        <div className="loan-brand"><span>SIM</span><strong>Loans Office</strong><small>Recreated module</small></div>
        <nav className="loan-nav">
          {modules.map((module) => <button key={module.id} className={activeModule === module.id ? "active" : ""} onClick={() => setActiveModule(module.id)}><strong>{module.label}</strong><span>{module.deck}</span></button>)}
        </nav>
        <a className="posting-link" href="#">Back to Posting App</a>
      </aside>
      <section className="loan-workspace">
        <header className="loan-topbar">
          <div><h1>{modules.find((module) => module.id === activeModule)?.label ?? "Workspace"}</h1><p>Modern office tools for customer AR, collection posting, ledger control, aging, and reports.</p></div>
          <label className="loan-search">Search accounts<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Account, customer, area" /></label>
        </header>
        <section className="loan-stat-grid">
          <StatCard label="Open AR Balance" value={formatCurrency(openBalance)} detail={`${accounts.length} accounts loaded`} />
          <StatCard label="Monthly Due" value={formatCurrency(monthlyDue)} detail="Expected active account billing" />
          <StatCard label="Past Due" value={String(pastDueCount)} detail="Accounts requiring follow-up" />
          <StatCard label="Selected Account" value={selectedAccount.accountNo} detail={selectedAccount.customer} />
        </section>
        {search.trim() ? (
          <section className="loan-account-strip"><AccountTable accounts={filteredAccounts} selectedAccountNo={selectedAccount.accountNo} onSelect={setSelectedAccountNo} /></section>
        ) : null}
        <MainPanel module={activeModule} accounts={filteredAccounts} selectedAccount={selectedAccount} selectedLines={selectedLines} collectionDraft={collectionDraft} collectionErrors={collectionErrors} audit={audit} onCreateAccount={createAccount} onCollectionChange={setCollectionDraft} onPostCollection={postCollection} onRestructure={applyRestructure} onSelect={setSelectedAccountNo} />
      </section>
    </main>
  );
}
