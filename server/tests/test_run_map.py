"""
run_map.py 单元测试：M4 roguelike 路线地图生成与推进。
"""
import random
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from server.domain.run_map import (
    choose_run_node,
    complete_current_node,
    generate_run_map,
    snapshot_run_map,
)


def test_generate_run_map_has_three_routes_and_core_node_types():
    run_map = generate_run_map(random.Random(7))
    first_chapter_nodes = [node for node in run_map.nodes if node.chapter == 1]
    node_types = {node.node_type for node in first_chapter_nodes}

    assert run_map.run_map_id.startswith("run_")
    assert len({node.route_index for node in first_chapter_nodes}) == 3
    assert 3 <= max(node.layer for node in first_chapter_nodes) + 1 <= 5
    assert {"cultivation", "gamble", "shop"}.issubset(node_types)
    assert len(run_map.available_next_nodes) == 3


def test_choose_and_complete_node_advances_available_nodes():
    run_map = generate_run_map(random.Random(3))
    first_node_id = run_map.available_next_nodes[1]

    ok, message = choose_run_node(run_map, first_node_id)
    completed = complete_current_node(run_map)

    assert ok is True
    assert message == ""
    assert completed.node_id == first_node_id
    assert first_node_id in run_map.visited_nodes
    assert run_map.current_node_id == ""
    assert len(run_map.available_next_nodes) >= 2
    assert all(run_map.node_by_id(node_id).layer == 1 for node_id in run_map.available_next_nodes)


def test_choose_rejects_locked_node():
    run_map = generate_run_map(random.Random(5))
    locked = next(node for node in run_map.nodes if node.layer > 0)

    ok, message = choose_run_node(run_map, locked.node_id)

    assert ok is False
    assert "不可选" in message


def test_snapshot_marks_node_statuses():
    run_map = generate_run_map(random.Random(9))
    first_node_id = run_map.available_next_nodes[0]
    choose_run_node(run_map, first_node_id)

    snapshot = snapshot_run_map(run_map)
    statuses = {
        node["node_id"]: node["status"]
        for chapter in snapshot["chapters"]
        for node in chapter["nodes"]
    }

    assert snapshot["current_node_id"] == first_node_id
    assert statuses[first_node_id] == "current"
