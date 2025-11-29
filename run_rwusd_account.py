# -*- coding: utf-8 -*-
"""
RWUSD交易循环启动脚本
支持按账号配置（api_key、api_secret、proxy）

使用方法:
    python scripts/run_rwusd_account.py --account-id account1 --api-key YOUR_KEY --api-secret YOUR_SECRET
    或使用环境变量:
        export ACCOUNT_ID=account1
        export BINANCE_API_KEY=YOUR_KEY
        export BINANCE_API_SECRET=YOUR_SECRET
        python scripts/run_rwusd_account.py

配置到crontab示例:
    # 每小时的 01分执行
    1 * * * * /usr/bin/python3 /path/to/project/scripts/run_rwusd_account.py --account-id account1 --api-key KEY --api-secret SECRET --proxy http://xxx.com --per-round-amount 20 --target-amount 1000 >> /var/log/rwusd_account1.log 2>&1
    python xxx > log_$(date +%Y%m%d).log 2>&1
"""
import os
import sys
import argparse
from pathlib import Path
from typing import Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from mybian.app.rwusd_service import get_rwusd_service
from mybian.common.log_utils import setup_logging, get_logger
from mybian.common.lock_utils import LockFile


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='RWUSD交易循环启动脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--account-id',
        type=str,
        required=True,
        help='账号标识（必填，用于区分不同账号）'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='币安API密钥（可选，也可通过环境变量BINANCE_API_KEY设置）'
    )
    
    parser.add_argument(
        '--api-secret',
        type=str,
        default=None,
        help='币安API密钥（可选，也可通过环境变量BINANCE_API_SECRET设置）'
    )
    
    parser.add_argument(
        '--proxy',
        type=str,
        default=None,
        help='代理地址（可选，格式: http://user:pass@host:port 或 http://host:port，也可通过环境变量BINANCE_PROXY设置）'
    )
    
    parser.add_argument(
        '--per-round-amount',
        type=float,
        default=10.0,
        help='单轮最大金额（USDT），默认10'
    )
    
    parser.add_argument(
        '--target-amount',
        type=float,
        default=None,
        help='目标操作金额（USDT），如果达到则停止，默认不限制'
    )
    
    parser.add_argument(
        '--retry-wait-seconds',
        type=int,
        default=5,
        help='中断条件发生时，等待重试的秒数，默认5秒'
    )
    
    parser.add_argument(
        '--must-profit',
        action='store_true',
        default=True,
        help='是否必须盈利（仅在有免费额度时生效，USDC/USDT价格必须>1.0），默认True'
    )
    
    parser.add_argument(
        '--no-must-profit',
        dest='must_profit',
        action='store_false',
        help='允许不盈利（与--must-profit相反，用于禁用必须盈利的要求）'
    )
    
    parser.add_argument(
        '--lock-dir',
        type=str,
        default=None,
        help='标志文件目录（可选，默认使用项目根目录下的.locks目录）'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别，默认INFO'
    )
    
    parser.add_argument(
        '--log-file',
        type=str,
        default=None,
        help='日志文件路径（可选，默认只输出到控制台）'
    )
    
    return parser.parse_args()


def get_config_from_env_or_args(env_key: str, arg_value: Optional[str]) -> Optional[str]:
    """
    从环境变量或命令行参数获取配置
    
    Args:
        env_key: 环境变量名
        arg_value: 命令行参数值
        
    Returns:
        配置值
    """
    if arg_value:
        return arg_value
    return os.getenv(env_key)


def main():
    """主函数"""
    args = parse_args()
    
    # 初始化日志
    log_file_path = Path(args.log_file) if args.log_file else None
    setup_logging(log_level=args.log_level, log_file=log_file_path)
    logger = get_logger(__name__)
    
    logger.info("=" * 60)
    logger.info("RWUSD交易循环启动")
    logger.info(f"账号ID: {args.account_id}")
    logger.info("=" * 60)
    
    # 获取账号配置
    api_key = get_config_from_env_or_args('BINANCE_API_KEY', args.api_key)
    api_secret = get_config_from_env_or_args('BINANCE_API_SECRET', args.api_secret)
    proxy = get_config_from_env_or_args('BINANCE_PROXY', args.proxy)
    
    # 验证必要配置
    if not api_key or not api_secret:
        logger.error("API密钥和密钥必须配置（通过命令行参数或环境变量）")
        sys.exit(1)
    
    # 设置标志文件路径
    if args.lock_dir:
        lock_dir = Path(args.lock_dir)
    else:
        lock_dir = project_root / ".locks"
    
    lock_file_path = lock_dir / f"rwusd_{args.account_id}.lock"
    
    # 尝试获取标志文件锁
    try:
        with LockFile(lock_file_path, args.account_id):
            logger.info(f"成功获取标志文件锁: {lock_file_path}")
            
            # 创建服务实例
            service = get_rwusd_service(
                api_key=api_key,
                api_secret=api_secret,
                proxy=proxy
            )
            
            # 执行交易循环
            result = service.execute_trading_cycle(
                per_round_amount=args.per_round_amount,
                target_amount=args.target_amount,
                retry_wait_seconds=args.retry_wait_seconds,
                must_profit=args.must_profit
            )
            
            logger.info("=" * 60)
            logger.info("交易循环执行完成")
            logger.info(f"总循环数: {result['total_cycles']}")
            logger.info(f"总操作金额: {result['total_operated']:.4f} USDT")
            logger.info(f"总盈亏: {result['total_profit']:.4f} USDT")
            if result['total_operated'] > 0:
                logger.info(f"平均利润率: {result['avg_profit_rate']:.2f}%")
            logger.info("=" * 60)
            
    except RuntimeError as e:
        logger.error(f"无法获取标志文件锁: {e}")
        logger.error("可能已有其他进程正在处理该账号，退出")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("收到中断信号，正在退出...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

