#!/usr/bin/env python3
"""
数据库迁移脚本 - 添加 AI 修改追踪字段

使用方法：
    python migrate_db.py

或指定数据库文件：
    python migrate_db.py --db-path /path/to/your/database.db

此脚本会：
1. 检查数据库是否已有这些字段
2. 如果没有，则添加 ai_modified, needs_confirmation, last_modified_by 字段
3. 备份原数据库（可选）
"""

import sqlite3
import argparse
import shutil
from pathlib import Path
from datetime import datetime


def check_column_exists(cursor, table_name, column_name):
    """检查表中是否存在指定列"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def backup_database(db_path):
    """备份数据库文件"""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"✅ 数据库已备份到: {backup_path}")
    return backup_path


def migrate_database(db_path, create_backup=True):
    """执行数据库迁移"""
    db_path = Path(db_path)
    
    if not db_path.exists():
        print(f"❌ 错误：数据库文件不存在: {db_path}")
        return False
    
    print(f"📂 数据库文件: {db_path}")
    
    # 备份数据库
    if create_backup:
        try:
            backup_database(db_path)
        except Exception as e:
            print(f"⚠️  警告：备份失败: {e}")
            response = input("是否继续迁移？(y/n): ")
            if response.lower() != 'y':
                print("❌ 迁移已取消")
                return False
    
    # 连接数据库
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查 card 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='card'")
        if not cursor.fetchone():
            print("❌ 错误：找不到 card 表")
            return False
        
        print("\n🔍 检查现有字段...")
        
        # 检查并添加字段
        # 注意：SQLite 没有原生 BOOLEAN 类型，但 SQLAlchemy 会将其映射为 INTEGER (0/1)
        # 为了与 SQLAlchemy/Alembic 保持一致，这里使用 BOOLEAN（SQLite 会自动转换为 INTEGER）
        fields_to_add = [
            ('ai_modified', 'BOOLEAN NOT NULL DEFAULT 0'),
            ('needs_confirmation', 'BOOLEAN NOT NULL DEFAULT 0'),
            ('last_modified_by', 'TEXT')
        ]
        
        added_fields = []
        skipped_fields = []
        
        for field_name, field_type in fields_to_add:
            if check_column_exists(cursor, 'card', field_name):
                print(f"  ⏭️  字段 '{field_name}' 已存在，跳过")
                skipped_fields.append(field_name)
            else:
                try:
                    sql = f"ALTER TABLE card ADD COLUMN {field_name} {field_type}"
                    cursor.execute(sql)
                    print(f"  ✅ 添加字段 '{field_name}'")
                    added_fields.append(field_name)
                except Exception as e:
                    print(f"  ❌ 添加字段 '{field_name}' 失败: {e}")
                    conn.rollback()
                    return False
        
        # 提交更改
        conn.commit()
        
        # 验证字段
        print("\n🔍 验证迁移结果...")
        cursor.execute("PRAGMA table_info(card)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        all_fields_present = all(field_name in columns for field_name, _ in fields_to_add)
        
        if all_fields_present:
            print("\n✅ 迁移成功！")
            if added_fields:
                print(f"   新增字段: {', '.join(added_fields)}")
            if skipped_fields:
                print(f"   已存在字段: {', '.join(skipped_fields)}")
            return True
        else:
            print("\n❌ 迁移失败：部分字段未添加成功")
            return False
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        return False
    finally:
        if conn:
            conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='NovelForge 数据库迁移脚本 - 添加 AI 修改追踪字段'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default='./novelforge.db',
        help='数据库文件路径（默认: ./novelforge.db）'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='不创建备份（不推荐）'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("NovelForge 数据库迁移工具")
    print("版本: 2026-01-21 - AI 修改追踪字段")
    print("=" * 60)
    print()
    
    success = migrate_database(
        args.db_path,
        create_backup=not args.no_backup
    )
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 迁移完成！现在可以启动应用程序了。")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("💔 迁移失败，请检查错误信息。")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    exit(main())
