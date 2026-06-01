import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Clock3,
  FolderClock,
  KeyRound,
  Landmark,
  LogOut,
  Plus,
  ReceiptText,
  Search,
  UserPlus,
  WalletCards
} from "lucide-react";

type Screen = "login" | "landing" | "collection" | "ledger" | "payment-detail" | "payment-create";

type CollectionRow = {
  id: string;
  accountNo: string;
  accountName: string;
  date: string;
  code: "OR" | "UPD" | "PEN" | "DEP";
  reference: string;
  interest: number;
  amount: number;
  rebate: number;
  total: number;
  balance: number;
  intPaid: number;
  vat: number;
};

type LedgerLine = {
  id: string;
  date: string;
  inst: number;
  code: "OR" | "UPD" | "PEN";
  reference: string;
  penalty: number;
  due: number;
  payment: number;
  rebate: number;
  overdue: number;
  debit: number;
  credit: number;
  balance: number;
};

const currentOperator = "LERO, NORIEL DELA CRUZ";

const collectionRows: CollectionRow[] = [
  { id: "c1", accountNo: "0001200826006563", accountName: "OTHER PAYMENTS / MMC074-TAYUG", date: "05/30/2026", code: "OR", reference: "13514", interest: 0, amount: 4500, rebate: 0, total: 4500, balance: 922215, intPaid: 0, vat: 0 },
  { id: "c2", accountNo: "0001251124015447", accountName: "MMC075-00501R / JAYLOUS MAR", date: "05/30/2026", code: "OR", reference: "5558 - (7/12", interest: 0, amount: 114, rebate: 0, total: 114, balance: 11320, intPaid: 0, vat: 0 },
  { id: "c3", accountNo: "0001250411014815", accountName: "MMC075-00478 / SOLEDAD MANZON", date: "05/30/2026", code: "OR", reference: "5556 -", interest: 0, amount: 2380, rebate: 300, total: 2680, balance: 26800, intPaid: 930, vat: 99.64 },
  { id: "c4", accountNo: "0001250127014472", accountName: "MMC074-00841R / LEOMARLYN ALCAIDE DISTOR", date: "05/30/2026", code: "OR", reference: "13513 -", interest: 0, amount: 2107, rebate: 0, total: 2107, balance: 23148, intPaid: 747, vat: 80.04 },
  { id: "c5", accountNo: "0001250429014875", accountName: "MMC070-00894 / THERSO ABANAG DAYAO", date: "05/30/2026", code: "OR", reference: "11272 -", interest: 0, amount: 5979, rebate: 0, total: 5979, balance: 37050, intPaid: 2045.45, vat: 219.16 },
  { id: "c6", accountNo: "0001231220012841", accountName: "MMC039-01160 / JIJI MAMARIL", date: "05/30/2026", code: "OR", reference: "17447 -", interest: 0, amount: 1185, rebate: 0, total: 1185, balance: 18836, intPaid: 525.73, vat: 56.33 }
];

const ledgerLines: LedgerLine[] = [
  { id: "l1", date: "03/10/2026", inst: 11, code: "UPD", reference: "11", penalty: 0, due: 2850, payment: 0, rebate: 0, overdue: 8550, debit: 0, credit: 0, balance: 45600 },
  { id: "l2", date: "04/10/2026", inst: 12, code: "UPD", reference: "12", penalty: 0, due: 2850, payment: 0, rebate: 0, overdue: 11400, debit: 0, credit: 0, balance: 45600 },
  { id: "l3", date: "04/13/2026", inst: 12, code: "PEN", reference: "10786 - (9/24", penalty: 0, due: 0, payment: 0, rebate: 0, overdue: 11400, debit: 429, credit: 0, balance: 46029 },
  { id: "l4", date: "04/13/2026", inst: 8, code: "OR", reference: "10786 - (9/24 MI", penalty: 0, due: 0, payment: 2571, rebate: 0, overdue: 8829, debit: 0, credit: 2571, balance: 43458 },
  { id: "l5", date: "05/10/2026", inst: 13, code: "UPD", reference: "13", penalty: 0, due: 2850, payment: 0, rebate: 0, overdue: 11679, debit: 0, credit: 0, balance: 43029 },
  { id: "l6", date: "05/30/2026", inst: 13, code: "PEN", reference: "11272 - (9-11/24", penalty: 0, due: 0, payment: 0, rebate: 0, overdue: 11679, debit: 715, credit: 0, balance: 43744 },
  { id: "l7", date: "05/30/2026", inst: 11, code: "OR", reference: "11272 - (9-11/24", penalty: 0, due: 0, payment: 5979, rebate: 0, overdue: 5700, debit: 0, credit: 5979, balance: 37765 },
  { id: "l8", date: "05/30/2026", inst: 13, code: "OR", reference: "11272 - (9-11/24", penalty: 0, due: 0, payment: 0, rebate: 0, overdue: 5700, debit: 0, credit: 715, balance: 37050 }
];

const focusedAccount = {
  accountNo: "1250429014875",
  name: "MMC070-00894 / THERSO ABANAG DAYAO",
  address: "PUROK 5 SAGUNTO SISON PANGASINAN",
  area: "POZORRUBIO, PANGASINAN",
  type: "MC",
  className: "CURRENT",
  invoiceDate: "4/10/2025",
  term: 24,
  monthly: 2850,
  rebate: 300,
  lcp: 48000,
  downPayment: 3000,
  remaining: "11 month(s) remaining"
};

function money(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function ModernTitleBar({ title, onLogout }: { title: string; onLogout?: () => void }) {
  return (
    <header className="simv3-window-title">
      <div><Landmark size={16} /><strong>{title}</strong></div>
      <span>MICROBASE_Branch7</span>
      {onLogout ? <button type="button" onClick={onLogout}><LogOut size={15} /> Logout</button> : null}
    </header>
  );
}

function MenuBar() {
  return (
    <nav className="simv3-menu">
      {["File", "Transaction", "Maintenance", "Reports", "Inventory", "Documents", "Accounting", "Audit", "Tools", "Setup", "Administration", "Help", "About"].map((item) => <button key={item} type="button">{item}</button>)}
    </nav>
  );
}

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  return (
    <main className="simv3-login-screen">
      <ModernTitleBar title="SIMLoans V3" />
      <section className="simv3-login-card">
        <div className="simv3-login-brand">
          <Landmark size={42} />
          <div><h1>SIMLoans V3</h1><p>Modern loan servicing and collection workspace</p></div>
        </div>
        <label>Area / Branch<select defaultValue="MICROBASE_Branch7"><option>MICROBASE_Branch7</option><option>MICROBASE_Main</option><option>MMC-ZUH</option></select></label>
        <label>Username<input defaultValue="LERO, NORIEL DELA CRUZ" /></label>
        <label>Password<input type="password" placeholder="Enter password" /></label>
        <button type="button" onClick={onLogin}><KeyRound size={18} /> Login</button>
      </section>
    </main>
  );
}

function SummaryPanel({ title, rows }: { title: string; rows: Array<[string, string]> }) {
  return (
    <section className="simv3-summary-panel">
      <h3>{title}</h3>
      <table><tbody>{rows.map(([label, value]) => <tr key={label}><td>{label}</td><td>{value}</td></tr>)}</tbody></table>
    </section>
  );
}

function LandingScreen({ onOpen }: { onOpen: (screen: Screen) => void }) {
  const actions = [
    { label: "Customer", icon: UserPlus, screen: "ledger" as Screen },
    { label: "Ledger", icon: WalletCards, screen: "ledger" as Screen },
    { label: "Collection", icon: ReceiptText, screen: "collection" as Screen },
    { label: "Matured Accounts", icon: FolderClock, screen: "collection" as Screen },
    { label: "Aging", icon: Clock3, screen: "collection" as Screen }
  ];
  return (
    <main className="simv3-desktop">
      <ModernTitleBar title="SIMLoans V3" onLogout={() => onOpen("login")} />
      <MenuBar />
      <section className="simv3-landing-head">
        <div><h1>MICROBASE_Branch7</h1><p>{currentOperator}</p></div>
        <div className="simv3-landing-filters"><select defaultValue="MICROBASE_Branch7"><option>MICROBASE_Branch7</option></select><input placeholder="Quick search" /><button type="button"><Search size={16} /></button></div>
      </section>
      <section className="simv3-summary-grid">
        <SummaryPanel title="Classification" rows={[["CASH", "1,856"], ["CURRENT", "1,748"], ["ERROR", "360"], ["FULLY PAID", "5,403"]]} />
        <SummaryPanel title="Transactions 2015-09-02" rows={[["OR", "31,031"], ["UPD", "0"], ["PEN", "3,231"], ["DEP", "0"]]} />
        <SummaryPanel title="Zone" rows={[["Total", "16,108"]]} />
      </section>
      <section className="simv3-module-row">
        {actions.map((action) => {
          const Icon = action.icon;
          return <button type="button" key={action.label} onClick={() => onOpen(action.screen)}><Icon size={56} /><span>{action.label}</span></button>;
        })}
      </section>
      <footer className="simv3-brand-footer"><span>MICROBASE MOTORBIKE CORPORATION</span><strong>Simsoft</strong></footer>
    </main>
  );
}

function CollectionScreen({ onOpenLedger, onBack }: { onOpenLedger: (row: CollectionRow) => void; onBack: () => void }) {
  const totals = useMemo(() => collectionRows.reduce((sum, row) => sum + row.total, 0), []);
  return (
    <main className="simv3-module-screen">
      <ModernTitleBar title="Collection Report" />
      <div className="simv3-module-toolbar">
        <button type="button" onClick={onBack}>Home</button><button type="button">View</button><button type="button">Print</button>
        <label><input type="checkbox" defaultChecked /> Quicksearch</label><input placeholder="Search collection" /><button type="button"><Search size={16} /></button>
      </div>
      <div className="simv3-filter-row">
        <select defaultValue="Select Area"><option>Select Area</option><option>POZORRUBIO</option></select>
        <select defaultValue="Select Zone"><option>Select Zone</option></select>
        <select defaultValue="Select Class"><option>Select Class</option><option>CURRENT</option></select>
        <select defaultValue="Select Transaction Code"><option>Select Transaction Code</option><option>OFFICIAL RECEIPT</option></select>
        <input type="date" defaultValue="2026-05-30" />
      </div>
      <div className="simv3-grid-wrap">
        <table className="simv3-data-grid">
          <thead><tr><th /><th>Account No.</th><th>Account Name</th><th>Date</th><th>Code</th><th>Reference</th><th>Interest</th><th>Amount</th><th>Rebate</th><th>Total</th><th>Balance</th><th>IntPaid</th><th>VAT</th></tr></thead>
          <tbody>{collectionRows.map((row) => <tr key={row.id} onDoubleClick={() => onOpenLedger(row)} onClick={() => onOpenLedger(row)}><td><input type="checkbox" readOnly checked={row.id === "c5"} /></td><td>{row.accountNo}</td><td>{row.accountName}</td><td>{row.date}</td><td>{row.code}</td><td>{row.reference}</td><td>{money(row.interest)}</td><td>{money(row.amount)}</td><td>{money(row.rebate)}</td><td><strong>{money(row.total)}</strong></td><td>{money(row.balance)}</td><td>{money(row.intPaid)}</td><td>{money(row.vat)}</td></tr>)}</tbody>
          <tfoot><tr><td colSpan={9}>{collectionRows.length} rows</td><td>{money(totals)}</td><td colSpan={3}>1,243,857</td></tr></tfoot>
        </table>
      </div>
      <footer className="simv3-grid-status"><span>CAPS</span><span>ID 14472 @trx_ledger</span><strong>100%</strong><button type="button">Post To GL</button></footer>
    </main>
  );
}

function AccountHeader() {
  return (
    <section className="simv3-account-header">
      <label>Account No.<input readOnly value={focusedAccount.accountNo} /></label>
      <label className="wide">Customer<input readOnly value={focusedAccount.name} /></label>
      <label className="wide">Address<input readOnly value={focusedAccount.address} /></label>
      <label>Area<input readOnly value={focusedAccount.area} /></label>
      <label>Type<input readOnly value={focusedAccount.type} /></label>
      <label>Class<input readOnly value={focusedAccount.className} /></label>
      <label>Invoice Date<input readOnly value={focusedAccount.invoiceDate} /></label>
      <label>Term<input readOnly value={focusedAccount.term} /></label>
      <label>Monthly<input readOnly value={money(focusedAccount.monthly)} /></label>
      <label>Rebate<input readOnly value={money(focusedAccount.rebate)} /></label>
      <label>LCP<input readOnly value={money(focusedAccount.lcp)} /></label>
      <label>Down Payment<input readOnly value={money(focusedAccount.downPayment)} /></label>
    </section>
  );
}

function LedgerScreen({ onBack, onPaymentDetail, onCreatePayment }: { onBack: () => void; onPaymentDetail: (line: LedgerLine) => void; onCreatePayment: () => void }) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        onCreatePayment();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCreatePayment]);

  return (
    <main className="simv3-module-screen">
      <ModernTitleBar title={focusedAccount.name} />
      <section className="simv3-ledger-shell">
        <AccountHeader />
        <div className="simv3-ledger-tools"><button type="button" onClick={onBack}>Back</button><select><option>Select Transaction Code</option></select><label><input type="checkbox" /> Detailed Ledger</label><strong>{focusedAccount.remaining}</strong><button type="button"><Search size={16} /></button></div>
        <div className="simv3-grid-wrap">
          <table className="simv3-data-grid">
            <thead><tr><th /><th>Date</th><th>INST</th><th>CODE</th><th>Reference</th><th>Penalty</th><th>Due</th><th>Payment</th><th>Rebate</th><th>Overdue</th><th>Debit</th><th>Credit</th><th>Balance</th></tr></thead>
            <tbody>{ledgerLines.map((line) => <tr key={line.id} onClick={() => line.code === "OR" ? onPaymentDetail(line) : undefined}><td><input type="checkbox" readOnly checked={line.id === "l8"} /></td><td>{line.date}</td><td className={line.code === "UPD" ? "danger-text" : ""}>{line.inst}</td><td className={line.code === "UPD" ? "danger-text" : ""}>{line.code}</td><td>{line.reference}</td><td>{money(line.penalty)}</td><td>{money(line.due)}</td><td>{money(line.payment)}</td><td>{money(line.rebate)}</td><td className="danger-text">{money(line.overdue)}</td><td>{money(line.debit)}</td><td>{money(line.credit)}</td><td>{money(line.balance)}</td></tr>)}</tbody>
            <tfoot><tr><td colSpan={2}>30 rows</td><td>13</td><td colSpan={3}>0</td><td>37,050</td><td>29,550</td><td>1,800</td><td>5,700</td><td>72,687</td><td>35,637</td><td>37,050</td></tr></tfoot>
          </table>
        </div>
        <footer className="simv3-actionbar"><span>Ctrl + N creates payment</span><button type="button" onClick={onCreatePayment}><Plus size={16} /> New</button><button type="button">Print</button><button type="button">Reports</button></footer>
      </section>
    </main>
  );
}

function PaymentForm({ mode, onBack }: { mode: "detail" | "create"; onBack: () => void }) {
  const isCreate = mode === "create";
  return (
    <main className="simv3-module-screen">
      <ModernTitleBar title={isCreate ? "Transaction: Ledger Update" : "11272 - (9-11/24 MI)"} />
      <section className="simv3-payment-form">
        <div className="simv3-form-topline"><select defaultValue="CASH INVOICE"><option>CASH INVOICE</option></select><select defaultValue={isCreate ? "C451B15A" : "D0E0AA29"}><option>D0E0AA29</option><option>C451B15A</option></select><input readOnly value={isCreate ? "0000000193" : "0000002549"} /></div>
        <AccountHeader />
        <div className="simv3-payment-body">
          <section className="simv3-payment-fields">
            <label>Date<input type="date" defaultValue="2026-05-30" /></label>
            <label>Trans Code<select defaultValue="OFFICIAL RECEIPT"><option>OFFICIAL RECEIPT</option></select></label>
            <label>Reference<input defaultValue={isCreate ? "" : "11272 - (9-11/24 MI)"} /></label>
            <label>Due<input defaultValue={isCreate ? "0" : "0"} /></label>
            <label>Payment<input defaultValue={isCreate ? "0" : "5,979"} /></label>
            <label>Rebate<input defaultValue="0" /></label>
            <label>Debit<input defaultValue="0" /></label>
            <label>Credit<input defaultValue={isCreate ? "0" : "5,979"} /></label>
          </section>
          <section className="simv3-overdue-card">
            <table><thead><tr><th /><th>Date</th><th>Overdue</th></tr></thead><tbody><tr><td><input type="checkbox" /></td><td>2026-04-10</td><td>2,850</td></tr><tr><td><input type="checkbox" defaultChecked /></td><td>2026-05-10</td><td>2,850</td></tr></tbody><tfoot><tr><td colSpan={2}>2 rows</td><td>5,700</td></tr></tfoot></table>
          </section>
        </div>
        <label className="simv3-remarks">Remarks<textarea defaultValue={isCreate ? "" : "9 - FULL JAN 2026 W/PEN ; 10 - FULL FEB 2026 W/ PEN ; 11 - FULL MAR 2026 W/PEN - 0930-202-5280"} /></label>
        <footer className="simv3-actionbar"><button type="button" onClick={onBack}>Back</button><button type="button">Print</button><button type="button"><Check size={16} /> Save</button></footer>
      </section>
    </main>
  );
}

export function SimLoansModernFlowPage() {
  const [screen, setScreen] = useState<Screen>("login");
  const [selectedPayment, setSelectedPayment] = useState<LedgerLine | null>(null);

  const openPayment = (line: LedgerLine) => {
    setSelectedPayment(line);
    setScreen("payment-detail");
  };

  if (screen === "login") return <LoginScreen onLogin={() => setScreen("landing")} />;
  if (screen === "landing") return <LandingScreen onOpen={setScreen} />;
  if (screen === "collection") return <CollectionScreen onBack={() => setScreen("landing")} onOpenLedger={() => setScreen("ledger")} />;
  if (screen === "ledger") return <LedgerScreen onBack={() => setScreen("collection")} onPaymentDetail={openPayment} onCreatePayment={() => setScreen("payment-create")} />;
  if (screen === "payment-create") return <PaymentForm mode="create" onBack={() => setScreen("ledger")} />;
  return <PaymentForm mode={selectedPayment ? "detail" : "detail"} onBack={() => setScreen("ledger")} />;
}
