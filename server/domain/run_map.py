"""
领域层：roguelike 路线地图模型与推进规则。

本模块只包含纯数据模型与纯函数，不依赖 WebSocket、数据库或文件 IO。
"""

import random
import uuid
from pydantic import BaseModel, Field
from server.config import REALM_CONFIG


ROUTE_LABELS = ("清修路", "赌命路", "因果路")
NODE_TYPES = ("cultivation", "temptation", "gamble", "shop", "heaven", "karma_echo", "rest")

NODE_TYPE_LABELS = {
    "cultivation": "修炼",
    "temptation": "诱惑",
    "gamble": "赌命",
    "shop": "黑市",
    "heaven": "天道",
    "karma_echo": "因果",
    "rest": "休整",
}

NODE_POOL_BY_TYPE = {
    "cultivation": "cultivation",
    "temptation": "temptation",
    "gamble": "gamble",
    "shop": "merit",
    "heaven": "heaven_gaze",
    "karma_echo": "karma_echo",
    "rest": "merit",
}

RISK_LEVEL_BY_TYPE = {
    "cultivation": "low",
    "temptation": "medium",
    "gamble": "high",
    "shop": "low",
    "heaven": "high",
    "karma_echo": "medium",
    "rest": "low",
}


class RunMapNode(BaseModel):
    """路线地图中的单个节点。

    Args:
        node_id: 节点唯一 ID。
        chapter: 所属章节，对应当前境界代号。
        layer: 章节内层数，从 0 开始。
        route_index: 三路中的索引，0/1/2。
        node_type: 节点类型，决定事件池、风险和是否触发天道事件。

    Returns:
        RunMapNode: 可序列化节点模型。

    Side Effects:
        无副作用。
    """
    node_id: str
    chapter: int
    layer: int
    route_index: int
    route_label: str
    node_type: str
    node_label: str
    event_pool: str
    risk_level: str
    reward_multiplier: float = 1.0
    risk_multiplier: float = 1.0
    tick_budget: int = 2
    title: str = ""
    summary: str = ""


class RunMap(BaseModel):
    """当局 roguelike 路线地图状态。

    Args:
        run_map_id: 当局地图唯一 ID。
        nodes: 所有章节节点。
        current_chapter: 当前章节，对应玩家境界代号。
        current_node_id: 当前正在执行的节点 ID，空表示等待选路。
        available_next_nodes: 当前可选择的下一批节点 ID。
        visited_nodes: 已完成节点 ID。
        route_notice: 路线耗尽、刷新等一次性提示文案。
        route_notice_level: 提示等级，供前端决定展示样式。

    Returns:
        RunMap: 可挂载到 PlayerState 的地图快照。

    Side Effects:
        无副作用；推进必须通过本模块函数返回的新状态完成。
    """
    run_map_id: str = ""
    nodes: list[RunMapNode] = Field(default_factory=list)
    current_chapter: int = 1
    current_node_id: str = ""
    available_next_nodes: list[str] = Field(default_factory=list)
    visited_nodes: list[str] = Field(default_factory=list)
    route_notice: str = ""
    route_notice_level: str = ""

    def node_by_id(self, node_id: str) -> RunMapNode | None:
        """按 ID 查找节点；找不到时返回 None。"""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None


def generate_run_map(rng: random.Random | None = None) -> RunMap:
    """生成一局 3 路、每境界 3-5 层的 roguelike 路线地图。

    Args:
        rng: 可选随机源，测试可传固定种子。

    Returns:
        RunMap: 初始地图，第一章第一层三个节点可选。

    Side Effects:
        无业务副作用；未传 rng 时会读取全局随机源。
    """
    rng = rng or random
    run_map_id = f"run_{uuid.uuid4().hex[:8]}"
    nodes = []
    for chapter in range(1, 7):
        depth = rng.randint(3, 5)
        nodes.extend(_build_chapter_nodes(run_map_id, chapter, depth, rng))
    first_nodes = [
        node.node_id for node in nodes
        if node.chapter == 1 and node.layer == 0
    ]
    return RunMap(
        run_map_id=run_map_id,
        nodes=nodes,
        current_chapter=1,
        available_next_nodes=first_nodes,
    )


def open_chapter_choices(run_map: RunMap, chapter: int):
    """打开指定章节第一层路线选择。

    Args:
        run_map: 当局路线地图。
        chapter: 目标章节，对应玩家当前境界代号。

    Returns:
        None: 本函数直接更新传入地图。

    Side Effects:
        会清空当前节点，并把目标章节第一层节点设为可选。
    """
    run_map.current_chapter = max(1, min(6, chapter))
    run_map.current_node_id = ""
    run_map.available_next_nodes = [
        node.node_id for node in run_map.nodes
        if node.chapter == run_map.current_chapter and node.layer == 0
    ]


def choose_run_node(run_map: RunMap, node_id: str) -> tuple[bool, str]:
    """选择一个当前可用节点并进入执行状态。

    Args:
        run_map: 当局路线地图。
        node_id: 玩家选择的节点 ID。

    Returns:
        tuple[bool, str]: 是否成功，以及失败原因或空字符串。

    Side Effects:
        成功时会更新 run_map 的当前节点与可选节点列表。
    """
    if node_id not in run_map.available_next_nodes:
        return False, "节点不可选"
    node = run_map.node_by_id(node_id)
    if not node:
        return False, "节点不存在"
    run_map.current_node_id = node_id
    run_map.current_chapter = node.chapter
    run_map.available_next_nodes = []
    run_map.route_notice = ""
    run_map.route_notice_level = ""
    return True, ""


def complete_current_node(run_map: RunMap) -> RunMapNode | None:
    """完成当前节点并解锁下一层节点。

    Args:
        run_map: 当局路线地图。

    Returns:
        RunMapNode | None: 被完成的节点；没有当前节点时返回 None。

    Side Effects:
        会追加 visited_nodes，并刷新 available_next_nodes。
    """
    node = run_map.node_by_id(run_map.current_node_id)
    if not node:
        return None
    if node.node_id not in run_map.visited_nodes:
        run_map.visited_nodes.append(node.node_id)
    run_map.current_node_id = ""
    run_map.available_next_nodes = _next_node_ids(run_map, node)
    return node


def snapshot_run_map(run_map: RunMap) -> dict:
    """生成前端可直接渲染的路线地图快照。

    Args:
        run_map: 当局路线地图。

    Returns:
        dict: 包含地图、当前节点、可选节点和节点状态的传输结构。

    Side Effects:
        无副作用。
    """
    available = set(run_map.available_next_nodes)
    visited = set(run_map.visited_nodes)
    current = run_map.current_node_id
    return {
        "run_map_id": run_map.run_map_id,
        "current_chapter": run_map.current_chapter,
        "current_node_id": current,
        "available_next_nodes": list(run_map.available_next_nodes),
        "visited_nodes": list(run_map.visited_nodes),
        "route_notice": run_map.route_notice,
        "route_notice_level": run_map.route_notice_level,
        "chapters": _snapshot_chapters(run_map, available, visited, current),
    }


def _build_chapter_nodes(
    run_map_id: str,
    chapter: int,
    depth: int,
    rng: random.Random,
) -> list[RunMapNode]:
    nodes = []
    guaranteed = {0: "cultivation", 1: "gamble", depth - 1: "shop"}
    for layer in range(depth):
        for route_index, route_label in enumerate(ROUTE_LABELS):
            node_type = _pick_node_type(layer, route_index, guaranteed, rng)
            nodes.append(_make_node(run_map_id, chapter, layer, route_index, route_label, node_type))
    return nodes


def _pick_node_type(layer: int, route_index: int, guaranteed: dict[int, str], rng: random.Random) -> str:
    if route_index == 1 and layer in guaranteed:
        return guaranteed[layer]
    weighted = ("cultivation", "temptation", "gamble", "karma_echo", "rest", "heaven")
    return rng.choice(weighted)


def _make_node(
    run_map_id: str,
    chapter: int,
    layer: int,
    route_index: int,
    route_label: str,
    node_type: str,
) -> RunMapNode:
    prefix = f"{run_map_id}_c{chapter}_l{layer}_r{route_index}"
    reward, risk = _node_multipliers(node_type)
    return RunMapNode(
        node_id=prefix,
        chapter=chapter,
        layer=layer,
        route_index=route_index,
        route_label=route_label,
        node_type=node_type,
        node_label=NODE_TYPE_LABELS[node_type],
        event_pool=NODE_POOL_BY_TYPE[node_type],
        risk_level=RISK_LEVEL_BY_TYPE[node_type],
        reward_multiplier=reward,
        risk_multiplier=risk,
        tick_budget=1 if node_type in ("shop", "heaven", "rest") else 2,
        title=_node_title(chapter, node_type),
        summary=_node_summary(node_type),
    )


def _node_multipliers(node_type: str) -> tuple[float, float]:
    if node_type == "gamble":
        return 1.8, 1.6
    if node_type == "temptation":
        return 1.4, 1.3
    if node_type == "heaven":
        return 1.2, 1.5
    if node_type == "rest":
        return 0.7, 0.5
    if node_type == "shop":
        return 0.8, 0.7
    return 1.0, 1.0


def _node_title(chapter: int, node_type: str) -> str:
    realm_name = REALM_CONFIG[chapter]["name"]
    return f"{realm_name}·{NODE_TYPE_LABELS[node_type]}"


def _node_summary(node_type: str) -> str:
    summaries = {
        "cultivation": "稳步修炼，收益平实。",
        "temptation": "收益更高，也更容易惹来天谴。",
        "gamble": "赌命换倍率，死相也更有节目效果。",
        "shop": "黑市短暂停留，局内只做轻量补给。",
        "heaven": "天道凝视，可能引出正式裁决。",
        "karma_echo": "前人因果回响，收益与污染并存。",
        "rest": "休整压险，修为收益较低。",
    }
    return summaries.get(node_type, "")


def _next_node_ids(run_map: RunMap, node: RunMapNode) -> list[str]:
    candidates = [
        item for item in run_map.nodes
        if item.chapter == node.chapter and item.layer == node.layer + 1
    ]
    if not candidates:
        candidates = [
            item for item in run_map.nodes
            if item.chapter == node.chapter + 1 and item.layer == 0
        ]
    route_min = max(0, node.route_index - 1)
    route_max = min(2, node.route_index + 1)
    return [
        item.node_id for item in candidates
        if route_min <= item.route_index <= route_max
    ]


def _snapshot_chapters(
    run_map: RunMap,
    available: set[str],
    visited: set[str],
    current: str,
) -> list[dict]:
    chapters = []
    for chapter in range(1, 7):
        nodes = [node for node in run_map.nodes if node.chapter == chapter]
        chapters.append({
            "chapter": chapter,
            "realm_name": REALM_CONFIG[chapter]["name"],
            "nodes": [_snapshot_node(node, available, visited, current) for node in nodes],
        })
    return chapters


def _snapshot_node(
    node: RunMapNode,
    available: set[str],
    visited: set[str],
    current: str,
) -> dict:
    data = node.model_dump()
    if node.node_id == current:
        data["status"] = "current"
    elif node.node_id in visited:
        data["status"] = "visited"
    elif node.node_id in available:
        data["status"] = "available"
    else:
        data["status"] = "locked"
    return data
