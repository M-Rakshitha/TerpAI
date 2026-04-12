import json

import requests

resp = requests.post(
    'http://127.0.0.1:8020/api/query',
    json={'message': 'what to have for dinner near reckord armory under $15', 'debug_trace_context': True},
    timeout=180,
)
resp.raise_for_status()
obj = resp.json()
payload = obj.get('results', {}) if isinstance(obj, dict) else {}
dining = payload.get('dining') or {}
navigator = payload.get('navigator') or {}
print('request_id', obj.get('request_id'))
print('agents_used', obj.get('agents_used'))
print('dining_sources', dining.get('data_sources'))
print('navigator_origin', navigator.get('origin'))
print('dining_options', [o.get('name') for o in (dining.get('options') or [])[:5]])
