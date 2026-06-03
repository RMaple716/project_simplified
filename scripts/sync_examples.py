"""
SQLAlchemy 自动同步建表功能 - 使用示例

演示如何在代码中集成和使用自动同步功能
"""
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import engine, Base
from src.models.db_models import City, Attraction


def example_1_basic_sync():
    """示例 1: 基础同步 - 在应用启动时自动创建表"""
    print("\n" + "="*80)
    print("示例 1: 基础同步")
    print("="*80)
    
    # 这行代码会检查并创建所有不存在的表
    Base.metadata.create_all(bind=engine)
    
    print("✅ 所有表已就绪（幂等操作，可安全多次调用）")


def example_2_check_tables():
    """示例 2: 检查特定表是否存在"""
    print("\n" + "="*80)
    print("示例 2: 检查表是否存在")
    print("="*80)
    
    from sqlalchemy import inspect
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    # 检查单个表
    if 'cities' in tables:
        print("✅ cities 表存在")
    else:
        print("❌ cities 表不存在")
    
    # 列出所有表
    print(f"\n数据库中共有 {len(tables)} 个表:")
    for table in sorted(tables):
        print(f"  - {table}")


def example_3_query_data():
    """示例 3: 查询数据验证表结构"""
    print("\n" + "="*80)
    print("示例 3: 查询数据验证")
    print("="*80)
    
    from sqlalchemy.orm import Session
    
    with Session(engine) as session:
        # 查询城市数量
        city_count = session.query(City).count()
        print(f"📊 城市数量: {city_count}")
        
        # 查询景点数量
        attraction_count = session.query(Attraction).count()
        print(f"📊 景点数量: {attraction_count}")
        
        # 查询前 3 个城市
        cities = session.query(City).limit(3).all()
        if cities:
            print("\n前 3 个城市:")
            for city in cities:
                print(f"  - {city.city_name} ({city.province})")


def example_4_advanced_migration():
    """示例 4: 使用高级迁移工具"""
    print("\n" + "="*80)
    print("示例 4: 高级迁移工具")
    print("="*80)
    
    from scripts.db_migration import DatabaseMigration
    
    migration = DatabaseMigration()
    
    # 显示所有表状态
    print("\n查看所有表状态:")
    migration.show_all_tables_info()
    
    # 检查差异
    print("\n检查表结构差异:")
    is_synced = migration.show_table_diff()
    
    if is_synced:
        print("\n✅ 数据库与代码定义完全同步！")


def example_5_create_single_table():
    """示例 5: 创建单个表"""
    print("\n" + "="*80)
    print("示例 5: 创建单个表")
    print("="*80)
    
    from scripts.db_migration import DatabaseMigration
    
    migration = DatabaseMigration()
    
    # 只创建 cities 表（如果不存在）
    success = migration.create_single_table("cities")
    
    if success:
        print("✅ cities 表已就绪")


def main():
    """运行所有示例"""
    print("\n" + "="*80)
    print("SQLAlchemy 自动同步建表 - 使用示例集合")
    print("="*80)
    
    try:
        example_1_basic_sync()
        example_2_check_tables()
        example_3_query_data()
        example_4_advanced_migration()
        example_5_create_single_table()
        
        print("\n" + "="*80)
        print("✅ 所有示例执行完成！")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
