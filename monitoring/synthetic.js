# NutriPlan Synthetic Monitoring (HRD-903)
# Run: k6 run monitoring/synthetic.js
# Schedule: Every 5 minutes via cron/GitHub Actions

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const API_ERROR = new Rate('api_error');
const API_LATENCY = new Trend('api_latency');

export const options = {
  stages: [
    { duration: '1m', target: 10 },
    { duration: '3m', target: 10 },
    { duration: '1m', target: 0 },
  ],
  thresholds: {
    api_latency: ['p(95)<500', 'p(99)<1000'],
    api_error: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.MONITOR_BASE_URL || 'https://api.nutriplan.example.com';
const USERNAME = __ENV.MONITOR_USERNAME || 'synthetic@example.com';
const PASSWORD = __ENV.MONITOR_PASSWORD || 'monitorpassword';

// Key user journeys to monitor
const journeys = [
  { name: 'signup', method: 'post', path: '/auth/register', check: (r) => r.status === 201 },
  { name: 'login', method: 'post', path: '/auth/login', check: (r) => r.status === 200 },
  { name: 'profile', method: 'get', path: '/api/profile', check: (r) => r.status === 200 },
  { name: 'meal-plans', method: 'get', path: '/api/meal-plans', check: (r) => r.status === 200 },
  { name: 'meal-plan-detail', method: 'get', path: '/api/meal-plans/1', check: (r) => r.status === 200 },
  { name: 'recipes-search', method: 'get', path: '/api/recipes/search?q=chicken', check: (r) => r.status === 200 },
  { name: 'recipe-detail', method: 'get', path: '/api/recipes/1', check: (r) => r.status === 200 },
  { name: 'nutrition-info', method: 'get', path: '/api/nutrition/info?recipe_id=1', check: (r) => r.status === 200 },
  { name: 'allergen-check', method: 'get', path: '/api/allergens/safe?recipe_id=1', check: (r) => r.status === 200 },
];

let token = null;

export default function () {
  // Login first
  if (!token) {
    const loginRes = http.post(
      `${BASE_URL}/auth/login`,
      JSON.stringify({ email: USERNAME, password: PASSWORD }),
      { headers: { 'Content-Type': 'application/json' } }
    );
    
    if (check(loginRes, { 'login: success': (r) => r.status === 200 })) {
      token = loginRes.json('access_token');
    } else {
      return;
    }
  }

  const authHeaders = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  };

  // Run each journey
  journeys.forEach((journey) => {
    let res;
    const url = `${BASE_URL}${journey.path}`;
    
    if (journey.method === 'post') {
      res = http.post(url, '{}', authHeaders);
    } else {
      res = http.get(url, authHeaders);
    }

    const latency = res.timings.duration;
    API_LATENCY.add(latency);
    
    const ok = check(res, {
      [`${journey.name}: status`]: (r) => journey.check(r),
      [`${journey.name}: fast`]: (r) => r.timings.duration < 500,
    });
    
    API_ERROR.add(!ok);
    sleep(0.5);
  });
}
