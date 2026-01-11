"""工作流初始化

初始化内置工作流及其触发器。
"""

from sqlmodel import Session, select
from loguru import logger

from app.db.models import Workflow, WorkflowTrigger
from app.core.config import settings
from .registry import initializer


def _create_or_update_workflow(db: Session, name: str, description: str, dsl: dict, trigger_card_type: str, overwrite: bool):
    """创建或更新单个工作流及其触发器的辅助函数"""
    created_count = updated_count = skipped_count = 0
    
    # 处理工作流
    wf = db.exec(select(Workflow).where(Workflow.name == name)).first()
    if not wf:
        wf = Workflow(name=name, description=description, is_built_in=True, is_active=True, version=1, dsl_version=1, definition_json=dsl)
        db.add(wf)
        db.commit()
        db.refresh(wf)
        created_count += 1
        logger.info(f"已创建内置工作流: {name} (id={wf.id})")
    else:
        if overwrite:
            wf.definition_json = dsl
            wf.is_built_in = True
            wf.is_active = True
            wf.version = 1
            db.add(wf)
            db.commit()
            updated_count += 1
            logger.info(f"已更新内置工作流: {name} (id={wf.id})")
        else:
            skipped_count += 1
    
    # 处理触发器
    tg = db.exec(select(WorkflowTrigger).where(WorkflowTrigger.workflow_id == wf.id, WorkflowTrigger.trigger_on == "onsave")).first()
    if not tg:
        tg = WorkflowTrigger(workflow_id=wf.id, trigger_on="onsave", card_type_name=trigger_card_type, is_active=True)
        db.add(tg)
        db.commit()
        created_count += 1
        logger.info(f"已创建触发器: onsave -> {name}")
    else:
        if overwrite:
            tg.card_type_name = trigger_card_type
            tg.is_active = True
            db.add(tg)
            db.commit()
            updated_count += 1
            logger.info(f"已更新触发器: onsave -> {name}")
        else:
            skipped_count += 1
    
    return created_count, updated_count, skipped_count


@initializer(name="工作流", order=50)
def init_workflows(session: Session) -> None:
    """初始化内置工作流
    
    创建所有内置工作流及其触发器。
    行为受配置项 BOOTSTRAP_OVERWRITE 控制。
    
    Args:
        session: 数据库会话
    """
    overwrite = settings.bootstrap.should_overwrite
    total_created = total_updated = total_skipped = 0
    
    # ============ 工作流1: 世界观·转组织 ============
    name = "世界观"
    dsl = {
        "dsl_version": 1,
        "name": name,
        "nodes": [
            {"id": "readself", "type": "Card.Read", "params": {"target": "$self", "type_name": "世界观设定"}, "position": {"x": 40, "y": 80}},
            {"id": "foreachOrgs", "type": "List.ForEach", "params": {"listPath": "$.content.world_view.social_system.major_power_camps"}, "position": {"x": 460, "y": 80}},
            {"id": "upsertOrg", "type": "Card.UpsertChildByTitle", "params": {"cardType": "组织卡", "title": "{item.name}", "useItemAsContent": True}, "position": {"x": 460, "y": 260}},
            {"id": "clearSource", "type": "Card.ModifyContent", "params": {"setPath": "world_view.social_system.major_power_camps", "setValue": []}, "position": {"x": 880, "y": 260}}
        ],
        "edges": [
            {"id": "e-readself-foreachOrgs", "source": "readself", "target": "foreachOrgs", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreachOrgs-upsertOrg", "source": "foreachOrgs", "target": "upsertOrg", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-foreachOrgs-clearSource", "source": "foreachOrgs", "target": "clearSource", "sourceHandle": "r", "targetHandle": "l"}
        ]
    }
    c, u, s = _create_or_update_workflow(session, name, "从世界观的势力列表生成组织卡，并清空来源字段", dsl, "世界观设定", overwrite)
    total_created += c
    total_updated += u
    total_skipped += s

    # ============ 工作流2: 核心蓝图·落子卡与分卷 ============
    name2 = "核心蓝图"
    dsl2 = {
        "dsl_version": 1,
        "name": name2,
        "nodes": [
            {"id": "read_bp", "type": "Card.Read", "params": {"target": "$self", "type_name": "核心蓝图"}, "position": {"x": 40, "y": 80}},
            {"id": "foreach_volumes", "type": "List.ForEachRange", "params": {"countPath": "$.content.volume_count", "start": 1}, "position": {"x": 460, "y": 80}},
            {"id": "upsert_volume", "type": "Card.UpsertChildByTitle", "params": {"parent": "$projectRoot", "cardType": "分卷大纲", "title": "第{index}卷", "contentTemplate": {"volume_number": "{index}"}}, "position": {"x": 460, "y": 330}},
            {"id": "foreach_chars", "type": "List.ForEach", "params": {"listPath": "$.content.character_cards"}, "position": {"x": 880, "y": 80}},
            {"id": "upsert_char", "type": "Card.UpsertChildByTitle", "params": {"cardType": "角色卡", "title": "{item.name}", "contentPath": "item"}, "position": {"x": 880, "y": 260}},
            {"id": "foreach_scenes", "type": "List.ForEach", "params": {"listPath": "$.content.scene_cards"}, "position": {"x": 1300, "y": 80}},
            {"id": "upsert_scene", "type": "Card.UpsertChildByTitle", "params": {"cardType": "场景卡", "title": "{item.name}", "contentPath": "item"}, "position": {"x": 1300, "y": 260}},
            {"id": "clear_lists", "type": "Card.ModifyContent", "params": {"contentMerge": {"character_cards": [], "scene_cards": []}}, "position": {"x": 1720, "y": 170}}
        ],
        "edges": [
            {"id": "e-read_bp-foreach_volumes", "source": "read_bp", "target": "foreach_volumes", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreach_volumes-upsert_volume", "source": "foreach_volumes", "target": "upsert_volume", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-foreach_volumes-foreach_chars", "source": "foreach_volumes", "target": "foreach_chars", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreach_chars-upsert_char", "source": "foreach_chars", "target": "upsert_char", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-foreach_chars-foreach_scenes", "source": "foreach_chars", "target": "foreach_scenes", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreach_scenes-upsert_scene", "source": "foreach_scenes", "target": "upsert_scene", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-foreach_scenes-clear_lists", "source": "foreach_scenes", "target": "clear_lists", "sourceHandle": "r", "targetHandle": "l"}
        ]
    }
    c, u, s = _create_or_update_workflow(session, name2, "蓝图生成：创建顶层分卷与蓝图子级的角色/场景卡，并清空蓝图内列表", dsl2, "核心蓝图", overwrite)
    total_created += c
    total_updated += u
    total_skipped += s

    # ============ 工作流3: 分卷大纲·落子卡 ============
    name3 = "分卷大纲"
    dsl3 = {
        "dsl_version": 1,
        "name": name3,
        "nodes": [
            {"id": "read_vol", "type": "Card.Read", "params": {"target": "$self", "type_name": "分卷大纲"}, "position": {"x": 40, "y": 80}},
            {"id": "foreach_new_chars", "type": "List.ForEach", "params": {"listPath": "$.content.new_character_cards"}, "position": {"x": 460, "y": 80}},
            {"id": "upsert_char2", "type": "Card.UpsertChildByTitle", "params": {"cardType": "角色卡", "title": "{item.name}", "contentPath": "item"}, "position": {"x": 460, "y": 260}},
            {"id": "foreach_new_scenes", "type": "List.ForEach", "params": {"listPath": "$.content.new_scene_cards"}, "position": {"x": 880, "y": 80}},
            {"id": "upsert_scene2", "type": "Card.UpsertChildByTitle", "params": {"cardType": "场景卡", "title": "{item.name}", "contentPath": "item"}, "position": {"x": 880, "y": 260}},
            {"id": "foreach_stage", "type": "List.ForEachRange", "params": {"countPath": "$.content.stage_count", "start": 1}, "position": {"x": 1300, "y": 80}},
            {"id": "upsert_stage", "type": "Card.UpsertChildByTitle", "params": {"cardType": "阶段大纲", "title": "阶段{index}", "contentTemplate": {"stage_number": "{index}", "volume_number": "{$.content.volume_number}"}}, "position": {"x": 1300, "y": 260}},
            {"id": "upsert_guide", "type": "Card.UpsertChildByTitle", "params": {"cardType": "写作指南", "title": "写作指南", "contentTemplate": {"volume_number": "{$.content.volume_number}"}}, "position": {"x": 1720, "y": 170}}
        ],
        "edges": [
            {"id": "e-read_vol-foreach_new_chars", "source": "read_vol", "target": "foreach_new_chars", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreach_new_chars-upsert_char2", "source": "foreach_new_chars", "target": "upsert_char2", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-foreach_new_chars-foreach_new_scenes", "source": "foreach_new_chars", "target": "foreach_new_scenes", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreach_new_scenes-upsert_scene2", "source": "foreach_new_scenes", "target": "upsert_scene2", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-foreach_new_scenes-foreach_stage", "source": "foreach_new_scenes", "target": "foreach_stage", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreach_stage-upsert_stage", "source": "foreach_stage", "target": "upsert_stage", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-foreach_stage-upsert_guide", "source": "foreach_stage", "target": "upsert_guide", "sourceHandle": "r", "targetHandle": "l"}
        ]
    }
    c, u, s = _create_or_update_workflow(session, name3, "分卷大纲：创建阶段大纲与写作指南，并落地新角色/场景子卡", dsl3, "分卷大纲", overwrite)
    total_created += c
    total_updated += u
    total_skipped += s

    # ============ 工作流4: 阶段大纲·落章节卡 ============
    name4 = "阶段大纲"
    dsl4 = {
        "dsl_version": 1,
        "name": name4,
        "nodes": [
            {"id": "read_stage", "type": "Card.Read", "params": {"target": "$self", "type_name": "阶段大纲"}, "position": {"x": 40, "y": 80}},
            {"id": "foreach_chapter_outline", "type": "List.ForEach", "params": {"listPath": "$.content.chapter_outline_list"}, "position": {"x": 460, "y": 80}},
            {"id": "upsert_outline", "type": "Card.UpsertChildByTitle", "params": {"cardType": "章节大纲", "title": "第{item.chapter_number}章 {item.title}", "useItemAsContent": True, "contentMerge": {"title": "第{item.chapter_number}章 {item.title}"}}, "position": {"x": 460, "y": 260}},
            {"id": "upsert_chapter", "type": "Card.UpsertChildByTitle", "params": {"cardType": "章节正文", "title": "第{item.chapter_number}章 {item.title}", "contentTemplate": {"volume_number": "{$.content.volume_number}", "stage_number": "{$.content.stage_number}", "chapter_number": "{item.chapter_number}", "title": "第{item.chapter_number}章 {item.title}", "entity_list": {"$toNameList": "item.entity_list"}, "content": ""}}, "position": {"x": 880, "y": 260}},
            {"id": "clear_outline", "type": "Card.ModifyContent", "params": {"setPath": "$.content.chapter_outline_list", "setValue": []}, "position": {"x": 1300, "y": 170}}
        ],
        "edges": [
            {"id": "e-read_stage-foreach_chapter_outline", "source": "read_stage", "target": "foreach_chapter_outline", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreach_chapter_outline-upsert_outline", "source": "foreach_chapter_outline", "target": "upsert_outline", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-foreach_chapter_outline-upsert_chapter", "source": "foreach_chapter_outline", "target": "upsert_chapter", "sourceHandle": "b", "targetHandle": "t"},
            {"id": "e-upsert_outline-upsert_chapter", "source": "upsert_outline", "target": "upsert_chapter", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-foreach_chapter_outline-clear_outline", "source": "foreach_chapter_outline", "target": "clear_outline", "sourceHandle": "r", "targetHandle": "l"}
        ]
    }
    c, u, s = _create_or_update_workflow(session, name4, "阶段大纲：根据章节大纲列表创建/更新章节大纲与章节正文子卡，并清空列表", dsl4, "阶段大纲", overwrite)
    total_created += c
    total_updated += u
    total_skipped += s

    # ============ 工作流5: 项目创建·雪花创作法 ============
    name5 = "项目创建·雪花创作法"
    dsl5 = {
        "dsl_version": 1,
        "name": name5,
        "nodes": [
            {"id": "upsert_tags", "type": "Card.UpsertChildByTitle", "params": {"parent": "$projectRoot", "cardType": "作品标签", "title": "作品标签"}, "position": {"x": 40, "y": 80}},
            {"id": "upsert_power", "type": "Card.UpsertChildByTitle", "params": {"parent": "$projectRoot", "cardType": "金手指", "title": "金手指"}, "position": {"x": 460, "y": 80}},
            {"id": "upsert_one_sentence", "type": "Card.UpsertChildByTitle", "params": {"parent": "$projectRoot", "cardType": "一句话梗概", "title": "一句话梗概"}, "position": {"x": 880, "y": 80}},
            {"id": "upsert_outline", "type": "Card.UpsertChildByTitle", "params": {"parent": "$projectRoot", "cardType": "故事大纲", "title": "故事大纲"}, "position": {"x": 1300, "y": 80}},
            {"id": "upsert_world", "type": "Card.UpsertChildByTitle", "params": {"parent": "$projectRoot", "cardType": "世界观设定", "title": "世界观设定"}, "position": {"x": 1720, "y": 80}},
            {"id": "upsert_blueprint", "type": "Card.UpsertChildByTitle", "params": {"parent": "$projectRoot", "cardType": "核心蓝图", "title": "核心蓝图"}, "position": {"x": 2140, "y": 80}}
        ],
        "edges": [
            {"id": "e-tags-power", "source": "upsert_tags", "target": "upsert_power", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-power-one", "source": "upsert_power", "target": "upsert_one_sentence", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-one-outline", "source": "upsert_one_sentence", "target": "upsert_outline", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-outline-world", "source": "upsert_outline", "target": "upsert_world", "sourceHandle": "r", "targetHandle": "l"},
            {"id": "e-world-blueprint", "source": "upsert_world", "target": "upsert_blueprint", "sourceHandle": "r", "targetHandle": "l"}
        ]
    }
    
    # 创建/更新该工作流
    wf5 = session.exec(select(Workflow).where(Workflow.name == name5)).first()
    if not wf5:
        wf5 = Workflow(name=name5, description="项目创建时：按雪花创作法初始化基础卡片", is_built_in=True, is_active=True, version=1, dsl_version=1, definition_json=dsl5)
        session.add(wf5)
        session.commit()
        session.refresh(wf5)
        total_created += 1
        logger.info(f"已创建内置工作流: {name5} (id={wf5.id})")
    else:
        if overwrite:
            wf5.definition_json = dsl5
            wf5.is_built_in = True
            wf5.is_active = True
            wf5.version = 1
            session.add(wf5)
            session.commit()
            total_updated += 1
            logger.info(f"已更新内置工作流: {name5} (id={wf5.id})")
        else:
            total_skipped += 1

    # 确保 onprojectcreate 触发器存在
    if wf5 and wf5.id:
        tg5 = session.exec(select(WorkflowTrigger).where(WorkflowTrigger.workflow_id == wf5.id, WorkflowTrigger.trigger_on == "onprojectcreate")).first()
        if not tg5:
            tg5 = WorkflowTrigger(workflow_id=wf5.id, trigger_on="onprojectcreate", is_active=True)
            session.add(tg5)
            session.commit()
            total_created += 1
            logger.info(f"已创建触发器: onprojectcreate -> {name5}")
        else:
            if overwrite:
                tg5.is_active = True
                session.add(tg5)
                session.commit()
                total_updated += 1
                logger.info(f"已更新触发器: onprojectcreate -> {name5}")
            else:
                total_skipped += 1

    if total_created > 0 or total_updated > 0:
        session.commit()
        logger.info(f"工作流初始化完成: 新增 {total_created} 个，更新 {total_updated} 个（overwrite={overwrite}，跳过 {total_skipped} 个）。")
    else:
        logger.info(f"所有工作流已是最新状态（overwrite={overwrite}，跳过 {total_skipped} 个）。")
