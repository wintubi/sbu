"""Offline reproduction of the pre-send budget gap; no real API key/network.
Run at the local-life-travel root: python openspec/changes/travel-runtime-budget/evidence/reproduce_budget.py
The JSON records observations, not a passing acceptance test for a fix.
"""
from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
import httpx
from app.amap_tools import AmapClient,AmapAdapter
from app.domain import LiveTravelRequest
import app.live as live
from app.store import Store

body={'mode':'live','city':'北京','date':'2026-11-09','timezone':'Asia/Shanghai','origin':'合成出发地',
      'time_window':{'start':'2026-11-09T09:00:00+08:00','end':'2026-11-09T18:00:00+08:00'},
      'transport':'walking','candidates':[{'name':name,'stay_seconds':600} for name in ['合成甲','合成乙','合成丙']]}
paths=[]
def handler(request):
    paths.append(request.url.path)
    if request.url.path=='/v3/geocode/geo':
        return httpx.Response(200,json={'status':'1','geocodes':[{'location':'116.4,39.9','city':'北京','adcode':'110000'}]})
    if request.url.path=='/v3/place/text':
        name=request.url.params['keywords']
        return httpx.Response(200,json={'status':'1','pois':[{'id':name,'name':name,'cityname':'北京','location':'116.4,39.9'}]})
    raise AssertionError('unexpected path')

old_limit=live.LIVE_MAX_TOOL_CALLS
client=AmapClient(key='synthetic-example',transport=httpx.MockTransport(handler))
try:
    live.LIVE_MAX_TOOL_CALLS=2
    with tempfile.TemporaryDirectory(prefix='travel-budget-reproduction-') as directory:
        store=Store(str(Path(directory)/'isolated.sqlite3'))
        try:
            run,created=live.create_live_run(store,LiveTravelRequest.model_validate(body),
                lambda city,transport:AmapAdapter(client,city=city,transport=transport),'synthetic-budget-reproduction')
            saved=store.get_run(run['run_id'])
            observation={'scope':'offline MockTransport; synthetic data; current baseline behavior, not a fix',
                         'limit':2,'transport_attempts':len(paths),'client_calls':client.calls,
                         'persisted_count':saved['budget']['tool_calls'],'run_status':saved['status'],
                         'budget_status':saved['budget']['status'],'path_categories':paths,
                         'issue_codes':[i['code'] for i in saved['state']['issues']],
                         'oversent':len(paths)>2}
        finally:store.close()
finally:
    client.close();live.LIVE_MAX_TOOL_CALLS=old_limit
print(json.dumps(observation,ensure_ascii=False))
