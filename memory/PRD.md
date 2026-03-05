# FOMO Market Data API - PRD

## Original Problem Statement
Клонировать репозиторий, изучить архитектуру и развернуть модуль парсера.
Нужно поднять всю логику exchange (биржевые провайдеры) и первый уровень анализа данных.

## Final Architecture

### Data Sources Roles
```
MARKET DATA - CoinGecko ONLY
├ CoinGecko → 15k coins, categories, trending, prices
└ Exchanges → realtime prices (Coinbase, Hyperliquid)

ANALYTICS - CryptoRank + Dropstab (redundancy)
├ CryptoRank → fundraising, investors, unlocks
└ Dropstab  → fundraising, investors, unlocks
```

### Scheduler Jobs (Final)
```
MARKET (enabled, auto-running):
├ coingecko_top_coins    → 10 min
├ coingecko_trending     → 30 min  
├ coingecko_categories   → daily
└ coingecko_markets_full → daily

ANALYTICS (disabled, require browser):
├ cryptorank_fundraising → 1h
├ cryptorank_unlocks     → 1h
├ cryptorank_investors   → 6h
├ dropstab_fundraising   → 1h
├ dropstab_unlocks       → 1h
└ dropstab_investors     → 6h
```

### Provider Status
| Provider | Status | Data |
|----------|--------|------|
| Coinbase | ✅ | 378 spot |
| Hyperliquid | ✅ | 229 perp |
| Binance | ❌ 451 | geo-blocked |
| Bybit | ❌ 403 | geo-blocked |

## Current System Status

### Health Monitor Output
```json
{
  "scheduler_running": true,
  "jobs_total": 10,
  "jobs_enabled": 4,
  "errors_24h": [],
  "database_stats": {
    "intel_projects": 350,
    "intel_categories": 675
  }
}
```

## Implemented (2026-03-05)

### Exchange API ✅
- `/api/exchange/providers`, `/instruments`, `/ticker`
- `/orderbook`, `/candles`, `/funding`, `/open-interest`

### Intel API ✅
| Endpoint | Function |
|----------|----------|
| POST /api/intel/sync/coingecko/markets_full | ~15k coins |
| POST /api/intel/sync/dropstab/browser | Playwright scraper |
| GET /api/intel/admin/health | System health |
| POST /api/intel/scheduler/start | Start scheduler |

### Browser Scraper ✅
- Playwright for bot detection bypass
- Discovered Dropstab internal APIs
- Proxy support

### Scheduler ✅
- Auto-running CoinGecko jobs
- Browser jobs ready (disabled by default)

## Database Stats
```
intel_projects:   350
intel_categories: 675
intel_funding:    0 (pending)
intel_unlocks:    0 (pending)
```

## Backlog

### P0 (Done)
- [x] Exchange providers (Coinbase, Hyperliquid)
- [x] CoinGecko full market sync
- [x] Scheduler with correct jobs
- [x] Health monitor
- [x] Browser scraper

### P1 (Next)
- [ ] Enable browser jobs for analytics
- [ ] CryptoRank browser discovery
- [ ] Full analytics data collection

### P2 (Future)
- [ ] Data deduplication
- [ ] Redis realtime pipeline
- [ ] Frontend dashboard
