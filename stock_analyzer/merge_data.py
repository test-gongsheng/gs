import pandas as pd
import os

data_dir = "/root/.openclaw/workspace/stock_analyzer/data"

# 读取所有CSV文件并合并
all_files = [f for f in os.listdir(data_dir) if f.endswith('.csv') and f != 'all_stocks_combined.csv']

dfs = []
for filename in all_files:
    filepath = os.path.join(data_dir, filename)
    df = pd.read_csv(filepath)
    dfs.append(df)
    print(f"读取: {filename} ({len(df)} 条)")

# 合并
if dfs:
    combined = pd.concat(dfs, ignore_index=True)
    
    # 确保列顺序一致
    expected_cols = ['date', 'stock_code', 'stock_name', 'market', 'open', 'high', 'low', 'close', 'volume']
    
    # 有些文件可能有code列，需要处理
    if 'code' in combined.columns and 'stock_code' not in combined.columns:
        combined['stock_code'] = combined['code'].str.replace(r'^(sh|sz)\.', '', regex=True)
    
    # 选择并排序列
    available_cols = [c for c in expected_cols if c in combined.columns]
    combined = combined[available_cols]
    
    # 保存
    combined_path = os.path.join(data_dir, "all_stocks_combined.csv")
    combined.to_csv(combined_path, index=False, encoding='utf-8-sig')
    
    print(f"\n{'='*60}")
    print(f"📊 合并完成: {len(dfs)} 只股票, {len(combined)} 条记录")
    print(f"📁 文件: {combined_path}")
    
    # 显示各股票记录数
    print(f"\n各股票数据统计:")
    for code in sorted(combined['stock_code'].unique()):
        name = combined[combined['stock_code']==code]['stock_name'].iloc[0]
        count = len(combined[combined['stock_code']==code])
        date_range = f"{combined[combined['stock_code']==code]['date'].min()} 至 {combined[combined['stock_code']==code]['date'].max()}"
        print(f"  {code} {name}: {count} 条 ({date_range})")
