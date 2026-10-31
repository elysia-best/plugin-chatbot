"""会话存储单元测试（可直接运行）。"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.messages import Message, ToolCall
from agent.store import SessionStore

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
    with tempfile.TemporaryDirectory() as root:
        store = SessionStore(root)

        # new_chat
        rec = store.new_chat(alias="alice")
        check("new_chat_returns_id", bool(rec.chat_id))
        check("new_chat_alias_bound", store.resolve("alice") == rec.chat_id)

        # exists / get
        check("exists_true", store.exists(rec.chat_id))
        check("get_returns_record", store.get(rec.chat_id) is not None)
        check("exists_false_unknown", not store.exists("deadbeef" * 6))

        # append + load roundtrip
        m1 = Message(role="user", content="hello")
        m2 = Message(role="assistant", content="world")
        m3 = Message(
            role="assistant",
            content="hi",
            tool_calls=[ToolCall(id="c1", name="Write", arguments={"a": 1})],
        )
        store.append(rec.chat_id, m1)
        store.append(rec.chat_id, m2)
        store.append(rec.chat_id, m3)
        store.save(rec.chat_id)
        loaded = store.load_messages(rec.chat_id)
        check("roundtrip_count", len(loaded) == 3)
        check(
            "roundtrip_content",
            loaded[0].content == "hello" and loaded[1].content == "world",
        )
        check(
            "roundtrip_toolcall",
            bool(loaded[2].tool_calls)
            and loaded[2].tool_calls[0].arguments == {"a": 1},
        )

        # save idempotent (no duplicate)
        store.save(rec.chat_id)
        loaded2 = store.load_messages(rec.chat_id)
        check("save_idempotent", len(loaded2) == 3)

        # 重启（新建 store 同 root）后仍可恢复
        store2 = SessionStore(root)
        check("restart_list", any(r.chat_id == rec.chat_id for r in store2.list()))
        loaded3 = store2.load_messages(rec.chat_id)
        check("restart_load", len(loaded3) == 3)
        check("restart_alias", store2.resolve("alice") == rec.chat_id)

        # list 有消息数
        check("list_has_count", store2.list()[0].message_count == 3)

        # delete
        check("delete_true", store2.delete(rec.chat_id))
        check("delete_removed", not store2.exists(rec.chat_id))
        check("delete_alias_cleared", store2.resolve("alice") is None)
        check("delete_unknown_false", not store2.delete("nope"))

        # 第二个 chat 隔离
        rec2 = store.new_chat(alias="bob")
        store.append(rec2.chat_id, Message(role="user", content="b1"))
        store.save(rec2.chat_id)
        check("isolation", len(store.load_messages(rec2.chat_id)) == 1)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
