/** API contract with the local paper-trading engine (phase 1). */

export type NewsState = "off" | "no_headlines" | "neutral" | "boost" | "veto";
export type Action = "enter" | "exit" | "hold";
export type OrderStatus = "filled" | "rejected";

export interface LiveTradingInfo {
  available: false;
  reason: string;
}

export interface NewsScoringStatus {
  enabled: boolean;
  provider: string;
  model: string | null;
  reason: string | null;
  last_error: string | null;
}

export interface RiskLimits {
  max_position_pct: number;
  max_open_positions: number;
  daily_loss_limit_pct: number;
}

export interface RiskResponse {
  limits: RiskLimits;
  kill_switch: boolean;
  day: string | null;
  day_start_equity: number | null;
  halted: boolean;
  halted_at: number | null;
}

export interface CycleSummary {
  candles_added?: Record<string, number>;
  news?: unknown;
  signals?: unknown[];
  orders?: unknown[];
  skipped?: unknown[];
}

export interface Heartbeat {
  id: number;
  started_at: number;
  finished_at: number | null;
  status: string;
  error: string | null;
  summary?: CycleSummary | null;
}

export interface CandlePoint {
  ts: number;
  close: number;
}

export interface CandleSeriesResponse {
  exchange: string;
  timeframe: string;
  series: Record<string, CandlePoint[]>;
}

export interface TradingLoopInfo {
  enabled: boolean;
  supervisor: boolean;
  note: string;
}

export interface Status {
  mode: "paper";
  live_trading: LiveTradingInfo;
  /** Present on current engines; optional so a mid-upgrade desk still typechecks. */
  trading?: TradingLoopInfo;
  exchange: string;
  symbols: string[];
  heartbeat: Heartbeat | null;
  news_scoring: NewsScoringStatus;
  risk: RiskResponse;
  server_time: number;
}

export interface PositionRow {
  symbol: string;
  qty: number;
  entry_price: number;
  entry_ts: number;
  stop_price: number;
  highest_close: number;
  last: number;
  unrealized_pnl: number;
}

export interface WatchlistRow {
  symbol: string;
  last: number | null;
  bid: number | null;
  ask: number | null;
  ts: number | null;
  trend: "up" | "down" | null;
}

export interface Portfolio {
  cash: number;
  equity: number;
  starting_cash: number;
  realized_pnl: number;
  fees_paid: number;
  total_pnl: number;
  day_pnl: number | null;
  positions: PositionRow[];
  watchlist: WatchlistRow[];
}

export interface EquityPoint {
  ts: number;
  equity: number;
  cash: number;
}

export interface HeadlineScore {
  coin: string;
  direction: number;
  strength: number;
  confidence: number;
  rationale: string;
  provider?: string;
  model?: string;
}

export interface HeadlineRow {
  id: number;
  source: string;
  kind?: string;
  title: string;
  url: string;
  published_at: number;
  fetched_at?: number;
  score_status: string;
  score_error?: string | null;
  scores: HeadlineScore[];
}

export interface SignalOrder {
  id: number;
  side: string;
  status: string;
  reject_reason: string | null;
  qty: number;
  fill_price: number | null;
}

export interface SignalRow {
  id: number;
  ts: number;
  created_at: number;
  symbol: string;
  action: Action;
  reasons: string[];
  indicators: Record<string, number | null>;
  news_state: NewsState;
  news_score: number | null;
  size_multiplier: number;
  headlines: HeadlineRow[];
  order: SignalOrder | null;
}

export interface OrderRow {
  id: number;
  created_at: number;
  symbol: string;
  side: string;
  requested_qty: number;
  qty: number;
  ref_price: number;
  status: OrderStatus | string;
  reject_reason: string | null;
  notes: string[];
  fill_price: number | null;
  fee: number | null;
  realized_pnl: number | null;
  signal_id: number | null;
  broker: string;
}

export interface NewsSource {
  name: string;
  kind: string;
  url: string;
  last_attempt_at: number | null;
  last_ok_at: number | null;
  last_error: string | null;
  last_count: number | null;
}

export interface NewsResponse {
  scoring: NewsScoringStatus;
  headlines: HeadlineRow[];
  sources: NewsSource[];
}

export interface BacktestResult {
  symbols: string[];
  data_start: number | null;
  period_start: number | null;
  period_end: number | null;
  bars: number;
  starting_cash: number;
  final_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  trades: number;
  wins: number;
  win_rate_pct: number | null;
  profit_factor: number | null;
  total_fees: number;
  buy_hold_return_pct: number | null;
  rejected_orders: number;
  fee_bps: number;
  slippage_bps: number;
  trade_list: Array<Record<string, number | string | null>>;
  open_positions: Array<Record<string, number | string | null>>;
  equity_curve: Array<{ ts: number; equity: number }>;
  news_included: boolean;
}

export interface BacktestRun {
  id: number;
  created_at: number;
  params: Record<string, unknown>;
  result: BacktestResult;
  news_included: boolean;
}

export interface CandleSymbolSummary {
  symbol: string;
  hourly_candles: number;
  signal_bars: number;
  oldest_ts: number | null;
  newest_ts: number | null;
}

export interface CandleHistorySummary {
  exchange: string;
  symbols: CandleSymbolSummary[];
  max_signal_bars: number;
  required_signal_bars: number;
  ready_for_backtest: boolean;
  backfill_days_default: number;
  message: string | null;
}
