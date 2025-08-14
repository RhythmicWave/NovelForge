from __future__ import annotations

from typing import Any, Dict, List
import re

class ConsistencyService:
    def check(self, text: str, facts_structured: Dict[str, Any] | str) -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        fixes: List[Dict[str, Any]] = []

        alias_table: Dict[str, List[str]] = {}
        relation_summaries: List[Dict[str, Any]] = []

        # 兼容旧入参为字符串情况（忽略）
        if isinstance(facts_structured, dict):
            alias_table = facts_structured.get('alias_table') or {}
            relation_summaries = facts_structured.get('relation_summaries') or []

        # 称谓一致性：若 alias_table 中存在推荐称谓（取别名表首个），检测正文中是否出现冲突称谓，给出替换建议
        for name, aliases in (alias_table or {}).items():
            if not isinstance(aliases, list) or not aliases:
                continue
            should = str(aliases[0]).strip()
            if not should:
                continue
            # 一组常见可能冲突的称谓（示例）
            bad_aliases = ["大哥", "老哥", "兄长", "大师兄", "兄弟", "师兄", "师弟", "道友"]
            for bad in bad_aliases:
                if bad != should and re.search(re.escape(name) + ".{0,6}" + re.escape(bad), text):
                    issues.append({
                        "type": "address_mismatch",
                        "message": f"{name} 应称为『{should}』，发现『{bad}』",
                    })
                    fixes.append({
                        "range": None,
                        "replacement": f"{bad}=>{should}"
                    })

        # 关系立场（占位轻量规则）：若正文中出现“亲密/敌对”等词与 relation.kind 强冲突，可提示偏差（示例，不严谨）
        for rel in (relation_summaries or []):
            try:
                a = str(rel.get('a') or '')
                b = str(rel.get('b') or '')
                kind = str(rel.get('kind') or '')
            except Exception:
                continue
            if not a or not b or not kind:
                continue
            # 简单词典：enemy 对应“亲密/友好”判为偏差；ally 对应“敌对/仇恨”判为偏差
            if kind == 'enemy' and re.search(fr"{re.escape(a)}.{0,12}{re.escape(b)}.*?(亲密|友好|信任)", text):
                issues.append({"type": "stance_deviation", "message": f"{a} 与 {b} 为敌对关系，正文出现亲密/友好表述"})
            if kind == 'ally' and re.search(fr"{re.escape(a)}.{0,12}{re.escape(b)}.*?(敌对|仇恨|憎恶)", text):
                issues.append({"type": "stance_deviation", "message": f"{a} 与 {b} 为同盟关系，正文出现敌对/仇恨表述"})

        # 数值/境界（极简示例）：若出现“不一致如：修为从 元婴 → 炼气 倒退”
        realms = ["炼气", "筑基", "结丹", "元婴", "化神", "炼虚", "合体", "大乘", "真仙"]
        realm_idx = {r: i for i, r in enumerate(realms)}
        found_realms = [r for r in realms if r in text]
        if len(found_realms) >= 2:
            first = None
            for r in found_realms:
                if first is None:
                    first = r
                else:
                    # 发现倒退（简单启发）
                    if realm_idx.get(r, 0) < realm_idx.get(first, 0):
                        issues.append({
                            "type": "realm_regression",
                            "message": f"修为出现倒退：前文『{first}』，后文『{r}』",
                        })
                        break

        # 简单数值一致性：捕捉“拥有(\d+)颗灵石”两次出现差异（极简，不定位范围）
        values = re.findall(r"拥有(\d+)颗灵石", text)
        if len(values) >= 2 and values[0] != values[-1]:
            issues.append({
                "type": "numeric_mismatch",
                "message": f"灵石数量前后不一致：{values[0]} → {values[-1]}",
            })

        return {"issues": issues, "suggested_fixes": fixes}
