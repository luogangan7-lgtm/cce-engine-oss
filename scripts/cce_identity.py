# -*- coding: utf-8 -*-
"""身份不变式(只许化名)的单一实现 —— 入口(scripts/cce_submission.py)与仓库扫描(tests/test_cce_no_real_identities.py)共用。

为什么要在入口查: 2026-09-28 诊断发现, 化名规则此前只在「仓库文件」和「归档时」检查, 入口只要求 actor_ref 字段存在。
于是真实论坛 handle 能随提交进到公开仓的 run artifact 和日志里(run 31993570335, 已删除并备份到本地保险库)。
边界必须设在进门处, 不是事后在归档时发现。

表来自 config/cce_identity_allowlists.json(由本地保险库的边界闸 check_boundary.py 落表; 与保险库的漂移检查在测试里, 只在有保险库的机器上跑)。
"""
import json
import os
import re

_V = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "cce_identity_allowlists.json"), encoding="utf-8"))
PSEUDONYM_PREFIXES = tuple(_V["pseudonym_prefixes"])
ID_FIELDS = {"actor_ref", "author", "username", "handle", "commenter", "op"}
MENTION_ALLOW = set(_V["mention_allow"])
ALLOW = set(_V["allow"]) | MENTION_ALLOW | {"", "None", "null"}
# 与边界闸同一条提及规则(u/xxx), 另加链接里的 /user/xxx(永久链接常带作者名)
MENTION = re.compile(r"(?:^|[^A-Za-z0-9_])u/([A-Za-z0-9_-]{3,20})")
USER_PATH = re.compile(r"/user/([A-Za-z0-9_-]{3,20})")


def is_pseudonym(v: str) -> bool:
    """actor_ref 之类的身份字段: 形如 reddit:u/user_47 · self_op · redacted_3 · creator_1, 或放行表里的公众人物/占位。"""
    tail = v.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return tail in ALLOW or v in ALLOW or any(tail.startswith(p) for p in PSEUDONYM_PREFIXES)


def real_mentions(text) -> list:
    """正文里的 u/xxx 与 /user/xxx 提及中, 不是化名的那些(返回名字本身, 只给调用方计数/报错用, 不要打印进公开日志)。"""
    if not isinstance(text, str):
        return []
    names = MENTION.findall(text) + USER_PATH.findall(text)
    return [n for n in names if not n.startswith(PSEUDONYM_PREFIXES) and n not in MENTION_ALLOW]
