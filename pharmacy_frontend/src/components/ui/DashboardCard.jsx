// src/components/ui/DashboardCard.jsx

export default function DashboardCard({
  title,
  value,
  subtitle,
  actionLabel,
  onAction,
  highlight = false,
}) {
  return (
    <div
      className={`rounded-xl border bg-white p-5 shadow-sm transition hover:shadow-md ${
        highlight ? "border-green-500" : "border-gray-200"
      }`}
    >
      <div className="flex flex-col h-full justify-between">
        <div>
          <h3 className="text-sm font-medium text-gray-500">
            {title}
          </h3>

          {value && (
            <div className="mt-2 text-2xl font-semibold text-gray-900">
              {value}
            </div>
          )}

          {subtitle && (
            <p className="mt-1 text-sm text-gray-500">
              {subtitle}
            </p>
          )}
        </div>

        {actionLabel && onAction && (
          <button
            onClick={onAction}
            className="mt-4 inline-flex items-center justify-center rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 transition"
          >
            {actionLabel}
          </button>
        )}
      </div>
    </div>
  );
}
