// src/components/accounting/BalanceSheetTable.jsx

import { formatMoney } from "../../utils/money";

function Section({ title, children }) {
  return (
    <div className="border rounded">
      <h3 className="px-4 py-2 font-semibold bg-gray-50 border-b">
        {title}
      </h3>
      {children}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between px-4 py-2 border-b text-sm">
      <span>{label}</span>
      <span>{formatMoney(value)}</span>
    </div>
  );
}

function TotalRow({ label, value }) {
  return (
    <div className="flex justify-between px-4 py-2 font-semibold bg-gray-100">
      <span>{label}</span>
      <span>{formatMoney(value)}</span>
    </div>
  );
}

export default function BalanceSheetTable({ data }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <Section title="Assets">
        {data.assets.accounts.map((acc) => (
          <Row
            key={acc.account_id}
            label={acc.account_name}
            value={acc.balance}
          />
        ))}
        <TotalRow label="Total Assets" value={data.assets.total} />
      </Section>

      <Section title="Liabilities & Equity">
        {data.liabilities.accounts.map((acc) => (
          <Row
            key={acc.account_id}
            label={acc.account_name}
            value={acc.balance}
          />
        ))}

        {data.equity.accounts.map((acc) => (
          <Row
            key={acc.account_id}
            label={acc.account_name}
            value={acc.balance}
          />
        ))}

        <TotalRow
          label="Total Liabilities & Equity"
          value={data.totals.liabilities_plus_equity}
        />
      </Section>
    </div>
  );
}
