"""
南向资金预加载定时任务配置
使用 APScheduler 实现
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from southbound_preload import run_preload_job, load_memory_cache_from_db
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局调度器
_scheduler = None

def init_preload_scheduler():
    """
    初始化预加载定时任务
    在Flask启动时调用
    """
    global _scheduler
    
    if _scheduler is not None:
        logger.info("[Scheduler] 已初始化，跳过")
        return _scheduler
    
    # 1. 启动时加载内存缓存
    load_memory_cache_from_db()
    
    # 2. 创建后台调度器
    _scheduler = BackgroundScheduler()
    
    # 3. 配置定时任务
    jobs = [
        # 开盘前预加载（09:00，周一到周五）
        {
            'id': 'preload_morning',
            'trigger': CronTrigger(hour=9, minute=0, day_of_week='mon-fri'),
            'func': run_preload_job,
            'replace_existing': True
        },
        # 午休更新（12:00，周一到周五）
        {
            'id': 'preload_noon',
            'trigger': CronTrigger(hour=12, minute=0, day_of_week='mon-fri'),
            'func': run_preload_job,
            'replace_existing': True
        },
        # 收盘后更新（15:35，周一到周五）
        {
            'id': 'preload_evening',
            'trigger': CronTrigger(hour=15, minute=35, day_of_week='mon-fri'),
            'func': run_preload_job,
            'replace_existing': True
        },
        # 晚间补充（20:00，周一到周五）- 确保数据完整
        {
            'id': 'preload_night',
            'trigger': CronTrigger(hour=20, minute=0, day_of_week='mon-fri'),
            'func': run_preload_job,
            'replace_existing': True
        }
    ]
    
    for job in jobs:
        _scheduler.add_job(**job)
        logger.info(f"[Scheduler] 添加任务: {job['id']} -> {job['trigger']}")
    
    # 4. 启动调度器
    _scheduler.start()
    logger.info("[Scheduler] 预加载定时任务已启动")
    
    return _scheduler

def stop_preload_scheduler():
    """停止定时任务"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("[Scheduler] 已停止")

if __name__ == "__main__":
    # 测试定时任务
    import time
    init_preload_scheduler()
    print("调度器已启动，按Ctrl+C停止")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_preload_scheduler()
