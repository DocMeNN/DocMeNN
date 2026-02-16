// src/components/accounting/PrintHeader.jsx

export default function PrintHeader({ title, subtitle }) {
  return (
    <div className="mb-6 border-b pb-2">
      <h1 className="text-xl font-semibold">{title}</h1>
      {subtitle && (
        <p className="text-sm text-gray-600">{subtitle}</p>
      )}
    </div>
  );
}
