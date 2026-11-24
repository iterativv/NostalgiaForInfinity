import { NextResponse } from "next/server";
import { makeDemoData } from "@/lib/demo";
import type {
  ClosedTrade,
  DashboardData,
  EquityPoint,
  OpenTrade,
  PairPerformance,
} from "@/lib/types";

export const dynamic = "force-dynamic";

const BASE_URL = process.env.FREQTRADE_API_URL?.replace(/\/+$/, "");
const USERNAME = process.env.FREQTRADE_USERNAME ?? "";
const PASSWORD = process.env.FREQTRADE_PASSWORD ?? "";

type Json = Record<string, unknown>;

async function freqtrade<T>(path: string): Promise<T> {
  if (!BASE_URL) throw new Error("FREQTRADE_API_URL is not configured");
  const headers: HeadersInit = { Accept: "application/json" };
  if (USERNAME || PASSWORD) {
    headers.Authorization = `Basic ${Buffer.from(
      `${USERNAME}:${PASSWORD}`,
    ).toString("base64")}`;
  }
  const response = await fetch(`${BASE_URL}${path}`, {
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(8_000),
  });
  if (!response.ok) {
    throw new Error(`${path} answered ${response.status}`);
  }
  return (await response.json()) as T;
}

function number(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function mapOpenTrade(raw: Json): OpenTrade {
  const openRate = number(raw.open_rate);
  const currentRate = number(raw.current_rate, openRate);
  return {
    trade_id: number(raw.trade_id),
    pair: text(raw.pair, "unknown"),
    is_short: Boolean(raw.is_short),
    leverage: number(raw.leverage, 1),
    amount: number(raw.amount),
    stake_amount: number(raw.stake_amount),
    open_rate: openRate,
    current_rate: currentRate,
    profit_abs: number(raw.profit_abs),
    profit_ratio: number(raw.profit_ratio),
    open_date: text(raw.open_date, new Date().toISOString()),
    enter_tag: text(raw.enter_tag, "manual"),
  };
}

function mapClosedTrade(raw: Json): ClosedTrade {
  return {
    trade_id: number(raw.trade_id),
    pair: text(raw.pair, "unknown"),
    is_short: Boolean(raw.is_short),
    leverage: number(raw.leverage, 1),
    open_rate: number(raw.open_rate),
    close_rate: number(raw.close_rate),
    profit_abs: number(raw.profit_abs),
    profit_ratio: number(raw.profit_ratio),
    open_date: text(raw.open_date),
    close_date: text(raw.close_date),
    exit_reason: text(raw.exit_reason, "unknown"),
    enter_tag: text(raw.enter_tag, "manual"),
    trade_duration: number(raw.trade_duration),
  };
}

function buildEquity(
  daily: Json[],
  closedTrades: ClosedTrade[],
  equityNow: number,
  realizedPnl: number,
): EquityPoint[] {
  const points: EquityPoint[] = [];
  if (daily.length > 0) {
    let cumulative = 0;
    const start = equityNow - daily.reduce(
      (sum, row) => sum + number(row.abs_profit),
      0,
    );
    for (const row of daily) {
      cumulative += number(row.abs_profit);
      points.push({
        date: text(row.date),
        equity: Number((start + cumulative).toFixed(2)),
        pnl: Number(cumulative.toFixed(2)),
      });
    }
    return points;
  }

  const start = equityNow - realizedPnl;
  let cumulative = 0;
  for (const trade of [...closedTrades].sort((a, b) =>
    a.close_date.localeCompare(b.close_date),
  )) {
    cumulative += trade.profit_abs;
    points.push({
      date: trade.close_date,
      equity: Number((start + cumulative).toFixed(2)),
      pnl: Number(cumulative.toFixed(2)),
    });
  }
  return points.length > 0 ? points : [{ date: "", equity: equityNow, pnl: 0 }];
}

export async function GET() {
  if (!BASE_URL) {
    return NextResponse.json(makeDemoData(), {
      headers: { "Cache-Control": "no-store" },
    });
  }

  const errors: string[] = [];
  const settled = await Promise.allSettled([
    freqtrade<Json>("/api/v1/status"),
    freqtrade<Json>("/api/v1/profit"),
    freqtrade<Json>("/api/v1/balance"),
    freqtrade<{ trades?: Json[] }>("/api/v1/trades?limit=500"),
    freqtrade<Json[]>("/api/v1/performance"),
    freqtrade<Json>("/api/v1/show_config"),
    freqtrade<string[]>("/api/v1/whitelist"),
    freqtrade<Json>("/api/v1/daily"),
  ]);

  const value = <T>(index: number, fallback: T): T => {
    const result = settled[index];
    if (result.status === "fulfilled") return result.value as T;
    errors.push(result.reason instanceof Error ? result.reason.message : "request failed");
    return fallback;
  };

  const status = value<Json[]>(0, []);
  const profit = value<Json>(1, {});
  const balance = value<Json>(2, {});
  const tradesPayload = value<{ trades?: Json[] }>(3, { trades: [] });
  const performance = value<Json[]>(4, []);
  const config = value<Json>(5, {});
  const whitelist = value<string[]>(6, []);
  const dailyRaw = value<Json | Json[]>(7, []);
  const daily = Array.isArray(dailyRaw)
    ? dailyRaw
    : Array.isArray(dailyRaw.data)
      ? (dailyRaw.data as Json[])
      : [];

  if (settled.every((result) => result.status === "rejected")) {
    return NextResponse.json(
      { error: "Freqtrade REST API is unreachable", errors },
      { status: 502 },
    );
  }

  try {
    const openTrades = (Array.isArray(status) ? status : []).map(mapOpenTrade);
    const recentTrades = (tradesPayload.trades ?? []).map(mapClosedTrade);
    const pairPerformance: PairPerformance[] = (
      Array.isArray(performance) ? performance : []
    )
      .map((row) => ({
        pair: text(row.pair, "unknown"),
        profit_abs: number(row.profit_abs),
        profit_percent: number(row.profit_percent),
        count: number(row.count),
      }))
      .sort((a, b) => b.profit_abs - a.profit_abs);

    const equityNow = number(balance.total);
    const realizedPnl = number(profit.profit_closed_coin);
    const unrealizedPnl = openTrades.reduce(
      (sum, trade) => sum + trade.profit_abs,
      0,
    );
    const winners = number(profit.winning_trades);
    const losers = number(profit.losing_trades);
    const closedTrades = number(
      profit.closed_trade_count,
      recentTrades.length,
    );

    const data: DashboardData = {
      mode: "live",
      generatedAt: new Date().toISOString(),
      config: {
        strategy: text(config.strategy, "NostalgiaForInfinityX9"),
        version: text(config.strategy_version, "v19.0.0"),
        timeframe: text(config.timeframe, "5m"),
        maxOpenTrades: number(config.max_open_trades),
        stakeAmount: number(config.stake_amount),
        dryRun: Boolean(config.dry_run),
        exchange: text(config.exchange, "unknown"),
        tradingMode: text(config.trading_mode, "futures"),
      },
      summary: {
        equity: equityNow,
        netPnl: number(profit.profit_all_coin, realizedPnl + unrealizedPnl),
        netPnlPct: number(profit.profit_all_percent),
        realizedPnl,
        unrealizedPnl,
        winRate: number(
          profit.winrate,
          winners + losers > 0 ? (winners / (winners + losers)) * 100 : 0,
        ),
        winners,
        losers,
        closedTrades,
        openTrades: openTrades.length,
        maxDrawdown: Math.abs(number(profit.max_drawdown_abs)),
        profitFactor:
          profit.profit_factor === undefined
            ? null
            : number(profit.profit_factor),
      },
      equity: buildEquity(daily, recentTrades, equityNow, realizedPnl),
      openTrades,
      recentTrades,
      pairPerformance,
      whitelist: (Array.isArray(whitelist) ? whitelist : []).filter(
        (pair): pair is string => typeof pair === "string",
      ),
      errors: errors.length > 0 ? errors : undefined,
    };

    return NextResponse.json(data, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "invalid API payload",
        errors,
      },
      { status: 502 },
    );
  }
}
