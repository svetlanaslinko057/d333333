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

### Data Pipeline Architecture (NEW!)
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
      Adapter Parsers → Unified Models
           │
           ▼
      Normalized Tables (normalized_*)
           │
           ▼
      Dedup Engine
           │
           ▼
      Curated Intel Tables (intel_*)
           │
           ▼
      Event Index
           │
           ▼
      API Layer
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
├ unlocks
├ token sales (ICO/IEO/IDO)
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

## Unified Data Models (NEW!)
```python
IntelUnlock   - token unlock events
IntelFunding  - funding rounds
IntelInvestor - VC/funds
IntelSale     - ICO/IEO/IDO sales
IntelEvent    - unified event index for fast queries
```

## Database Collections
```
# Raw storage
/app/data/raw/{source}/{target}/*.json.gz

# Normalized (parsed, per-source)
normalized_unlocks
normalized_funding
normalized_investors
normalized_sales

# Curated (deduplicated, multi-source)
intel_unlocks
intel_funding
intel_investors
intel_sales

# Event Index (fast queries)
intel_events
```

## API Endpoints

### Exchange
- `/api/exchange/providers` - 4 providers
- `/api/exchange/instruments` - 607 instruments
- `/api/exchange/ticker`, `/orderbook`, `/candles`

### Intel Sync (Legacy)
- `POST /api/intel/sync/coingecko/markets_full` - 15k coins
- `GET /api/intel/admin/health` - system health

### Scraper Engine
- `GET /api/intel/scraper/status` - Full scraper status
- `POST /api/intel/scraper/discover/{source}` - Browser discovery
- `GET /api/intel/scraper/registry` - View discovered endpoints
- `GET /api/intel/scraper/raw` - List raw data files
- `GET /api/intel/scraper/raw/stats` - Storage statistics

### Worker System
- `GET /api/intel/worker/status` - Worker status
- `POST /api/intel/worker/start` - Start worker
- `POST /api/intel/worker/stop` - Stop worker

### Job Queue (Redis)
- `GET /api/intel/queue/status` - Queue statistics
- `GET /api/intel/queue/jobs?status=pending|processing|completed|failed`
- `POST /api/intel/queue/push/discover?source=dropstab&targets=unlocks,funding`
- `POST /api/intel/queue/push/sync?source=dropstab&targets=unlocks`
- `DELETE /api/intel/queue/clear?confirm=true`

### Normalization Pipeline (NEW!)
- `GET /api/intel/pipeline/stats` - Normalized/curated counts
- `POST /api/intel/pipeline/dedupe` - Run full dedup pipeline
- `POST /api/intel/pipeline/dedupe/{entity}` - Dedupe specific entity
- `POST /api/intel/pipeline/index` - Rebuild event index

### Curated Data API (NEW!)
- `GET /api/intel/curated/unlocks?days=30&symbol=SOL&min_usd=1000000`
- `GET /api/intel/curated/funding?days=90&round_type=seed`
- `GET /api/intel/curated/investors?tier=tier_1&search=a16z`

### Event Index (NEW!)
- `GET /api/intel/events?type=unlock&days=30&direction=future`
- `GET /api/intel/events/{symbol}` - All events for symbol

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
Registry endpoints: 16
├ dropstab/unlocks:    4
├ dropstab/funding:    4
├ dropstab/investors:  5
├ cryptorank/funding:  3

Raw files: 4 discovery files
```

## Discovered Direct APIs
```
# Dropstab
✅ api2.dropstab.com/portfolio/api/markets
✅ api2.dropstab.com/portfolio/api/markets/recentSearchItems
✅ api2.dropstab.com/portfolio/api/exchange
✅ extra-bff.dropstab.com/v1.2/market-data/market-total-and-widgets-summary

# CryptoRank
✅ api.cryptorank.io/v0/global
✅ api.cryptorank.io/v0/funding-rounds-widgets/total-funding-over
✅ api.cryptorank.io/v0/app/coins/fiat
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
- [x] **Unified Data Models (IntelUnlock, IntelFunding, etc)**
- [x] **Adapter Parsers (Dropstab, CryptoRank)**
- [x] **Normalization Engine**
- [x] **Deduplication Engine**
- [x] **Event Index for Fast Queries**
- [x] **Curated Data API**

### P1 (In Progress)
- [ ] Run full discovery for all CryptoRank targets
- [ ] Collect actual data and run through parsing pipeline
- [ ] Populate curated tables with real data
- [ ] Activate scheduler for periodic data collection

### P2 (Future)
- [ ] DOM Parser (Layer 3) fallback
- [ ] Data deduplication optimization
- [ ] Analytics and aggregation layer
- [ ] Alerts and signals
