// src/components/accounting/ProfitAndLossTable.jsx

import { formatMoney } from "../../utils/money";

function Section({ title, children }) {
  return (
    <div className="mb-6">
      <h3 className="font-semibold mb-2">{title}</h3>
      <div className="border rounded bg-white">{children}</div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between px-4 py-2 border-b text-sm">
      <span className="text-gray-700">{label}</span>
      <span className="font-medium">{formatMoney(value)}</span>
    </div>
  );
}

function TotalRow({ label, value }) {
  return (
    <div className="flex justify-between px-4 py-2 font-semibold bg-gray-50">
      <span>{label}</span>
      <span>{formatMoney(value)}</span>
    </div>
  );
}

function isBreakdownShape(x) {
  return (
    x &&
    typeof x === "object" &&
    Array.isArray(x.accounts) &&
    Object.prototype.hasOwnProperty.call(x, "total")
  );
}

/**
 * Supports BOTH contracts:
 *
 * 1) Summary contract (current backend):
 *    <ProfitAndLossTable income={number} expenses={number} netProfit={number} />
 *
 * 2) Future breakdown contract:
 *    <ProfitAndLossTable revenue={{accounts:[...], total}} expenses={{accounts:[...], total}} />
 */
export default function ProfitAndLossTable(props) {
  // ---- Breakdown mode (future-proof)
  if (isBreakdownShape(props.revenue) && isBreakdownShape(props.expenses)) {
    const revenue = props.revenue;
    const expenses = props.expenses;

    return (
      <>
        <Section title="Revenue">
          {revenue.accounts.map((acc) => (
            <Row
              key={acc.account_id ?? acc.code ?? acc.account_code ?? acc.account_name}
              label={acc.account_name ?? acc.name ?? "Revenue"}
              value={acc.amount ?? 0}
            />
          ))}
          <TotalRow label="Total Revenue" value={revenue.total ?? 0} />
        </Section>

        <Section title="Expenses">
          {expenses.accounts.map((acc) => (
            <Row
              key={acc.account_id ?? acc.code ?? acc.account_code ?? acc.account_name}
              label={acc.account_name ?? acc.name ?? "Expense"}
              value={acc.amount ?? 0}
            />
          ))}
          <TotalRow label="Total Expenses" value={expenses.total ?? 0} />
        </Section>
      </>
    );
  }

  // ---- Summary mode (what you need NOW)
  const income =
    props.income ?? props.revenue ?? props.total_income ?? 0;

  const expenses =
    props.expenses ?? props.total_expenses ?? 0;

  const netProfit =
    props.netProfit ?? props.net_profit ?? (Number(income) - Number(expenses)) ?? 0;

  return (
    <>
      <Section title="Revenue">
        <TotalRow label="Total Revenue" value={income} />
      </Section>

      <Section title="Expenses">
        <TotalRow label="Total Expenses" value={expenses} />
      </Section>

      <div className="border rounded bg-white">
        <TotalRow label="Net Profit" value={netProfit} />
      </div>
    </>
  );
}
