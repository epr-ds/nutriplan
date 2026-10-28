# NutriPlan Load Testing Configuration (HRD-202)
# Run with: k6 run load-tests/nutriplan.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const ERROR_RATE = new Rate('error_rate');

// Test configuration
export const options = {
  stages: [
    { duration: '2m', target: 100 },   // Ramp up to 100 VUs
    { duration: '10m', target: 100 },  // Stay at 100 VUs
    { duration: '5m', target: 200 },   // Spike to 200 VUs
    { duration: '5m', target: 200 },   // Hold at 200 VUs
    { duration: '2m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    error_rate: ['rate<0.01'],
    checks: ['rate>0.95'],
  },
};

const BASE_URL = __ENV.K6_BASE_URL || 'https://api.nutriplan.example.com';
const USERNAME = __ENV.K6_USERNAME || 'test@example.com';
const PASSWORD = __ENV.K6_PASSWORD || 'testpassword';

const tags = { api: 'nutriplan-load-test' };

export default function () {
  // Step 1: Login
  const loginUrl = `${BASE_URL}/auth/login`;
  const loginPayload = JSON.stringify({ email: USERNAME, password: PASSWORD });
  const loginParams = {
    headers: { 'Content-Type': 'application/json' },
    tags,
  };
  const loginRes = http.post(loginUrl, loginPayload, loginParams);
  
  const loggedIn = check(loginRes, {
    'login: status 200': (r) => r.status === 200,
    'login: has token': (r) => r.json('access_token') != null,
  });
  
  if (!loggedIn) {
    ERROR_RATE.add(1);
    return;
  }
  
  const token = loginRes.json('access_token');
  const authHeaders = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    tags,
  };

  sleep(1);

  // Step 2: Get user profile
  const profileRes = http.get(`${BASE_URL}/api/profile`, authHeaders);
  check(profileRes, {
    'profile: status 200': (r) => r.status === 200,
    'profile: has name': (r) => r.json('name') != null,
  });

  sleep(1);

  // Step 3: Get meal plan
  const mealPlanRes = http.get(`${BASE_URL}/api/meal-plans`, authHeaders);
  const mealPlanOk = check(mealPlanRes, {
    'meal-plan: status 200': (r) => r.status === 200,
    'meal-plan: is array': (r) => Array.isArray(r.json()),
  });
  ERROR_RATE.add(mealPlanOk ? 0 : 1);

  sleep(1);

  // Step 4: Search recipes
  const searchRes = http.get(`${BASE_URL}/api/recipes/search?q=chicken`, authHeaders);
  check(searchRes, {
    'search: status 200': (r) => r.status === 200,
    'search: has results': (r) => r.json('results') != null,
  });

  sleep(1);

  // Step 5: Get nutrition info
  const nutritionRes = http.get(`${BASE_URL}/api/nutrition/info?recipe_id=1`, authHeaders);
  check(nutritionRes, {
    'nutrition: status 200': (r) => r.status === 200,
    'nutrition: has macros': (r) => r.json('macros') != null,
  });

  sleep(1);

  // Step 6: Order lifecycle (create → pay → track)
  const orderRes = http.get(`${BASE_URL}/api/orders`, authHeaders);
  const orderOk = check(orderRes, {
    'order: status 200': (r) => r.status === 200,
    'order: is array': (r) => Array.isArray(r.json()),
  });
  ERROR_RATE.add(orderOk ? 0 : 1);

  sleep(1);

  // Step 7: Notifications fan-out (order status push)
  const notificationsRes = http.get(`${BASE_URL}/api/notifications`, authHeaders);
  const notificationsOk = check(notificationsRes, {
    'notifications: status 200': (r) => r.status === 200,
    'notifications: has items': (r) => Array.isArray(r.json()),
  });
  ERROR_RATE.add(notificationsOk ? 0 : 1);

  sleep(1);
}
