"""facts.py tests (synthetic text). Run: cd .../twingen/v2 && python3 -m unittest discover -s tests -p "test_facts.py"."""
import os
import sys
import unittest

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)
sys.path.insert(0, "/opt/posthog-sft/env-research/twins")
import facts  # noqa: E402

CTX = """<attached_context>
# Dashboard
The user is viewing this dashboard.

## Dashboard name: Garden sales (web)
Dashboard ID: 1648091
Dashboard URL: /dashboard/1648091
Description: Landing -> sign-up -> purchase

Dashboard insights:
Name: Daily sales by type
Insight ID: abcd1234
Description: daily sales
Insight URL: /insights/abcd1234

Query schema:
```json
{"kind": "HogQLQuery", "query": "SELECT 1"}
```

Name: Visitors
Insight ID: efgh5678
Insight URL: /insights/efgh5678
</attached_context> how is traffic?"""


class ContextObjects(unittest.TestCase):
    """b02 review: dashboards the user had open were created as empty stubs named "Dashboard" (no tiles, no queries)."""

    def test_dashboard_and_insights(self):
        o = facts.parse_context_objects(CTX)
        self.assertEqual(o["dashboards"]["1648091"]["name"], "Garden sales (web)")
        self.assertEqual([t["short_id"] for t in o["dashboards"]["1648091"]["tiles"]], ["abcd1234", "efgh5678"])
        self.assertEqual(o["insights"]["abcd1234"]["query"]["kind"], "HogQLQuery")
        self.assertIsNone(o["insights"]["efgh5678"]["query"])

    def test_no_context(self):
        self.assertEqual(facts.parse_context_objects("plain question"), {"insights": {}, "dashboards": {}})


if __name__ == "__main__":
    unittest.main()
