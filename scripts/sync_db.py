"""
SQLAlchemy 自动同步建表脚本（类似 Sequelize 的 sync 功能）

使用方法:
    python scripts/sync_db.py              # 普通同步（只创建不存在的表）
    python scripts/sync_db.py --force      # 强制重建（删除现有表后重新创建）
"""
import sys
import os
import argparse
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import inspect, text
from src.database import engine, Base
from src.models.db_models import (
    City, Attraction, Location, Hotel, Restaurant,
    UserRequirement, Task, Itinerary
)


def get_all_tables():
    """获取所有已定义的表名"""
    return Base.metadata.tables.keys()


def check_tables_exist():
    """检查数据库中是否已存在所有表"""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    defined_tables = set(get_all_tables())
    
    missing_tables = defined_tables - existing_tables
    extra_tables = existing_tables - defined_tables
    
    return {
        'existing': list(existing_tables & defined_tables),
        'missing': list(missing_tables),
        'extra': list(extra_tables),
        'all_exist': len(missing_tables) == 0
    }


def print_table_structure(table_name):
    """打印表结构详情"""
    inspector = inspect(engine)
    
    print(f"\n{'='*60}")
    print(f"表: {table_name}")
    print('='*60)
    
    # 列信息
    columns = inspector.get_columns(table_name)
    print(f"\n列 ({len(columns)}个):")
    for col in columns:
        nullable = "NULL" if col['nullable'] else "NOT NULL"
        default = f" DEFAULT {col['default']}" if col['default'] else ""
        print(f"  - {col['name']:25s} {str(col['type']):20s} {nullable}{default}")
    
    # 主键
    pk_constraint = inspector.get_pk_constraint(table_name)
    if pk_constraint['constrained_columns']:
        print(f"\n主键: {', '.join(pk_constraint['constrained_columns'])}")
    
    # 外键
    fk_constraints = inspector.get_foreign_keys(table_name)
    if fk_constraints:
        print(f"\n外键:")
        for fk in fk_constraints:
            print(f"  - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
    
    # 索引
    indexes = inspector.get_indexes(table_name)
    if indexes:
        print(f"\n索引:")
        for idx in indexes:
            unique = "UNIQUE" if idx['unique'] else "NON-UNIQUE"
            columns = ', '.join([col for col in idx['column_names'] if col]) or 'N/A'
            print(f"  - {idx['name']:30s} ({columns}) [{unique}]")


def sync_tables(force=False):
    """
    同步数据库表结构
    
    Args:
        force: 如果为 True，先删除所有表再重新创建
    """
    print("\n" + "="*80)
    print("SQLAlchemy 自动同步建表工具")
    print("="*80)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模式: {'强制重建' if force else '普通同步'}")
    print("="*80)
    
    # 检查当前状态
    status = check_tables_exist()
    print(f"\n当前数据库状态:")
    print(f"  ✓ 已存在的表: {len(status['existing'])} 个")
    if status['existing']:
        for table in sorted(status['existing']):
            print(f"    - {table}")
    
    if status['missing']:
        print(f"  ⚠ 缺失的表: {len(status['missing'])} 个")
        for table in sorted(status['missing']):
            print(f"    - {table}")
    
    if status['extra']:
        print(f"  ℹ 额外的表: {len(status['extra'])} 个")
        for table in sorted(status['extra']):
            print(f"    - {table}")
    
    # 执行同步
    if force:
        print("\n⚠️  警告: 即将删除所有表并重新创建！这将导致数据丢失！")
        confirm = input("确认继续？(yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ 操作已取消")
            return False
        
        print("\n🗑️  正在删除所有表...")
        try:
            Base.metadata.drop_all(bind=engine)
            print("✅ 所有表已删除")
        except Exception as e:
            print(f"❌ 删除表失败: {e}")
            return False
    
    print("\n📝 正在创建表...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ 表创建完成")
    except Exception as e:
        print(f"❌ 创建表失败: {e}")
        return False
    
    # 验证结果
    print("\n🔍 验证表结构...")
    new_status = check_tables_exist()
    
    if new_status['all_exist']:
        print("✅ 所有表已成功创建")
        
        # 打印每个表的结构
        for table_name in sorted(get_all_tables()):
            print_table_structure(table_name)
        
        print("\n" + "="*80)
        print("✅ 数据库同步完成！")
        print("="*80)
        return True
    else:
        print(f"❌ 仍有 {len(new_status['missing'])} 个表未创建:")
        for table in new_status['missing']:
            print(f"    - {table}")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='SQLAlchemy 自动同步建表工具（类似 Sequelize sync）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/sync_db.py              # 普通同步
  python scripts/sync_db.py --force      # 强制重建
        """
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='强制重建：删除所有现有表后重新创建（会丢失数据！）'
    )
    
    args = parser.parse_args()
    
    success = sync_tables(force=args.force)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
