import unittest

from semantic_oracles import incident_replay, route, sensor_posterior


class OracleTests(unittest.TestCase):
    def test_bayes_updates_use_negative_likelihood_and_prior(self):
        self.assertAlmostEqual(
            sensor_posterior(
                {
                    "prior_probability_incident": "1/2",
                    "sensors": [
                        {
                            "observed": "positive",
                            "p_positive_given_incident": "4/5",
                            "p_positive_given_no_incident": "1/5",
                        }
                    ],
                }
            )["incident_real"],
            0.8,
        )
        self.assertAlmostEqual(
            sensor_posterior(
                {
                    "prior_probability_incident": "1/2",
                    "sensors": [
                        {
                            "observed": "negative",
                            "p_positive_given_incident": "4/5",
                            "p_positive_given_no_incident": "1/5",
                        }
                    ],
                }
            )["incident_real"],
            0.2,
        )

    def test_replay_ignores_stale_snapshot_and_cancelled_assignment(self):
        state = {
            "initial_state": {"owner": "alice", "open": True, "severity": "routine"},
            "stale_snapshot": {"owner": "bob", "open": True},
            "events": [
                {"ts": 3, "kind": "resolve"},
                {"ts": 2, "kind": "void", "voids_ts": 1},
                {"ts": 1, "kind": "assign", "owner": "bob"},
            ],
        }
        self.assertEqual(
            incident_replay(state),
            {"current_owner": "alice", "current_severity": "0", "is_open": 0},
        )

    def test_cheapest_route_must_visit_via_and_break_first_hop_ties(self):
        state = {
            "nodes": ["a", "b", "c", "d"],
            "start": "a",
            "finish": "d",
            "via": "b",
            "edges": [
                {"from": "a", "to": "d", "cost": 1, "open": True},
                {"from": "a", "to": "b", "cost": 2, "open": True},
                {"from": "b", "to": "d", "cost": 2, "open": True},
                {"from": "a", "to": "c", "cost": 1, "open": True},
                {"from": "c", "to": "b", "cost": 1, "open": True},
            ],
        }
        self.assertEqual(
            route(state), {"reachable": 1, "shortest_cost": "4", "first_hop": "b"}
        )


if __name__ == "__main__":
    unittest.main()
