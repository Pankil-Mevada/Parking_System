// Synthetic browser QA only. Never used by the production/local real API.
// Change .tools/browser-scenario.txt to success, empty, slow, failure or timeout.
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
const server = createServer((request, response) => {
  if (request.url !== '/api/locations') {
    response.writeHead(404).end();
    return;
  }
  let scenario = 'success';
  try { scenario = readFileSync('.tools/browser-scenario.txt', 'utf8').trim(); } catch {}
  const send = () => {
    response.writeHead(scenario === 'failure' ? 503 : 200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    response.end(JSON.stringify(scenario === 'failure' ? {error:'availability_unavailable'} : {
      timestamp: new Date().toISOString(),
      locations: scenario === 'empty' ? [] : [{
        id:'10000000-0000-0000-0000-000000000001', name:'Synthetic QA fixture parking',
        capacity:5,occupied:0,available:5,outOfService:1
      }]
    }));
  };
  if (scenario === 'timeout') {
    const timer = setTimeout(send, 10000);
    response.on('close', () => clearTimeout(timer));
  } else if (scenario === 'slow') {
    setTimeout(send, 4000);
  } else send();
});
server.listen(8081, '127.0.0.1', () => console.log('Synthetic browser QA API on 127.0.0.1:8081; not the real backend.'));
