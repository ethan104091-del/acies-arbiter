"""兩官意見不一致就辯論：把對方意見交給彼此重答，最多 MAX_ROUNDS 輪；仍不一致 → 爭議。"""
MAX_ROUNDS = 3


def same_verdict(a, b):
    return a["verdict"] == b["verdict"]


def agree(a, b):
    if a["verdict"] != b["verdict"]:
        return False
    if a["verdict"] == "改寫":
        # 改寫要在修訂文字上大致一致：條件與效果各自的字元二元組相似度
        from .checks import containment
        ra, rb = a.get("revision") or {}, b.get("revision") or {}
        return containment(ra.get("condition", ""), rb.get("condition", "")) >= 0.6 and \
               containment(ra.get("effect", ""), rb.get("effect", "")) >= 0.6
    return True


def run(ruling, checks, applications, ask, names=("claude", "codex"), log=print):
    """ask(name, ruling, checks, applications, role=, opponent=, round_=) → (review|None, info)。
    回傳 {"outcome": 定案|推翻|改寫|爭議|失敗, "final": review|None, "rounds": [...], "reviews": {name: review}}。"""
    roles = {names[0]: "審查官甲", names[1]: "審查官乙"}
    reviews, rounds, infos = {}, [], {}
    for n in names:
        r, info = ask(n, ruling, checks, applications, role=roles[n])
        infos[n] = info
        if r is None:
            log(f"  {n} 審查失敗：{info.get('json_error') or info.get('error')}")
            return {"outcome": "失敗", "final": None, "rounds": rounds, "reviews": reviews, "infos": infos}
        reviews[n] = r
    rounds.append({"round": 0, "reviews": dict(reviews)})
    a, b = names
    for k in range(1, MAX_ROUNDS + 1):
        if agree(reviews[a], reviews[b]):
            break
        log(f"  第 {k} 輪辯論：{a}={reviews[a]['verdict']}，{b}={reviews[b]['verdict']}")
        new = {}
        for me, other in ((a, b), (b, a)):
            r, info = ask(me, ruling, checks, applications, role=roles[me], opponent=reviews[other], round_=k)
            if r is None:
                return {"outcome": "失敗", "final": None, "rounds": rounds, "reviews": reviews, "infos": infos}
            new[me] = r
        reviews = new
        rounds.append({"round": k, "reviews": dict(reviews)})
    if agree(reviews[a], reviews[b]):
        return {"outcome": reviews[a]["verdict"], "final": reviews[a], "rounds": rounds, "reviews": reviews, "infos": infos}
    if same_verdict(reviews[a], reviews[b]):
        # 結論一致、修訂文字不同：請甲以雙方最後一輪修訂合成一份最終稿
        log("  結論一致但修訂文字不同：合稿")
        merged, info = ask(a, ruling, checks, applications, role=roles[a],
                           merge_of={"甲": {"revision": reviews[a].get("revision"), "amendment": reviews[a].get("amendment")},
                                     "乙": {"revision": reviews[b].get("revision"), "amendment": reviews[b].get("amendment")}})
        if merged is not None and merged["verdict"] == reviews[a]["verdict"]:
            rounds.append({"round": "合稿", "reviews": {a: merged}})
            return {"outcome": merged["verdict"], "final": merged, "rounds": rounds, "reviews": reviews, "infos": infos}
    return {"outcome": "爭議", "final": None, "rounds": rounds, "reviews": reviews, "infos": infos}
