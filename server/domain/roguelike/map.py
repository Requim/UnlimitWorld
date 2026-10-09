"""九层路线地图规则。"""

from __future__ import annotations

from .errors import InvalidAction
from .models import MapNode, RunMap, RunState


LAYER_KINDS = [
    ["combat", "combat", "combat"],
    ["event", "combat", "event"],
    ["combat", "elite", "combat"],
    ["shop", "rest", "shop"],
    ["combat", "event", "combat"],
    ["elite", "combat", "elite"],
    ["event", "combat", "event"],
    ["rest", "shop", "rest"],
    ["boss"],
]


def generate_map() -> RunMap:
    """生成固定结构的九层有向地图；无入参和外部副作用。"""
    nodes: list[MapNode] = []
    previous: list[MapNode] = []
    for layer, kinds in enumerate(LAYER_KINDS, start=1):
        current = _build_layer(layer, kinds, previous)
        nodes.extend(current)
        previous = current
    for node in nodes:
        node.available = node.layer == 1
    return RunMap(nodes=nodes)


def _build_layer(layer: int, kinds: list[str], previous: list[MapNode]) -> list[MapNode]:
    result = []
    for lane, kind in enumerate(kinds):
        links = [node.id for node in previous if _is_adjacent(lane, len(kinds), node, len(previous))]
        result.append(MapNode(id=f"L{layer}N{lane}", layer=layer, lane=lane, kind=kind, links_from=links))
    return result


def _is_adjacent(lane: int, width: int, node: MapNode, previous_width: int) -> bool:
    if width == 1 or previous_width == 1:
        return True
    return abs(lane - node.lane) <= 1


def choose_node(run: RunState, node_id: str) -> MapNode:
    """锁定当前可达节点；会修改层数和地图，非法或越层选择抛 InvalidAction。"""
    if run.phase != "map" or run.map.current_node_id is not None:
        raise InvalidAction("当前不能选择路线节点")
    node = _find_node(run.map, node_id)
    if not node.available or node.layer != run.layer + 1:
        raise InvalidAction("节点尚未开放或不与当前路线相连")
    for item in run.map.nodes:
        item.available = False
    run.layer = node.layer
    run.map.current_node_id = node.id
    return node


def complete_current_node(run: RunState) -> None:
    """完成已锁定节点并开放相邻下一层；没有当前节点时仅回到地图阶段。"""
    current_id = run.map.current_node_id
    if current_id is None:
        run.phase = "map"
        return
    current = _find_node(run.map, current_id)
    current.completed = True
    run.map.current_node_id = None
    if current.layer < 9:
        _unlock_next(run.map, current)
        run.phase = "map"


def _unlock_next(run_map: RunMap, current: MapNode) -> None:
    for node in run_map.nodes:
        node.available = node.layer == current.layer + 1 and current.id in node.links_from


def _find_node(run_map: RunMap, node_id: str) -> MapNode:
    try:
        return next(node for node in run_map.nodes if node.id == node_id)
    except StopIteration as exc:
        raise InvalidAction("路线节点不存在") from exc
