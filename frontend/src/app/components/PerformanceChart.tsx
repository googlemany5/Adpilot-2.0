"use client";

type Item = {
  campaign_id: number;
  name: string;
  spend: number;
  revenue: number;
};

export default function PerformanceChart({ items }: { items: Item[] }) {
  const data = items.filter(
    (item) =>
      Number.isFinite(item.spend) &&
      Number.isFinite(item.revenue) &&
      (item.spend > 0 || item.revenue > 0)
  );

  const maxValue = Math.max(1, ...data.flatMap((item) => [item.spend, item.revenue]));
  const chartHeight = 190;
  const chartWidth = 640;
  const left = 42;
  const right = 12;
  const top = 14;
  const bottom = 32;
  const plotWidth = chartWidth - left - right;
  const plotHeight = chartHeight - top - bottom;
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  const compactMoney = (value: number) =>
    value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    });

  if (data.length === 0) {
    return (
      <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-white/10 bg-white/[0.02] px-6 py-10 text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-blue-400/20 bg-blue-400/10 text-xl text-blue-300">
          ↗
        </div>
        <p className="font-semibold text-slate-200">Performance data will appear here</p>
        <p className="mt-2 max-w-sm text-sm leading-6 text-slate-400">
          Once your campaigns have saved experiment spend or revenue, this chart will visualize those recorded results.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-4 text-xs text-slate-400">
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-sm bg-blue-400" />
          Recorded spend
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-sm bg-emerald-400" />
          Recorded revenue
        </span>
        <span className="ml-auto">USD · Saved experiment data</span>
      </div>

      <div className="w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          role="img"
          aria-label="Bar chart comparing recorded experiment spend and revenue by campaign"
          className="block w-full min-w-[420px]"
        >
          {ticks.map((tick) => {
            const y = top + plotHeight * (1 - tick);
            return (
              <g key={tick}>
                <line
                  x1={left}
                  y1={y}
                  x2={chartWidth - right}
                  y2={y}
                  stroke="rgba(148,163,184,0.15)"
                  strokeDasharray={tick === 0 ? "0" : "4 5"}
                />
                <text
                  x={left - 8}
                  y={y + 4}
                  textAnchor="end"
                  fill="#94a3b8"
                  fontSize="10"
                >
                  {compactMoney(maxValue * tick)}
                </text>
              </g>
            );
          })}

          {data.map((item, index) => {
            const groupWidth = plotWidth / data.length;
            const barWidth = Math.min(24, groupWidth * 0.28);
            const center = left + groupWidth * (index + 0.5);
            const spendHeight = (item.spend / maxValue) * plotHeight;
            const revenueHeight = (item.revenue / maxValue) * plotHeight;
            const label = item.name.length > 12 ? `${item.name.slice(0, 11)}…` : item.name;

            return (
              <g key={item.campaign_id}>
                <rect
                  x={center - barWidth - 2}
                  y={top + plotHeight - spendHeight}
                  width={barWidth}
                  height={Math.max(item.spend > 0 ? 2 : 0, spendHeight)}
                  rx="4"
                  fill="#60a5fa"
                >
                  <title>{item.name}: recorded spend {compactMoney(item.spend)}</title>
                </rect>
                <rect
                  x={center + 2}
                  y={top + plotHeight - revenueHeight}
                  width={barWidth}
                  height={Math.max(item.revenue > 0 ? 2 : 0, revenueHeight)}
                  rx="4"
                  fill="#34d399"
                >
                  <title>{item.name}: recorded revenue {compactMoney(item.revenue)}</title>
                </rect>
                <text
                  x={center}
                  y={chartHeight - 10}
                  textAnchor="middle"
                  fill="#94a3b8"
                  fontSize="10"
                >
                  {label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Revenue is recorded experiment revenue, not a prediction or independently verified platform-wide total.
      </p>
    </div>
  );
}
