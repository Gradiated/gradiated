"""Independent calculations from public rendered states, without generator answers."""

import heapq
from fractions import Fraction


def sensor_posterior(state):
    yes = Fraction(state["prior_probability_incident"])
    no = 1 - yes
    for sensor in state["sensors"]:
        positive_yes = Fraction(sensor["p_positive_given_incident"])
        positive_no = Fraction(sensor["p_positive_given_no_incident"])
        if sensor["observed"] == "positive":
            yes *= positive_yes
            no *= positive_no
        elif sensor["observed"] == "negative":
            yes *= 1 - positive_yes
            no *= 1 - positive_no
        else:
            raise ValueError("unknown sensor observation")
    return {"incident_real": float(yes / (yes + no))}


def incident_replay(state):
    current = dict(state["initial_state"])
    events = sorted(state["events"], key=lambda event: event["ts"])
    cancelled = set()
    for event in reversed(events):
        if event["ts"] not in cancelled and event["kind"] == "void":
            cancelled.add(event["voids_ts"])
    for event in events:
        if event["ts"] in cancelled:
            continue
        kind = event["kind"]
        if kind == "assign":
            current["owner"] = event["owner"]
        elif kind == "severity":
            current["severity"] = event["severity"]
        elif kind in ("resolve", "reopen"):
            current["open"] = kind == "reopen"
        elif kind not in ("note", "void"):
            raise ValueError("unknown incident event")
    return {
        "current_owner": current["owner"],
        "current_severity": str(
            ["routine", "degraded", "critical"].index(current["severity"])
        ),
        "is_open": float(current["open"]),
    }


def route(state):
    edges = {node: [] for node in state["nodes"]}
    for edge in state["edges"]:
        if edge["open"]:
            if edge["cost"] <= 0:
                raise ValueError("nonpositive route cost")
            edges[edge["from"]].append((edge["to"], edge["cost"]))
    start, finish, via = state["start"], state["finish"], state.get("via")
    visited_via = via is None or start == via
    distances = {(start, visited_via): (0, "")}
    queue = [(0, "", start, visited_via)]
    while queue:
        cost, first, node, seen = heapq.heappop(queue)
        if distances[(node, seen)] != (cost, first):
            continue
        if node == finish and seen:
            return {
                "reachable": 1.0,
                "shortest_cost": str(cost),
                "first_hop": first or "none",
            }
        for destination, weight in edges[node]:
            next_seen = seen or destination == via
            value = (cost + weight, first or destination)
            key = (destination, next_seen)
            if key not in distances or value < distances[key]:
                distances[key] = value
                heapq.heappush(queue, (*value, destination, next_seen))
    return {"reachable": 0.0, "shortest_cost": "unreachable", "first_hop": "none"}


ORACLES = {
    "partial_observation_calibration": sensor_posterior,
    "event_state_reconstruction": incident_replay,
    "graph_navigation": route,
}
