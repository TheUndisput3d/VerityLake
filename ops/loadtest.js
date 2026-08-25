import http from 'k6/http';
import { check, sleep } from 'k6';
export const options = {
  vus: 1, duration: '2m',
  thresholds: { http_req_failed: ['rate<0.05'], http_req_duration: ['p(95)<120000'] },
};
export default function () {
  const response = http.post(`${__ENV.BASE_URL || 'http://127.0.0.1:8000'}/ask`,
    JSON.stringify({question:'What is the listed price of A Light in the Attic?',top_k:4}),
    {headers:{'Content-Type':'application/json','X-API-Key':__ENV.API_KEY},timeout:'180s'});
  check(response, {'request served': r => r.status === 200});
  sleep(5);
}
