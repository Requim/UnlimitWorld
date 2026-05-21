"""
天道不正经 —— 全局配置管理

使用 pydantic-settings 从 .env 文件和环境变量读取配置。
严禁任何形式的 API Key 硬编码。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── 大模型 ──
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ── 应用环境 ──
    app_env: str = "development"

    # ── PRD 事件路由 ──
    prd_step_min: int = 2        # 每 tick PRD 累加最小值
    prd_step_max: int = 12       # 每 tick PRD 累加最大值

    # ── 暴毙公式 ──
    alpha: float = 3.0           # 天谴惩罚指数

    # ── 挂机参数 ──
    tick_interval: int = 10      # 每 tick 秒数
    offline_timeout: int = 600   # 离线超时释放 Task（秒）

    # ── 对线超时 ──
    decision_timeout: int = 60   # 玩家对线响应超时（秒）

    # ── 天道点结算 ──
    heaven_point_survive_divisor: float = 60.0
    heaven_point_cultivation_multiplier: float = 0.01

    # ── 大模型容错 ──
    llm_max_retries: int = 2     # 修复重试上限

    # ── 飞升门槛 ──
    ascension_cultivation: int = 50_000_000  # 渡劫期满修为 5000W

    # ── M2 服务器 ──
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    ws_heartbeat_interval: int = 30     # 服务端心跳检测间隔（秒）
    ws_connect_timeout: int = 120       # 客户端开局超时（秒）

    # ── M2 MySQL ──
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "tiandao"

    # ── M2 Redis ──
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # ── M2 怨念池 ──
    karma_pool_clean_interval: int = 600  # 怨念池清洗间隔（秒）
    karma_pool_top_n: int = 250           # 每次清洗保留精品数

    # ── M2 异步写回 ──
    session_flush_interval: int = 30      # Redis → MySQL 写回间隔（秒）

    # ── M3 微信小程序 ──
    wechat_appid: str = ""                # 小程序 AppID
    wechat_secret: str = ""               # 小程序 AppSecret
    wechat_msg_sec_check_enabled: bool = True  # 内容安全审查开关

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


# 境界配置：realm_code -> 元数据
REALM_CONFIG = {
    1: {  # 练气期
        "name": "练气期",
        "cultivation_base": 0,
        "cultivation_cap": 1_000,
        "cultivation_rate_min": 1,
        "cultivation_rate_max": 5,
        "base_death_rate": 0.05,
        "sin_max": 50,
        "prd_threshold": 60,      # 新手期高频 LLM 引导，约 8-9 tick 触发
    },
    2: {  # 筑基期
        "name": "筑基期",
        "cultivation_base": 1_000,
        "cultivation_cap": 8_000,
        "cultivation_rate_min": 10,
        "cultivation_rate_max": 20,
        "base_death_rate": 0.15,
        "sin_max": 60,
        "prd_threshold": 70,
    },
    3: {  # 金丹期
        "name": "金丹期",
        "cultivation_base": 8_000,
        "cultivation_cap": 50_000,
        "cultivation_rate_min": 50,
        "cultivation_rate_max": 100,
        "base_death_rate": 0.25,
        "sin_max": 70,
        "prd_threshold": 85,
    },
    4: {  # 元婴期
        "name": "元婴期",
        "cultivation_base": 50_000,
        "cultivation_cap": 400_000,
        "cultivation_rate_min": 200,
        "cultivation_rate_max": 500,
        "base_death_rate": 0.40,
        "sin_max": 80,
        "prd_threshold": 100,
    },
    5: {  # 化神期
        "name": "化神期",
        "cultivation_base": 400_000,
        "cultivation_cap": 5_000_000,
        "cultivation_rate_min": 1_000,
        "cultivation_rate_max": 3_000,
        "base_death_rate": 0.60,
        "sin_max": 90,
        "prd_threshold": 110,
    },
    6: {  # 渡劫期
        "name": "渡劫期",
        "cultivation_base": 5_000_000,
        "cultivation_cap": 50_000_000,
        "cultivation_rate_min": 10_000,
        "cultivation_rate_max": 30_000,
        "base_death_rate": 0.85,
        "sin_max": 100,
        "prd_threshold": 120,     # 最高境界最稀有，LLM 事件最史诗
    },
    7: {  # 大乘期（飞升）
        "name": "大乘期",
        "cultivation_base": 50_000_000,
        "cultivation_cap": float("inf"),
        "cultivation_rate_min": 0,
        "cultivation_rate_max": 0,
        "base_death_rate": 0.0,
        "sin_max": 100,
        "prd_threshold": 999,     # 飞升后不再触发 PRD
    },
}

# 境界名称到代号的反向映射
REALM_NAME_TO_CODE = {v["name"]: k for k, v in REALM_CONFIG.items()}


settings = Settings()
