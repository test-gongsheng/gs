import requests
import json

# 清空现有数据
resp = requests.post('http://localhost:8888/api/stocks/clear')
print(f'清空: {resp.status_code}')

# 导入12只持仓股（示例数据）
stocks = [
    {"code":"000559","name":"万向钱潮","market":"A股","avg_cost":7.5,"shares":10000,"current_price":7.2,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""},
    {"code":"000878","name":"云南铜业","market":"A股","avg_cost":12.0,"shares":8000,"current_price":11.5,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""},
    {"code":"002050","name":"三花智控","market":"A股","avg_cost":25.0,"shares":5000,"current_price":24.0,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""},
    {"code":"002594","name":"比亚迪","market":"A股","avg_cost":180.0,"shares":1000,"current_price":175.0,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P0","strategy_mode":"基础策略","notes":""},
    {"code":"00285","name":"比亚迪电子","market":"港股","avg_cost":30.0,"shares":5000,"current_price":28.5,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""},
    {"code":"00700","name":"腾讯控股","market":"港股","avg_cost":400.0,"shares":1000,"current_price":511.5,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P0","strategy_mode":"基础策略","notes":""},
    {"code":"09988","name":"阿里巴巴","market":"港股","avg_cost":80.0,"shares":2000,"current_price":125.7,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P0","strategy_mode":"基础策略","notes":""},
    {"code":"300229","name":"拓尔思","market":"A股","avg_cost":20.0,"shares":5000,"current_price":19.0,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""},
    {"code":"300316","name":"晶盛机电","market":"A股","avg_cost":35.0,"shares":4000,"current_price":33.0,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""},
    {"code":"300442","name":"润泽科技","market":"A股","avg_cost":45.0,"shares":3000,"current_price":42.0,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""},
    {"code":"601600","name":"中国铝业","market":"A股","avg_cost":6.5,"shares":15000,"current_price":6.2,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""},
    {"code":"688795","name":"摩尔线程","market":"A股","avg_cost":50.0,"shares":2000,"current_price":48.0,"axis_price":0,"base_position_pct":50,"float_position_pct":50,"trigger_pct":8,"stop_loss":0,"priority":"P2","strategy_mode":"基础策略","notes":""}
]

resp = requests.post('http://localhost:8888/api/stocks/batch', 
    json={'stocks': stocks, 'trades': []})
result = resp.json()
print(f'导入: success={result.get("success")}, count={result.get("count")}')

# 验证
resp = requests.get('http://localhost:8888/api/stocks')
data = resp.json()
print(f'\n验证: 后端返回 {len(data)} 只股票')
for s in data[:5]:
    print(f'  {s["code"]} {s["name"]}')
if len(data) > 5:
    print(f'  ... 共 {len(data)} 只')
