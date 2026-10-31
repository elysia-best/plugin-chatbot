"""权限与安全判定单元测试（可直接运行：python tests/test_permissions.py）。"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.permissions import PermissionContext, PermissionRule, default_rules

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}")


def main():
    with tempfile.TemporaryDirectory() as ws:
        with tempfile.TemporaryDirectory() as other:
            # read in workspace
            ctx = PermissionContext(workspace=ws)
            check(
                "read_in_ws_allow",
                ctx.check("Read", path=os.path.join(ws, "a.py"), category="read")
                == "allow",
            )

            # read outside
            check(
                "read_outside_ask",
                ctx.check("Read", path=os.path.join(other, "x.txt"), category="read")
                == "ask",
            )

            # write in ws default ask
            check(
                "write_in_ws_default_ask",
                ctx.check("Write", path=os.path.join(ws, "a.py")) == "ask",
            )

            # acceptEdits
            ctx2 = PermissionContext(workspace=ws, mode="acceptEdits")
            check(
                "accept_edits_allow",
                ctx2.check("Write", path=os.path.join(ws, "a.py")) == "allow",
            )

            # bypass
            ctx3 = PermissionContext(workspace=ws, mode="bypassPermissions")
            check("bypass_allow", ctx3.check("Bash", command="rm -rf /") == "allow")

            # dontAsk
            ctx4 = PermissionContext(workspace=ws, mode="dontAsk")
            check("dontask_deny", ctx4.check("Bash", command="ls") == "deny")

            # dangerous path protected even bypass
            check(
                "danger_git",
                ctx3.check("Write", path=os.path.join(ws, ".git", "config")) == "ask",
            )
            check(
                "danger_env",
                ctx3.check("Write", path=os.path.join(ws, ".env")) == "ask",
            )

            # deny rule priority
            ctx5 = PermissionContext(
                workspace=ws, rules=[PermissionRule(tool="Bash", behavior="deny")]
            )
            check("deny_rule", ctx5.check("Bash", command="ls") == "deny")

            # allow rule
            ctx6 = PermissionContext(
                workspace=ws, rules=[PermissionRule(tool="Write", behavior="allow")]
            )
            check(
                "allow_rule",
                ctx6.check("Write", path=os.path.join(ws, "a.py")) == "allow",
            )

            # additional dirs
            ctx7 = PermissionContext(workspace=ws, additional_dirs=[other])
            check(
                "additional_dir",
                ctx7.check("Read", path=os.path.join(other, "y.txt"), category="read")
                == "allow",
            )

            # path traversal
            outside = os.path.normpath(os.path.join(ws, "..", ".."))
            check(
                "traversal_ask",
                ctx.check("Read", path=os.path.join(outside, "x"), category="read")
                == "ask",
            )

            # wildcard pattern
            ctx8 = PermissionContext(
                workspace=ws,
                rules=[
                    PermissionRule(tool="Read", behavior="allow", pattern="./src/**")
                ],
            )
            check(
                "wildcard",
                ctx8.check(
                    "Read", path=os.path.join(ws, "src", "a.py"), category="read"
                )
                == "allow",
            )

            # default rules 只含只读安全工具（写/命令由模式决定）
            rules = default_rules()
            names = {r.tool for r in rules}
            check(
                "default_rules_read_only",
                {"Read", "Glob", "Grep", "WebFetch"} <= names,
            )
            check(
                "default_rules_no_write_rule",
                not {"Write", "Edit", "Bash"} & names,
            )

            # 模式实际行为（经 default_rules + check 综合判定）
            from agent import Agent

            ag = Agent(model="m", workspace=ws)
            check(
                "mode_default_read",
                ag._check_permission(
                    ag._tool_map["Read"], {"file_path": os.path.join(ws, "a.py")}
                )
                == "allow",
            )
            check(
                "mode_default_write",
                ag._check_permission(
                    ag._tool_map["Write"], {"file_path": os.path.join(ws, "a.py")}
                )
                == "ask",
            )
            check(
                "mode_default_bash",
                ag._check_permission(ag._tool_map["Bash"], {"command": "ls"}) == "ask",
            )
            ag2 = Agent(model="m", workspace=ws, permission_mode="acceptEdits")
            check(
                "mode_accept_edits_write",
                ag2._check_permission(
                    ag2._tool_map["Write"], {"file_path": os.path.join(ws, "a.py")}
                )
                == "allow",
            )
            ag3 = Agent(model="m", workspace=ws, permission_mode="bypassPermissions")
            check(
                "mode_bypass_bash",
                ag3._check_permission(ag3._tool_map["Bash"], {"command": "rm -rf /"})
                == "allow",
            )
            check(
                "mode_bypass_env",
                ag3._check_permission(
                    ag3._tool_map["Write"], {"file_path": os.path.join(ws, ".env")}
                )
                == "ask",
            )
            ag4 = Agent(model="m", workspace=ws, permission_mode="dontAsk")
            check(
                "mode_dontask_bash",
                ag4._check_permission(ag4._tool_map["Bash"], {"command": "ls"})
                == "deny",
            )

    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
