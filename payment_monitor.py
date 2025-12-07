import asyncio
import logging
import aiohttp
from core.database import db
from core.config import settings
from aiogram import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - Monitor - %(levelname)s - %(message)s")
logger = logging.getLogger("PayMonitor")

bot = Bot(token=settings.BOT_TOKEN)

# TRON 官方公共节点 (或使用你自己的 key)
TRON_API = "https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

async def check_transactions():
    """轮询链上数据，匹配订单"""
    if not db.pg_pool: await db.connect()
    
    # 1. 获取收款地址
    async with db.pg_pool.acquire() as conn:
        wallet = await conn.fetchval("SELECT value FROM system_settings WHERE key='usdt_address'")
        # 获取所有 pending 订单
        orders = await conn.fetch("SELECT * FROM orders WHERE status='pending' AND expire_at > NOW()")
    
    if not wallet or not orders: return

    # 2. 请求 TronGrid (查询最近20条 TRC20 转账)
    try:
        url = TRON_API.format(address=wallet)
        params = {"limit": 20, "contract_address": USDT_CONTRACT, "only_confirmed": "true"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                
        if not data.get("data"): return
        
        # 3. 遍历链上交易
        for tx in data["data"]:
            # 过滤：必须是转入我钱包的
            if tx["to"] != wallet: continue
            
            # 金额转换 (链上是6位整数，转为浮点)
            amount = float(tx["value"]) / 1_000_000
            tx_hash = tx["transaction_id"]
            tx_time = int(tx["block_timestamp"]) / 1000
            
            # 4. 比对订单
            for order in orders:
                # 逻辑：金额一致 + 时间在订单创建之后
                order_time = order["created_at"].timestamp()
                
                # 容错：允许金额极其微小的误差? 不，TRC20通常是精确的
                if abs(float(order["amount"]) - amount) < 0.000001 and tx_time >= order_time:
                    # 匹配成功！
                    logger.info(f"💰 订单匹配成功: {order['order_no']} | Hash: {tx_hash}")
                    await process_success_order(order, tx_hash)
                    
    except Exception as e:
        logger.error(f"查链失败: {e}")

async def process_success_order(order, tx_hash):
    """处理成功订单：更新状态 -> 加会员 -> 通知"""
    async with db.pg_pool.acquire() as conn:
        # 1. 检查是否处理过 (防止重复入账)
        exists = await conn.fetchval("SELECT order_no FROM orders WHERE tx_hash = $1", tx_hash)
        if exists: return

        # 2. 更新订单
        await conn.execute("UPDATE orders SET status='paid', tx_hash=$1 WHERE order_no=$2", tx_hash, order['order_no'])
        
        # 3. 获取套餐时长
        plan = await conn.fetchrow("SELECT * FROM vip_plans WHERE id = $1", order['plan_id'])
        
        # 4. 加会员
        interval = f"{plan['duration']} {plan['unit']}s" # e.g. '30 days'
        await conn.execute(f"""
            UPDATE users 
            SET role='vip', 
                expire_at = CASE 
                    WHEN expire_at > NOW() THEN expire_at + INTERVAL '{interval}'
                    ELSE NOW() + INTERVAL '{interval}'
                END
            WHERE tg_id = $1
        """, order['user_id'])
        
    # 5. 发送通知
    await bot.send_message(order['user_id'], f"✅ <b>支付成功！</b>\n会员已自动开通。\n交易哈希: `{tx_hash}`", parse_mode="HTML")

async def main():
    logger.info("🚀 支付监控进程启动...")
    while True:
        await check_transactions()
        await asyncio.sleep(10) # 10秒查一次

if __name__ == "__main__":
    asyncio.run(main())