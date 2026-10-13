# Soak / Endurance Test

## HRD-904: Long-Session Load Testing

### Purpose

Validate that NutriPlan services maintain stability under sustained load over extended periods (24-72 hours). Detect memory leaks, connection pool exhaustion, cache degradation, and data corruption under continuous operation.

### Test Configuration

```javascript
// load-tests/soak.js
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';
import http from 'k6/http';

const errorRate = new Rate('errors');

// Soak test parameters
const DURATION_HOURS = 24;
const TARGET_RPS = 50;
const VU_RANGE = [20, 50];

export const options = {
  stages: [
    { duration: '5m', target: 20 },   // Ramp up
    { duration: `${DURATION_HOURS}h`, target: 50 },  // Sustained load
    { duration: '5m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    errors: ['rate<0.05'],
    http_req_waiting: ['p(95)<400'],
    http_req_connecting: ['p(95)<100'],
    http_req_tls_handshaking: ['p(95)<200'],
  },
};

export function handleSummary(data) {
  return {
    'soak-report.json': JSON.stringify({
      duration_hours: DURATION_HOURS,
      avg_rps: TARGET_RPS,
      error_rate: data.metrics.errors?.values?.rate || 0,
      p95_latency: data.metrics.http_req_duration?.values?.['p(95)'] || 0,
      p99_latency: data.metrics.http_req_duration?.values?.['p(99)'] || 0,
      total_requests: data.metrics.http_req_duration?.values?.count || 0,
    }, null, 2),
  };
}

function getAuthToken() {
  // Use pre-provisioned test account
  return 'Bearer test-soak-account-token';
}

function randomUserId() {
  const users = ['usr_soak_001', 'usr_soak_002', 'usr_soak_003'];
  return users[Math.floor(Math.random() * users.length)];
}

export default function () {
  const userId = randomUserId();
  const token = getAuthToken();

  // Simulate realistic user journey mix
  const journey = Math.random();

  if (journey < 0.3) {
    // Home feed (most common)
    const res = http.get(`${__ENV.BASE_URL}/api/v1/home`, {
      headers: { Authorization: token },
      timeout: 5000,
    });
    check(res, {
      'home status 200': res.status === 200,
      'home p95 < 500ms': res.timings.duration < 500,
    });
    errorRate.add(res.status >= 500);
  } else if (journey < 0.5) {
    // Meal plan
    const res = http.get(`${__ENV.BASE_URL}/api/v1/meal-plans/current`, {
      headers: { Authorization: token },
      timeout: 5000,
    });
    check(res, {
      'meal-plan status 200': res.status === 200,
      'meal-plan p95 < 500ms': res.timings.duration < 500,
    });
    errorRate.add(res.status >= 500);
  } else if (journey < 0.7) {
    // AI analysis
    const res = http.post(`${__ENV.BASE_URL}/api/v1/analysis`, JSON.stringify({
      meal: { name: 'test meal', ingredients: [{ name: 'rice', quantity: 1, unit: 'cup' }] },
    }), {
      headers: {
        Authorization: token,
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    });
    check(res, {
      'analysis status 200-299': res.status >= 200 && res.status < 300,
      'analysis p99 < 3s': res.timings.duration < 3000,
    });
    errorRate.add(res.status >= 500);
  } else if (journey < 0.85) {
    // Recipe search
    const res = http.get(`${__ENV.BASE_URL}/api/v1/recipes?query=chicken`, {
      headers: { Authorization: token },
      timeout: 5000,
    });
    check(res, {
      'recipe status 200': res.status === 200,
      'recipe p95 < 500ms': res.timings.duration < 500,
    });
    errorRate.add(res.status >= 500);
  } else {
    // Profile update (write)
    const res = http.put(`${__ENV.BASE_URL}/api/v1/profile`, JSON.stringify({
      name: 'Soak Test User',
      dietary_preferences: ['vegetarian'],
    }), {
      headers: {
        Authorization: token,
        'Content-Type': 'application/json',
      },
      timeout: 5000,
    });
    check(res, {
      'profile status 200': res.status === 200,
      'profile p95 < 500ms': res.timings.duration < 500,
    });
    errorRate.add(res.status >= 500);
  }

  sleep(Math.random() * 3 + 1); // 1-4s think time
}
```

### Execution

```bash
# Run soak test against staging
k6 run --out json=soak-results.json load-tests/soak.js \
  --env BASE_URL=https://staging.nutriplan.app \
  --env AUTH_TOKEN="Bearer $SOAK_TEST_TOKEN"

# Run soak test against production (off-peak hours only)
k6 run --out json=soak-results.json load-tests/soak.js \
  --env BASE_URL=https://api.nutriplan.app \
  --env AUTH_TOKEN="Bearer $PROD_SOAK_TOKEN"
```

### Pass/Fail Criteria

| Metric | Pass Threshold | Rationale |
|--------|----------------|-----------|
| Error rate | < 1% | Acceptable for sustained load |
| p95 latency | < 500ms | Within SLO |
| p99 latency | < 1000ms | Within SLO |
| Memory growth | < 5% over test | No memory leaks |
| Connection pool | No exhaustion | Stable connections |
| Cache hit rate | > 60% | Cache functioning |
| DB connections | < 80% max | Headroom available |
| Disk usage | < 90% | No log growth issues |

### Monitoring During Soak Test

| Check | Tool | Frequency |
|-------|------|-----------|
| Memory per pod | Prometheus | 15s |
| GC pauses | Prometheus | 15s |
| DB connection count | Prometheus | 15s |
| Cache hit rate | Prometheus | 15s |
| Error rate | Grafana | 1m |
| Latency p95/p99 | Grafana | 1m |
| Disk I/O | Grafana | 15s |
| Network I/O | Grafana | 15s |

### Soak Test Schedule

| Phase | Duration | Frequency | Target |
|-------|----------|-----------|--------|
| Pre-GA | 24h | Once | Validate baseline |
| Post-GA | 72h | Monthly | Validate stability |
| Quarterly | 72h | Quarterly | Regression check |

### Cleanup

After soak test completes:
1. Verify no data corruption in meal plans, orders, user profiles
2. Check for orphaned sessions or stale cache entries
3. Verify log volume didn't cause disk pressure
4. Confirm no zombie connections in connection pools
5. Review metrics for gradual degradation trends
