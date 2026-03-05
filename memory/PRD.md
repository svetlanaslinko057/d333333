# FOMO Market Data API - PRD

## Original Problem Statement
Клонировать репозиторий, изучить архитектуру и развернуть модуль парсера.
Нужно поднять всю логику exchange (биржевые провайдеры) и первый уровень анализа данных.

## Final Architecture

### Multi-Layer Scraper Engine (IRON-CLAD)
```
Layer 1: Direct API (fastest, may break)
Layer 2: Browser Network Discovery (stealth, request blueprint capture)
Layer 3: DOM Extraction (slowest, most stable)

If Layer 1 fails → fallback to Layer 2
If Layer 2 fails → fallback to Layer 3
```

### Data Pipeline Architecture
```
Scheduler
   │
   ▼
Job Queue (Redis)
   │
   ▼
Workers (N parallel)
   │
   ├── Discovery Mode: Browser → Capture XHR → Save Blueprints
   │
   └── Sync Mode: Replay Blueprints → Direct API → Raw JSON
           │
           ▼
      Raw Data Store (/app/data/raw/)
           │
           ▼
      Parsers → MongoDB
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
✅ Full request blueprint capture (URL, headers, body, cookies)
✅ Endpoint registry with scoring (success/fail tracking)
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

### Intel Sync (Legacy)
- `POST /api/intel/sync/coingecko/markets_full` - 15k coins
- `POST /api/intel/sync/dropstab/browser` - stealth scraper
- `GET /api/intel/admin/health` - system health

### NEW: Scraper Engine
- `GET /api/intel/scraper/status` - Full scraper status
- `POST /api/intel/scraper/discover/{source}` - Browser discovery
- `POST /api/intel/scraper/sync/{source}/{target}` - Sync from registry
- `GET /api/intel/scraper/registry` - View discovered endpoints
- `GET /api/intel/scraper/raw` - List raw data files
- `GET /api/intel/scraper/raw/stats` - Storage statistics

### NEW: Worker System
- `GET /api/intel/worker/status` - Worker status
- `POST /api/intel/worker/start` - Start worker
- `POST /api/intel/worker/stop` - Stop worker

### NEW: Job Queue (Redis)
- `GET /api/intel/queue/status` - Queue statistics
- `GET /api/intel/queue/jobs?status=pending|processing|completed|failed`
- `POST /api/intel/queue/push/discover?source=dropstab&targets=unlocks,funding`
- `POST /api/intel/queue/push/sync?source=dropstab&targets=unlocks`
- `DELETE /api/intel/queue/clear?confirm=true`

### Scheduler
- `POST /api/intel/scheduler/start`
- `POST /api/intel/scheduler/run/{job}`
- `GET /api/intel/scheduler/status`

### Proxy Admin
- `GET /api/intel/admin/proxy/status`
- `POST /api/intel/admin/proxy/add`
- `POST /api/intel/admin/proxy/remove`

## Current Stats (2026-03-05)
```
Registry endpoints: 13
├ dropstab/unlocks:    4
├ dropstab/funding:    4
└ dropstab/investors:  5

Raw files: 3 discovery files
```

## Discovered Direct APIs
```
✅ api2.dropstab.com/portfolio/api/markets
✅ api2.dropstab.com/portfolio/api/markets/recentSearchItems
✅ api2.dropstab.com/portfolio/api/exchange
✅ extra-bff.dropstab.com/v1.2/market-data/market-total-and-widgets-summary
```

## Backlog

### P0 (Done)
- [x] Exchange providers (Coinbase, Hyperliquid, Binance, Bybit)
- [x] CoinGecko full market sync
- [x] Scheduler with correct jobs
- [x] Stealth browser scraper
- [x] Proxy failover system
- [x] Human behaviour simulation
- [x] Endpoint auto-discovery
- [x] **Redis Job Queue**
- [x] **Worker System (parallel processing)**
- [x] **Request Blueprint Capture**
- [x] **Raw Data Storage**
- [x] **Endpoint Registry with Scoring**

### P1 (In Progress)
- [ ] Implement parsers for raw data (dropstab/parsers.py, cryptorank/parsers.py)
- [ ] Full browser scrape for analytics (more targets)
- [ ] CryptoRank browser discovery
- [ ] Direct API cookie replay

### P2 (Future)
- [ ] DOM Parser (Layer 3) fallback
- [ ] Data deduplication from multiple sources
- [ ] Realtime price updates pipeline
