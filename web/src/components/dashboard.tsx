"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  CircleDot,
  Clock3,
  Coins,
  Gauge,
  LayoutDashboard,
  LineChart,
  ListOrdered,
  Radio,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { compactMoney, duration, money, percent, shortPair, timeAgo } from "@/lib/format";
import type { DashboardData, EquityPoint, OpenTrade } from "@/lib/types";

const NAV = [
  { href: "#overview", label: "Overview", icon: LayoutDashboard },
  { href: "#positions", label: "Positions", icon: ListOrdered },
  { href: "#performance", label: "Performance", icon: BarChart3 },
  { href: "#activity", label: "Activity", icon: Activity },
  { href: "#strategy", label: "Strategy", icon: ShieldCheck },
];

const tooltipStyle = {
  background: "#0b111a",
  border: "1px solid #243247",
  borderRadius: 12,
  color: "#eef4fb",
  fontSize: 12,
  boxShadow: "0 18px 50px -20px rgba(0,0,0,.9)",
};

function StatCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: ReactNode;
  icon: ComponentType<{ className?: string }>;
  tone?: "positive" | "negative" | "neutral";
}) {
  const toneClass =
    tone === "positive"
      ? "text-positive"
      : tone === "negative"
        ? "text-negative"
        : "text-ink";
  return (
    <div className="card card-hover p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
          {label}
        </p>
        <span className="grid size-9 place-items-center rounded-xl border border-line bg-panel-2 text-muted">
          <Icon className="size-4" />
        </span>
      </div>
      <p className={`mono mt-4 text-[26px] leading-none tracking-tight ${toneClass}`}>
        {value}
      </p>
      <div className="mt-3 text-xs text-muted">{detail}</div>
    </div>
  );
}

function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "positive" | "negative" | "warning" | "accent" | "neutral";
}) {
  const classes = {
    positive: "border-positive/25 bg-positive/10 text-positive",
    negative: "border-negative/25 bg-negative/10 text-negative",
    warning: "border-warning/25 bg-warning/10 text-warning",
    accent: "border-accent/25 bg-accent/10 text-accent",
    neutral: "border-line bg-panel-2 text-muted",
  }[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${classes}`}
    >
      {children}
    </span>
  );
}

function EquityTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number | string; payload?: EquityPoint }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  return (
    <div className="rounded-xl border border-line bg-panel px-3 py-2 shadow-2xl">
      <p className="text-[10px] uppercase tracking-wider text-muted">
        {point?.date ? new Date(point.date).toLocaleDateString() : label}
      </p>
      <p className="mono mt-1 text-sm text-ink">
        {money(Number(payload[0]?.value ?? 0))}
      </p>
      {point ? (
        <p
          className={`mono mt-0.5 text-[11px] ${
            point.pnl >= 0 ? "text-positive" : "text-negative"
          }`}
        >
          {percent((point.pnl / Math.max(1, point.equity - point.pnl)) * 100)}
        </p>
      ) : null}
    </div>
  );
}

function ChartCard({
  title,
  description,
  children,
  action,
  className = "",
}: {
  title: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-5 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-ink">{title}</h2>
          {description ? (
            <p className="mt-1 text-xs text-muted">{description}</p>
          ) : null}
        </div>
        {action}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function Sidebar({ data }: { data: DashboardData }) {
  const slots = Math.max(0, data.config.maxOpenTrades - data.summary.openTrades);
  return (
    <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-line bg-canvas/80 px-4 py-5 backdrop-blur lg:flex">
      <div className="flex items-center gap-3 px-2">
        <div className="grid size-10 place-items-center rounded-2xl border border-accent/30 bg-accent/10 text-accent shadow-[0_0_28px_-8px_rgba(110,168,255,.65)]">
          <Bot className="size-5" />
        </div>
        <div>
          <p className="text-sm font-semibold tracking-tight">NFI / X9</p>
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted">
            Command center
          </p>
        </div>
      </div>

      <nav className="mt-8 space-y-1">
        {NAV.map(({ href, label, icon: Icon }, index) => (
          <a
            key={href}
            href={href}
            className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${
              index === 0
                ? "bg-panel-2 text-ink"
                : "text-muted hover:bg-panel-2/70 hover:text-ink"
            }`}
          >
            <Icon className="size-4" />
            {label}
          </a>
        ))}
      </nav>

      <div className="mt-auto space-y-3">
        <div className="rounded-2xl border border-line bg-panel p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-[0.16em] text-muted">
              Open capacity
            </span>
            <span className="mono text-xs text-ink">
              {data.summary.openTrades}/{data.config.maxOpenTrades || "—"}
            </span>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-panel-2">
            <div
              className="h-full rounded-full bg-gradient-to-r from-accent to-positive"
              style={{
                width: `${Math.min(
                  100,
                  (data.summary.openTrades /
                    Math.max(1, data.config.maxOpenTrades)) *
                    100,
                )}%`,
              }}
            />
          </div>
          <p className="mt-2 text-[11px] text-muted">
            {slots} slot{slots === 1 ? "" : "s"} available
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-xl border border-line bg-panel px-3 py-2.5 text-xs text-muted">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-positive opacity-50" />
            <span className="relative inline-flex size-2 rounded-full bg-positive" />
          </span>
          <span className="truncate">
            {data.mode === "live" ? "Connected to bot" : "Demo dataset"}
          </span>
          <Radio className="ml-auto size-3.5" />
        </div>
      </div>
    </aside>
  );
}

function PositionsTable({ trades }: { trades: OpenTrade[] }) {
  if (trades.length === 0) {
    return (
      <div className="grid min-h-40 place-items-center rounded-2xl border border-dashed border-line bg-panel-2/40 text-center">
        <div>
          <Target className="mx-auto size-6 text-muted" />
          <p className="mt-2 text-sm text-ink">No open positions</p>
          <p className="mt-1 text-xs text-muted">
            The strategy is waiting for a qualified entry.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line text-[10px] uppercase tracking-[0.14em] text-muted">
            <th className="pb-3 font-medium">Market</th>
            <th className="pb-3 font-medium">Side</th>
            <th className="hidden pb-3 text-right font-medium sm:table-cell">
              Entry
            </th>
            <th className="hidden pb-3 text-right font-medium sm:table-cell">
              Mark
            </th>
            <th className="pb-3 text-right font-medium">P/L</th>
            <th className="pb-3 text-right font-medium">Age</th>
            <th className="hidden pb-3 text-right font-medium md:table-cell">
              Signal
            </th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => {
            const pnl = trade.profit_abs;
            return (
              <tr
                key={trade.trade_id}
                className="border-b border-line/60 last:border-0"
              >
                <td className="py-3.5 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="grid size-7 place-items-center rounded-lg bg-panel-2 text-[10px] font-semibold text-accent">
                      {shortPair(trade.pair).slice(0, 2)}
                    </span>
                    <span className="font-medium text-ink">
                      {shortPair(trade.pair)}
                    </span>
                    <span className="text-[10px] text-muted">
                      {trade.leverage}x
                    </span>
                  </div>
                </td>
                <td className="py-3.5 pr-4">
                  <Badge tone={trade.is_short ? "negative" : "positive"}>
                    {trade.is_short ? (
                      <ArrowDownRight className="size-3" />
                    ) : (
                      <ArrowUpRight className="size-3" />
                    )}
                    {trade.is_short ? "Short" : "Long"}
                  </Badge>
                </td>
                <td className="mono hidden py-3.5 pr-4 text-right text-muted sm:table-cell">
                  {trade.open_rate.toFixed(4)}
                </td>
                <td className="mono hidden py-3.5 pr-4 text-right text-ink sm:table-cell">
                  {trade.current_rate.toFixed(4)}
                </td>
                <td
                  className={`mono py-3.5 pr-4 text-right font-medium ${
                    pnl >= 0 ? "text-positive" : "text-negative"
                  }`}
                >
                  {money(pnl)}
                  <span className="ml-2 text-[10px] opacity-70">
                    {percent(trade.profit_ratio * 100)}
                  </span>
                </td>
                <td className="mono py-3.5 pr-4 text-right text-muted">
                  {timeAgo(trade.open_date).replace(" ago", "")}
                </td>
                <td className="hidden py-3.5 text-right md:table-cell">
                  <span className="rounded-md border border-line bg-panel-2 px-2 py-1 text-[10px] text-muted">
                    {trade.enter_tag}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function LoadingScreen({ error, onRetry }: { error?: string; onRetry: () => void }) {
  return (
    <div className="grid min-h-screen place-items-center px-6">
      <div className="card w-full max-w-md p-8 text-center">
        <div className="mx-auto grid size-12 place-items-center rounded-2xl border border-accent/30 bg-accent/10 text-accent">
          {error ? (
            <AlertTriangle className="size-5" />
          ) : (
            <Sparkles className="size-5 animate-pulse" />
          )}
        </div>
        <h1 className="mt-5 text-lg font-semibold">
          {error ? "Could not reach the dashboard" : "Waking up the desk"}
        </h1>
        <p className="mt-2 text-sm text-muted">
          {error ??
            "Loading equity, open risk and the latest X9 execution context."}
        </p>
        {error ? (
          <button
            onClick={onRetry}
            className="mt-6 inline-flex items-center gap-2 rounded-xl border border-line bg-panel-2 px-4 py-2 text-sm text-ink transition hover:border-accent/50"
          >
            <RefreshCw className="size-4" />
            Retry connection
          </button>
        ) : (
          <div className="mt-6 h-1 overflow-hidden rounded-full bg-panel-2">
            <div className="h-full w-1/2 animate-pulse rounded-full bg-accent" />
          </div>
        )}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store" });
      const payload = (await response.json()) as
        | DashboardData
        | { error?: string };
      if (!response.ok) {
        throw new Error(
          "error" in payload && payload.error
            ? payload.error
            : `Dashboard API answered ${response.status}`,
        );
      }
      setData(payload as DashboardData);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unknown error");
    }
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  useEffect(() => {
    // Initial hydration of external bot state; the state write happens after
    // the fetch resolves, not synchronously in the effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const interval = window.setInterval(() => void load(), 20_000);
    return () => window.clearInterval(interval);
  }, [load]);

  if (!data) {
    return <LoadingScreen error={error ?? undefined} onRetry={refresh} />;
  }

  const { summary, config } = data;
  const positive = summary.netPnl >= 0;
  const openStake = data.openTrades.reduce(
    (sum, trade) => sum + trade.stake_amount,
    0,
  );

  return (
    <div className="lg:grid lg:grid-cols-[248px_1fr]">
      <Sidebar data={data} />

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-line bg-canvas/80 px-5 py-3 backdrop-blur-xl lg:px-8">
          <div className="mx-auto flex max-w-[1440px] items-center gap-3">
            <div className="flex items-center gap-2 lg:hidden">
              <div className="grid size-9 place-items-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
                <Bot className="size-4" />
              </div>
              <span className="text-sm font-semibold">NFI / X9</span>
            </div>
            <div className="hidden items-center gap-2 text-xs text-muted lg:flex">
              <span>Strategy</span>
              <span className="text-line">/</span>
              <span className="text-ink">Command center</span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <Badge tone={data.mode === "live" ? "positive" : "warning"}>
                <span
                  className={`size-1.5 rounded-full ${
                    data.mode === "live"
                      ? "live-dot bg-positive"
                      : "bg-warning"
                  }`}
                />
                {data.mode === "live" ? "Live" : "Demo"}
              </Badge>
              <span className="hidden text-[11px] text-muted sm:inline">
                {timeAgo(data.generatedAt)}
              </span>
              <button
                onClick={() => void refresh()}
                className="grid size-9 place-items-center rounded-xl border border-line bg-panel text-muted transition hover:border-accent/50 hover:text-ink"
                aria-label="Refresh dashboard"
              >
                <RefreshCw
                  className={`size-4 ${refreshing ? "animate-spin" : ""}`}
                />
              </button>
            </div>
          </div>
          <nav className="mx-auto mt-3 flex max-w-[1440px] gap-1 overflow-x-auto lg:hidden">
            {NAV.map(({ href, label, icon: Icon }) => (
              <a
                key={href}
                href={href}
                className="flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] text-muted transition hover:bg-panel-2 hover:text-ink"
              >
                <Icon className="size-3.5" />
                {label}
              </a>
            ))}
          </nav>
        </header>

        <main className="mx-auto max-w-[1440px] px-5 py-7 lg:px-8 lg:py-10">
          <section id="overview" className="scroll-mt-24">
            <div className="flex flex-wrap items-end justify-between gap-5">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="accent">
                    <Zap className="size-3" />
                    X9 engine
                  </Badge>
                  <Badge>{config.timeframe} timeframe</Badge>
                  <Badge>{config.tradingMode}</Badge>
                  {config.dryRun ? <Badge tone="warning">Dry run</Badge> : null}
                </div>
                <h1 className="mt-4 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
                  Command center
                </h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
                  Live exposure, execution quality and pair-level attribution for{" "}
                  <span className="text-ink">{config.strategy}</span>. Read-only,
                  credential-free UI.
                </p>
              </div>
              <div className="flex items-center gap-3 rounded-2xl border border-line bg-panel/70 px-4 py-3">
                <div className="grid size-9 place-items-center rounded-xl bg-positive/10 text-positive">
                  <Wallet className="size-4" />
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.14em] text-muted">
                    Equity
                  </p>
                  <p className="mono text-lg leading-tight text-ink">
                    {money(summary.equity)}
                  </p>
                </div>
                <div
                  className={`mono ml-2 text-xs ${
                    positive ? "text-positive" : "text-negative"
                  }`}
                >
                  {percent(summary.netPnlPct)}
                </div>
              </div>
            </div>

            {data.errors?.length ? (
              <div className="mt-5 flex items-start gap-2 rounded-xl border border-warning/20 bg-warning/5 px-3 py-2.5 text-xs text-warning">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <span>
                  Partial data: {data.errors.join(" · ")}
                </span>
              </div>
            ) : null}

            <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                label="Net P/L"
                value={money(summary.netPnl)}
                tone={positive ? "positive" : "negative"}
                icon={TrendingUp}
                detail={
                  <span>
                    Realized{" "}
                    <span className="mono text-ink">{money(summary.realizedPnl)}</span>
                    <span className="mx-1.5 text-line">·</span>
                    Open{" "}
                    <span className="mono text-ink">
                      {money(summary.unrealizedPnl)}
                    </span>
                  </span>
                }
              />
              <StatCard
                label="Win rate"
                value={`${summary.winRate.toFixed(1)}%`}
                icon={Target}
                detail={
                  <span>
                    <span className="text-positive">{summary.winners} wins</span>
                    <span className="mx-1.5 text-line">·</span>
                    <span className="text-negative">{summary.losers} losses</span>
                    <span className="mx-1.5 text-line">·</span>
                    {summary.closedTrades} closed
                  </span>
                }
              />
              <StatCard
                label="Open risk"
                value={`${summary.openTrades}`}
                icon={Gauge}
                detail={
                  <span>
                    <span className="mono text-ink">{money(openStake)}</span>{" "}
                    committed
                    <span className="mx-1.5 text-line">·</span>
                    max {config.maxOpenTrades || "—"}
                  </span>
                }
              />
              <StatCard
                label="Max drawdown"
                value={`${summary.maxDrawdown.toFixed(2)}%`}
                tone="negative"
                icon={Activity}
                detail={
                  <span>
                    Profit factor{" "}
                    <span className="mono text-ink">
                      {summary.profitFactor === null
                        ? "n/a"
                        : summary.profitFactor.toFixed(2)}
                    </span>
                    <span className="mx-1.5 text-line">·</span>
                    {config.exchange}
                  </span>
                }
              />
            </div>
          </section>

          <section className="mt-4 grid gap-4 xl:grid-cols-3">
            <ChartCard
              title="Equity curve"
              description="Cumulative account value and net P/L across the selected window."
              className="xl:col-span-2"
              action={
                <Badge tone={positive ? "positive" : "negative"}>
                  {positive ? (
                    <ArrowUpRight className="size-3" />
                  ) : (
                    <ArrowDownRight className="size-3" />
                  )}
                  {percent(summary.netPnlPct)}
                </Badge>
              }
            >
              <div className="h-[290px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={data.equity}
                    margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#42e8a4" stopOpacity={0.28} />
                        <stop offset="100%" stopColor="#42e8a4" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      stroke="#1c293a"
                      strokeDasharray="3 5"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="date"
                      tickLine={false}
                      axisLine={false}
                      minTickGap={40}
                      tickFormatter={(value: string) =>
                        value
                          ? new Date(value).toLocaleDateString(undefined, {
                              month: "short",
                              day: "numeric",
                            })
                          : ""
                      }
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      width={58}
                      tickFormatter={(value: number) => compactMoney(value)}
                      domain={["dataMin - 1200", "dataMax + 1200"]}
                    />
                    <Tooltip
                      content={<EquityTooltip />}
                      cursor={{ stroke: "#3a506d", strokeDasharray: "3 4" }}
                    />
                    <ReferenceLine
                      y={data.equity[0]?.equity ?? 0}
                      stroke="#3a506d"
                      strokeDasharray="4 5"
                    />
                    <Area
                      type="monotone"
                      dataKey="equity"
                      stroke="#42e8a4"
                      strokeWidth={2}
                      fill="url(#equityFill)"
                      activeDot={{ r: 4, fill: "#42e8a4", stroke: "#06090e" }}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <section className="card flex flex-col p-5">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-sm font-semibold">Strategy health</h2>
                  <p className="mt-1 text-xs text-muted">
                    Execution quality at a glance.
                  </p>
                </div>
                <ShieldCheck className="size-4 text-positive" />
              </div>

              <div className="mt-6 flex items-center gap-5">
                <div
                  className="grid size-28 shrink-0 place-items-center rounded-full p-[7px]"
                  style={{
                    background: `conic-gradient(#42e8a4 ${
                      Math.min(100, Math.max(0, summary.winRate)) * 3.6
                    }deg, #1c293a 0)`,
                  }}
                >
                  <div className="grid size-full place-items-center rounded-full bg-panel text-center">
                    <div>
                      <p className="mono text-xl font-semibold">
                        {summary.winRate.toFixed(0)}%
                      </p>
                      <p className="text-[9px] uppercase tracking-wider text-muted">
                        win rate
                      </p>
                    </div>
                  </div>
                </div>
                <div className="min-w-0 space-y-3 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted">Profit factor</span>
                    <span className="mono text-ink">
                      {summary.profitFactor === null
                        ? "n/a"
                        : summary.profitFactor.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted">Max drawdown</span>
                    <span className="mono text-negative">
                      {summary.maxDrawdown.toFixed(2)}%
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted">Closed trades</span>
                    <span className="mono text-ink">{summary.closedTrades}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted">Free slots</span>
                    <span className="mono text-positive">
                      {Math.max(0, config.maxOpenTrades - summary.openTrades)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-6 space-y-2.5 border-t border-line pt-5 text-xs">
                <div className="flex items-center gap-2 text-muted">
                  <Coins className="size-3.5" />
                  Stake{" "}
                  <span className="mono ml-auto text-ink">
                    {money(config.stakeAmount)}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-muted">
                  <Clock3 className="size-3.5" />
                  Timeframe{" "}
                  <span className="mono ml-auto text-ink">{config.timeframe}</span>
                </div>
                <div className="flex items-center gap-2 text-muted">
                  <CircleDot className="size-3.5" />
                  Mode{" "}
                  <span className="ml-auto text-ink">
                    {config.dryRun ? "Dry run" : "Live capital"}
                  </span>
                </div>
              </div>
            </section>
          </section>

          <section id="positions" className="mt-8 scroll-mt-24">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold tracking-tight">
                  Open positions
                </h2>
                <p className="mt-1 text-xs text-muted">
                  Mark-to-market exposure managed by the X9 exit engine.
                </p>
              </div>
              <Badge tone={summary.unrealizedPnl >= 0 ? "positive" : "negative"}>
                Unrealized{" "}
                <span className="mono">{money(summary.unrealizedPnl)}</span>
              </Badge>
            </div>
            <div className="card p-4 sm:p-5">
              <PositionsTable trades={data.openTrades} />
            </div>
          </section>

          <section
            id="performance"
            className="mt-8 grid scroll-mt-24 gap-4 xl:grid-cols-5"
          >
            <ChartCard
              title="Pair attribution"
              description="Realized P/L by market. Red bars are net-negative pairs."
              className="xl:col-span-3"
            >
              <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={data.pairPerformance}
                    layout="vertical"
                    margin={{ top: 0, right: 12, left: 0, bottom: 0 }}
                    barCategoryGap={10}
                  >
                    <CartesianGrid
                      stroke="#1c293a"
                      strokeDasharray="3 5"
                      horizontal={false}
                    />
                    <XAxis
                      type="number"
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value: number) => compactMoney(value)}
                    />
                    <YAxis
                      type="category"
                      dataKey="pair"
                      width={64}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value: string) => shortPair(value)}
                    />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      cursor={{ fill: "rgba(110,168,255,.06)" }}
                      formatter={(value) => [money(Number(value)), "P/L"]}
                    />
                    <ReferenceLine x={0} stroke="#3a506d" />
                    <Bar
                      dataKey="profit_abs"
                      radius={[0, 6, 6, 0]}
                      isAnimationActive={false}
                    >
                      {data.pairPerformance.map((entry) => (
                        <Cell
                          key={entry.pair}
                          fill={entry.profit_abs >= 0 ? "#42e8a4" : "#ff6b7d"}
                          fillOpacity={0.82}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <section id="activity" className="card scroll-mt-24 p-5 xl:col-span-2">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-sm font-semibold">Recent activity</h2>
                  <p className="mt-1 text-xs text-muted">
                    Latest closed executions and exit reasons.
                  </p>
                </div>
                <Activity className="size-4 text-accent" />
              </div>
              <div className="mt-4 divide-y divide-line/70">
                {data.recentTrades.slice(0, 7).map((trade) => (
                  <div
                    key={trade.trade_id}
                    className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <span
                      className={`grid size-8 shrink-0 place-items-center rounded-xl border ${
                        trade.profit_abs >= 0
                          ? "border-positive/20 bg-positive/10 text-positive"
                          : "border-negative/20 bg-negative/10 text-negative"
                      }`}
                    >
                      {trade.is_short ? (
                        <ArrowDownRight className="size-3.5" />
                      ) : (
                        <ArrowUpRight className="size-3.5" />
                      )}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-ink">
                        {shortPair(trade.pair)}
                        <span className="ml-2 text-[10px] font-normal text-muted">
                          {trade.is_short ? "short" : "long"} · {trade.leverage}x
                        </span>
                      </p>
                      <p className="mt-0.5 text-[10px] text-muted">
                        {trade.exit_reason.replaceAll("_", " ")} ·{" "}
                        {duration(trade.trade_duration)}
                      </p>
                    </div>
                    <div className="ml-auto text-right">
                      <p
                        className={`mono text-xs ${
                          trade.profit_abs >= 0
                            ? "text-positive"
                            : "text-negative"
                        }`}
                      >
                        {money(trade.profit_abs)}
                      </p>
                      <p className="mono mt-0.5 text-[10px] text-muted">
                        {percent(trade.profit_ratio * 100)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </section>

          <section id="strategy" className="mt-8 scroll-mt-24">
            <div className="card overflow-hidden">
              <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[1.1fr_1.4fr]">
                <div>
                  <div className="flex items-center gap-2">
                    <Badge tone="accent">
                      <Sparkles className="size-3" />
                      X9
                    </Badge>
                    <Badge>{config.version}</Badge>
                  </div>
                  <h2 className="mt-4 text-xl font-semibold tracking-tight">
                    {config.strategy}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-muted">
                    A market-regime aware execution engine with layered entry
                    guards, adaptive de-risking and a strict open-trade budget.
                    The dashboard is read-only and never stores exchange
                    credentials.
                  </p>
                  <div className="mt-5 grid grid-cols-2 gap-3 text-xs">
                    {[
                      ["Exchange", config.exchange],
                      ["Trading mode", config.tradingMode],
                      ["Timeframe", config.timeframe],
                      ["Execution", config.dryRun ? "Dry run" : "Live"],
                    ].map(([label, value]) => (
                      <div
                        key={label}
                        className="rounded-xl border border-line bg-panel-2/60 px-3 py-2.5"
                      >
                        <p className="text-[9px] uppercase tracking-[0.14em] text-muted">
                          {label}
                        </p>
                        <p className="mt-1 truncate text-ink">{value}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-line bg-panel-2/40 p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-muted">
                      <LineChart className="size-4" />
                      Watched universe
                    </div>
                    <span className="mono text-xs text-ink">
                      {data.whitelist.length} pairs
                    </span>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {data.whitelist.length === 0 ? (
                      <p className="text-xs text-muted">
                        Pairlist unavailable for this connection.
                      </p>
                    ) : (
                      data.whitelist.slice(0, 18).map((pair) => (
                        <span
                          key={pair}
                          className="rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[11px] text-muted"
                        >
                          {shortPair(pair)}
                        </span>
                      ))
                    )}
                    {data.whitelist.length > 18 ? (
                      <span className="rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[11px] text-accent">
                        +{data.whitelist.length - 18} more
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-5 flex items-center gap-2 border-t border-line pt-4 text-[11px] text-muted">
                    <ShieldCheck className="size-3.5 text-positive" />
                    Read-only proxy · credentials stay on the server
                  </div>
                </div>
              </div>
            </div>
          </section>

          <footer className="mt-10 flex flex-wrap items-center justify-between gap-2 border-t border-line py-5 text-[11px] text-muted">
            <span>
              NFI X9 · {config.strategy} · {config.version}
            </span>
            <span className="flex items-center gap-2">
              <span
                className={`size-1.5 rounded-full ${
                  data.mode === "live" ? "bg-positive" : "bg-warning"
                }`}
              />
              {data.mode === "live"
                ? "Streaming from the local Freqtrade API"
                : "Demo data · configure FREQTRADE_API_URL for live mode"}
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
