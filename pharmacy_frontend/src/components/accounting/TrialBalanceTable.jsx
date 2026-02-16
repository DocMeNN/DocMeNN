// src/components/accounting/TrialBalanceTable.jsx

import { formatMoney } from "../../utils/money";

export default function TrialBalanceTable({ accounts, totals }) {
  const rows = Array.isArray(accounts) ? accounts : [];
  const safeTotals = totals || { debit: 0, credit: 0 };

  return (
    <table className="w-full border text-sm">
      <thead className="bg-gray-50">
        <tr>
          <th className="border px-3 py-2 text-left">Code</th>
          <th className="border px-3 py-2 text-left">Account</th>
          <th className="border px-3 py-2 text-right">Debit</th>
          <th className="border px-3 py-2 text-right">Credit</th>
        </tr>
      </thead>

      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={4} className="border px-3 py-6 text-center text-gray-500">
              No ledger activity yet.
            </td>
          </tr>
        ) : (
          rows.map((a) => (
            <tr key={a.account_id}>
              <td className="border px-3 py-1">{a.account_code}</td>
              <td className="border px-3 py-1">{a.account_name}</td>
              <td className="border px-3 py-1 text-right">
                {formatMoney(a.debit)}
              </td>
              <td className="border px-3 py-1 text-right">
                {formatMoney(a.credit)}
              </td>
            </tr>
          ))
        )}
      </tbody>

      <tfoot className="bg-gray-100 font-semibold">
        <tr>
          <td colSpan="2" className="border px-3 py-2 text-right">
            Totals
          </td>
          <td className="border px-3 py-2 text-right">
            {formatMoney(safeTotals.debit)}
          </td>
          <td className="border px-3 py-2 text-right">
            {formatMoney(safeTotals.credit)}
          </td>
        </tr>
      </tfoot>
    </table>
  );
}
