"""Hide twin bookkeeping names from the agent (loop batch b01 review). Idempotent; backs up each file once.

    python3 patch_display_names.py /opt/posthog-env

- agent_driver.py: PostHog AI's system prompt gets project_name / organization_name from POSTHOG_ENV_PROJECT_NAME /
  POSTHOG_ENV_ORG_NAME (defaults "Default project" / "Default organization") instead of the twin's bookkeeping names
  ("Twin2 <uuid>"), which made models ask whether they were in the wrong project.
- loader/load_twin_v2.py: new twin teams are named "Default project" (sub-model prompts read team.name directly).
  Twins are identified by the organization-name prefix, which is unchanged.
Existing teams are renamed separately (rename_twin_teams.sql).
"""

import os
import shutil
import sys

base = sys.argv[1]


def patch(path, marker, old, new):
    bak = path + ".before-names-20261030"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    s = open(path).read()
    if marker in s:
        print(os.path.basename(path), "already patched")
        return
    assert s.count(old) == 1, (path, s.count(old))
    open(path, "w").write(s.replace(old, new))
    print(os.path.basename(path), "patched")


patch(f"{base}/agent_driver.py", "def install_display_names", """def install_models(root: str, submodels: str) -> None:""",
      """def install_display_names() -> None:
    \"\"\"[NAMES PATCH 2026-10-30] Neutral project/organization names in PostHog AI's prompt (the twin's bookkeeping names
    leak that it is a synthetic copy). Revert: restore agent_driver.py.before-names-20261030.\"\"\"
    from ee.hogai.llm import MaxChatMixin

    orig = MaxChatMixin._get_project_org_user_variables

    def _vars(self):
        v = orig(self)
        v["project_name"] = os.environ.get("POSTHOG_ENV_PROJECT_NAME", "Default project")
        v["organization_name"] = os.environ.get("POSTHOG_ENV_ORG_NAME", "Default organization")
        return v

    MaxChatMixin._get_project_org_user_variables = _vars


def install_models(root: str, submodels: str) -> None:""")
patch(f"{base}/agent_driver.py", "    install_display_names()\n", """    install_usage_tracking()
    stub_external_services()""", """    install_usage_tracking()
    stub_external_services()
    install_display_names()""")
patch(f"{base}/loader/load_twin_v2.py", 'team_fields={"name": "Default project"', """team_fields={"name": f"Twin2 {self.twin_id[:12]}", "timezone": tz}""",
      """team_fields={"name": "Default project", "timezone": tz}""")
