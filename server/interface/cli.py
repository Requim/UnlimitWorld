"""
M1 CLI 适配器：控制台交互循环

通过 input() 接收玩家骚话，sys.stdout.write 模拟打字机效果。
使用与 M2 WebSocket 完全相同的 application/ 层接口。
"""

import sys
import asyncio
import random

from server.application.game_engine import GameEngine, Stage, TickResult
from server.application.heaven_persona import PERSONA_NAMES


# ═══════════════════════════════════════════════════════════════
# 控制台颜色（Windows 兼容）
# ═══════════════════════════════════════════════════════════════

def _setup_windows_console():
    """启用 Windows 终端 ANSI 颜色支持"""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GOLD = "\033[33m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    YELLOW = "\033[93m"


# ═══════════════════════════════════════════════════════════════
# 打字机效果
# ═══════════════════════════════════════════════════════════════

async def typewriter_print(text: str, delay: float = 0.03, color: str = Colors.RESET):
    """逐字打印，模拟打字机效果"""
    sys.stdout.write(color)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        await asyncio.sleep(random.uniform(delay * 0.5, delay * 1.5))
    sys.stdout.write(Colors.RESET + "\n")
    sys.stdout.flush()


# ═══════════════════════════════════════════════════════════════
# 显示组件
# ═══════════════════════════════════════════════════════════════

def display_status(result: TickResult):
    """显示玩家当前状态栏"""
    sin_color = Colors.RESET
    if result.sin_phase == "warning":
        sin_color = Colors.YELLOW
    elif result.sin_phase == "danger":
        sin_color = Colors.RED

    print(f"\n{Colors.DIM}{'─' * 60}{Colors.RESET}")
    print(f"  {Colors.BOLD}{result.realm}{Colors.RESET}  |  "
          f"修为: {Colors.GOLD}{result.cultivation:,}{Colors.RESET}  |  "
          f"天谴: {sin_color}{result.sin_value}{Colors.RESET}  |  "
          f"气运: {result.luck}  |  根基: {result.foundation}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")


def display_trigger(trigger) -> list:
    """显示天道事件弹窗，返回 [A/B/C]"""
    print(f"\n{Colors.MAGENTA}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}⚡ 天道降临！人格：【{trigger.heaven_persona}】{Colors.RESET}")
    print(f"{Colors.MAGENTA}{'═' * 60}{Colors.RESET}")

    if trigger.karma_brief:
        print(f"\n{Colors.CYAN}💀 前世因果：{trigger.karma_brief}{Colors.RESET}\n")

    for opt in trigger.fixed_options:
        print(f"  {Colors.GREEN}[{opt['id']}]{Colors.RESET} {opt['text']}")

    if trigger.allow_custom_input:
        print(f"  {Colors.GREEN}[C]{Colors.RESET} 逆天改命 —— 自由输入骚话对线！")

    print(f"\n{Colors.DIM}（输入 A / B / C 或直接输入骚话，60秒超时）{Colors.RESET}")

    return [opt["id"] for opt in trigger.fixed_options] + (["C"] if trigger.allow_custom_input else [])


# ═══════════════════════════════════════════════════════════════
# CLI 主循环
# ═══════════════════════════════════════════════════════════════

async def cli_main():
    """M1 控制台主入口"""
    _setup_windows_console()

    print(f"{Colors.BOLD}{Colors.GOLD}")
    print("╔══════════════════════════════════════════════════╗")
    print("║       天 道 不 正 经  —  M1  CLI  原 型         ║")
    print("║    大模型因果沙盒修仙肉鸽 · 控制台版              ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")

    # ── 开局设置 ──
    player_name = input(f"{Colors.GREEN}请输入修士大名（回车默认'张大仙'）: {Colors.RESET}").strip()
    if not player_name:
        player_name = "张大仙"

    print(f"\n{Colors.DIM}天道意志正在随机分配人格...{Colors.RESET}")
    await asyncio.sleep(0.5)

    engine = GameEngine()
    session = engine.new_game(player_name=player_name)

    print(f"\n{Colors.BOLD}🎭 本局天道人格：【{session.heaven_persona}】{Colors.RESET}")
    print(f"{Colors.DIM}初始属性 — 修为: {session.cultivation} | 天谴: {session.sin_value} | "
          f"气运: {session.luck} | 根基: {session.foundation}{Colors.RESET}")
    print(f"\n{Colors.DIM}{'─' * 60}{Colors.RESET}")
    print(f"{Colors.DIM}【玩法说明】{Colors.RESET}")
    print(f"{Colors.DIM}  - 按 Enter 推进挂机（每 10 秒一 tick）{Colors.RESET}")
    print(f"{Colors.DIM}  - 触发天道事件时输入 A/B/C 或自由骚话{Colors.RESET}")
    print(f"{Colors.DIM}  - 修行至渡劫期满 5000W 修为即可飞升{Colors.RESET}")
    print(f"{Colors.DIM}  - 暴毙或飞升后结算天道点{Colors.RESET}")
    print(f"{Colors.DIM}  - 输入 'quit' 退出游戏{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

    # ── 主循环 ──
    while engine.stage != Stage.GAME_OVER:
        if engine.stage == Stage.IDLE:
            # 等待玩家按 Enter 推进
            cmd = input(f"{Colors.GREEN}[按 Enter 挂机 / quit 退出] {Colors.RESET}").strip()

            if cmd.lower() == "quit":
                print(f"\n{Colors.DIM}你选择了逃避天道... coward.{Colors.RESET}")
                break

            # 执行 tick
            result = await engine.tick()

            if result.event_type == "LOCAL":
                # 本地日常事件
                print(f"{Colors.GOLD}{result.log_text}{Colors.RESET}")
                display_status(result)

            elif result.waiting_for_decision:
                # 天道事件触发
                valid_options = display_trigger(result.trigger)
                display_status(result)
                engine.stage = Stage.AWAIT_DECISION

        elif engine.stage == Stage.AWAIT_DECISION:
            # 接收玩家决策
            try:
                choice = await asyncio.wait_for(
                    _async_input(f"{Colors.GREEN}> {Colors.RESET}"),
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                print(f"\n{Colors.RED}⏰ 对线超时！天道降下'道心蒙尘'惩罚！{Colors.RESET}")
                timeout_result = engine.handle_timeout()
                print(f"{Colors.RED}{timeout_result.log_text}{Colors.RESET}")
                # 超时后自动选 A
                choice = "A"

            choice = choice.strip()
            if choice.lower() == "quit":
                print(f"\n{Colors.DIM}你在天道面前临阵脱逃...{Colors.RESET}")
                break

            # 判断是 A/B 还是自定义骚话
            valid_ids = [opt["id"] for opt in engine._current_trigger.fixed_options]
            if choice in valid_ids:
                choice_id = choice
                custom_text = ""
            else:
                choice_id = "C"
                custom_text = choice

            print(f"{Colors.MAGENTA}\n天道正在推演你的命运...{Colors.RESET}\n")

            # 流式输出
            result = await engine.submit_decision(choice_id, custom_text)

            if result.settlement:
                # 显示完整剧情
                await typewriter_print(result.settlement.story_text, delay=0.03, color=Colors.GREEN)
                print()

                if result.settlement.intercepted_by_shield:
                    print(f"{Colors.BOLD}{Colors.GOLD}🛡️ 因果遮蔽卡触发！太上老祖撕裂时空将你捞回！{Colors.RESET}\n")

                if result.is_dead:
                    print(f"{Colors.BOLD}{Colors.RED}💀 你死了！{Colors.RESET}")
                    print(f"   死因：{Colors.CYAN}{result.settlement.dead_title}{Colors.RESET}")
                    print(f"   存活时间：{engine.session.survival_seconds} 秒")
                    print(f"   获得天道点：{Colors.GOLD}{result.heaven_points_earned}{Colors.RESET}")
                elif result.game_over and not result.is_dead:
                    print(f"{Colors.BOLD}{Colors.GOLD}🌟 飞升成功！你已踏入大乘之境！{Colors.RESET}")
                    print(f"   获得天道点：{Colors.GOLD}{result.heaven_points_earned}{Colors.RESET}")
                    print(f"   尊号已永留仙尊名人堂！")
                else:
                    display_status(result)

            if result.game_over:
                break

        else:
            # 其他状态，回退到 IDLE
            engine.stage = Stage.IDLE

    # ── 游戏结束 ──
    print(f"\n{Colors.BOLD}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}  游戏结束。天道点余额：{Colors.GOLD}{engine.session.heaven_points}{Colors.RESET}")
    print(f"{Colors.BOLD}  死亡因果池收录：{len(engine._dead_registry)} 条死因{Colors.RESET}")
    print(f"{Colors.BOLD}  仙尊名人堂：{len(engine._immortal_hall)} 位飞升者{Colors.RESET}")
    print(f"{Colors.BOLD}{'═' * 60}{Colors.RESET}")
    print(f"\n{Colors.DIM}天道不正经 M1 CLI —— 感谢测试。下次带骚话来！{Colors.RESET}")


async def _async_input(prompt: str) -> str:
    """异步包装 input()，以便使用 asyncio.wait_for 实现超时"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, prompt)
