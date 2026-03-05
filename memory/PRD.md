# FOMO Market Data API - PRD

## Original Problem Statement
Клонировать репозиторий, изучить архитектуру и развернуть модуль парсера.
Нужно поднять всю логику exchange (биржевые провайдеры) и первый уровень анализа данных.

## Final Architecture

### Multi-Layer Scraper Engine
```
Layer 1: Direct API (fastest, may break)
Layer 2: Browser Network Discovery (stealth)
Layer 3: DOM Extraction (slowest, most stable)

If Layer 1 fails → fallback to Layer 2
If Layer 2 fails → fallback to Layer 3
```

### Data Sources
```
MARKET DATA - CoinGecko ONLY
├ 15k coins
├ 675 categories
└ trending

ANALYTICS - CryptoRank + Dropstab (redundancy)
├ fundraising
├ investors
└ unlocks
```

### Stealth Browser Features
```
✅ navigator.webdriver = undefined
✅ chrome.runtime mock  
✅ Human behaviour simulation (mouse, scroll, delays)
✅ Realistic viewport 1920x1080
✅ Proper user-agent
✅ Snapshot system for debugging
✅ Endpoint registry auto-discovery
```

### Proxy Failover System
```
Proxy #1 (primary)
    ↓ if fails
Proxy #2 (backup)
    ↓ if fails
Proxy #3 (backup)

NOT rotation - just failover
```

## API Endpoints

### Exchange
- `/api/exchange/providers` - 4 providers
- `/api/exchange/instruments` - 607 instruments
- `/api/exchange/ticker`, `/orderbook`, `/candles`

### Intel Sync
- `POST /api/intel/sync/coingecko/markets_full` - 15k coins
- `POST /api/intel/sync/dropstab/browser` - stealth scraper
- `GET /api/intel/admin/health` - system health

### Scheduler
- `POST /api/intel/scheduler/start`
- `POST /api/intel/scheduler/run/{job}`
- `GET /api/intel/scheduler/status`

### Proxy Admin
- `GET /api/intel/admin/proxy/status`
- `POST /api/intel/admin/proxy/add`
- `POST /api/intel/admin/proxy/remove`

## Database Stats
```
intel_projects:   350
intel_categories: 675
intel_funding:    0 (pending browser scrape)
intel_unlocks:    0 (pending)
```

## Discovered Direct APIs
```
✅ api2.dropstab.com/portfolio/api/marketTotal/last - works!
⚠️ api2.dropstab.com/portfolio/api/markets - needs cookies
⚠️ api2.dropstab.com/portfolio/api/exchange - needs cookies
```

## Backlog

### P0 (Done)
- [x] Exchange providers (Coinbase, Hyperliquid)
- [x] CoinGecko full market sync
- [x] Scheduler with correct jobs
- [x] Stealth browser scraper
- [x] Proxy failover system
- [x] Human behaviour simulation
- [x] Endpoint auto-discovery

### P1 (Next)
- [ ] Full browser scrape for analytics
- [ ] CryptoRank browser discovery
- [ ] Direct API cookie replay

### P2 (Future)
- [ ] Data deduplication
- [ ] Redis realtime pipeline
