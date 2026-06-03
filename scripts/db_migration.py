"""
SQLAlchemy 数据库迁移管理工具（高级版）

提供更细粒度的表结构管理功能：
- 检查表是否存在
- 创建/删除单个表
- 添加/删除列
- 查看表结构差异
"""
import sys
import os
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import inspect, text, MetaData
from src.database import engine, Base


class DatabaseMigration:
    """数据库迁移管理器"""
    
    def __init__(self):
        self.inspector = inspect(engine)
        self.metadata = MetaData()
    
    def get_existing_tables(self):
        """获取数据库中已存在的表"""
        return set(self.inspector.get_table_names())
    
    def get_defined_tables(self):
        """获取代码中定义的所有表"""
        return set(Base.metadata.tables.keys())
    
    def check_table_exists(self, table_name):
        """检查指定表是否存在"""
        return table_name in self.get_existing_tables()
    
    def create_single_table(self, table_name):
        """创建单个表"""
        if table_name not in Base.metadata.tables:
            print(f"❌ 未找到表定义: {table_name}")
            return False
        
        if self.check_table_exists(table_name):
            print(f"⚠️  表已存在: {table_name}")
            return True
        
        try:
            Base.metadata.tables[table_name].create(bind=engine)
            print(f"✅ 表创建成功: {table_name}")
            return True
        except Exception as e:
            print(f"❌ 创建表失败 {table_name}: {e}")
            return False
    
    def drop_single_table(self, table_name):
        """删除单个表"""
        if not self.check_table_exists(table_name):
            print(f"⚠️  表不存在: {table_name}")
            return True
        
        try:
            Base.metadata.tables[table_name].drop(bind=engine)
            print(f"✅ 表删除成功: {table_name}")
            return True
        except Exception as e:
            print(f"❌ 删除表失败 {table_name}: {e}")
            return False
    
    def add_column(self, table_name, column_name, column_type, nullable=True, default=None):
        """
        添加新列到现有表
        
        Args:
            table_name: 表名
            column_name: 列名
            column_type: SQLAlchemy 类型（如 String(100), Integer 等）
            nullable: 是否允许 NULL
            default: 默认值
        """
        if not self.check_table_exists(table_name):
            print(f"❌ 表不存在: {table_name}")
            return False
        
        # 检查列是否已存在
        columns = [col['name'] for col in self.inspector.get_columns(table_name)]
        if column_name in columns:
            print(f"⚠️  列已存在: {table_name}.{column_name}")
            return True
        
        try:
            # 构建 ALTER TABLE 语句
            sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            if not nullable:
                sql += " NOT NULL"
            if default is not None:
                sql += f" DEFAULT {default}"
            
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
            
            print(f"✅ 列添加成功: {table_name}.{column_name}")
            return True
        except Exception as e:
            print(f"❌ 添加列失败: {e}")
            return False
    
    def drop_column(self, table_name, column_name):
        """删除表中的列"""
        if not self.check_table_exists(table_name):
            print(f"❌ 表不存在: {table_name}")
            return False
        
        columns = [col['name'] for col in self.inspector.get_columns(table_name)]
        if column_name not in columns:
            print(f"⚠️  列不存在: {table_name}.{column_name}")
            return True
        
        try:
            sql = f"ALTER TABLE {table_name} DROP COLUMN {column_name}"
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
            
            print(f"✅ 列删除成功: {table_name}.{column_name}")
            return True
        except Exception as e:
            print(f"❌ 删除列失败: {e}")
            return False
    
    def show_table_diff(self):
        """显示数据库与代码定义的差异"""
        existing = self.get_existing_tables()
        defined = self.get_defined_tables()
        
        missing_in_db = defined - existing
        extra_in_db = existing - defined
        
        print("\n" + "="*80)
        print("数据库结构差异分析")
        print("="*80)
        
        if missing_in_db:
            print(f"\n📋 代码中定义但数据库中缺失的表 ({len(missing_in_db)}个):")
            for table in sorted(missing_in_db):
                print(f"  - {table}")
        else:
            print("\n✅ 所有代码定义的表都已存在于数据库中")
        
        if extra_in_db:
            print(f"\n📋 数据库中存在但代码中未定义的表 ({len(extra_in_db)}个):")
            for table in sorted(extra_in_db):
                print(f"  - {table}")
        else:
            print("\n✅ 数据库中没有额外的表")
        
        return len(missing_in_db) == 0 and len(extra_in_db) == 0
    
    def show_all_tables_info(self):
        """显示所有表的详细信息"""
        defined_tables = sorted(self.get_defined_tables())
        
        print("\n" + "="*80)
        print(f"数据库表概览 (共 {len(defined_tables)} 个表)")
        print("="*80)
        
        for table_name in defined_tables:
            exists = "✅" if self.check_table_exists(table_name) else "❌"
            print(f"{exists} {table_name}")


def main():
    """主函数 - 交互式菜单"""
    migration = DatabaseMigration()
    
    print("\n" + "="*80)
    print("SQLAlchemy 数据库迁移管理工具")
    print("="*80)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    while True:
        print("\n请选择操作:")
        print("  1. 查看所有表状态")
        print("  2. 检查表结构差异")
        print("  3. 创建单个表")
        print("  4. 删除单个表")
        print("  5. 添加列")
        print("  6. 删除列")
        print("  7. 退出")
        
        choice = input("\n请输入选项 (1-7): ").strip()
        
        if choice == '1':
            migration.show_all_tables_info()
        
        elif choice == '2':
            is_synced = migration.show_table_diff()
            if is_synced:
                print("\n✅ 数据库与代码定义完全同步！")
        
        elif choice == '3':
            table_name = input("请输入要创建的表名: ").strip()
            migration.create_single_table(table_name)
        
        elif choice == '4':
            table_name = input("请输入要删除的表名: ").strip()
            confirm = input(f"确认删除表 '{table_name}'？这将丢失所有数据！(yes/no): ")
            if confirm.lower() == 'yes':
                migration.drop_single_table(table_name)
            else:
                print("❌ 操作已取消")
        
        elif choice == '5':
            table_name = input("请输入表名: ").strip()
            column_name = input("请输入列名: ").strip()
            column_type = input("请输入列类型 (如 VARCHAR(100), INTEGER): ").strip()
            nullable = input("是否允许 NULL？(yes/no, 默认yes): ").strip().lower() != 'no'
            default = input("默认值 (直接回车表示无): ").strip() or None
            
            migration.add_column(table_name, column_name, column_type, nullable, default)
        
        elif choice == '6':
            table_name = input("请输入表名: ").strip()
            column_name = input("请输入要删除的列名: ").strip()
            confirm = input(f"确认删除列 '{table_name}.{column_name}'？(yes/no): ")
            if confirm.lower() == 'yes':
                migration.drop_column(table_name, column_name)
            else:
                print("❌ 操作已取消")
        
        elif choice == '7':
            print("\n👋 再见！")
            break
        
        else:
            print("❌ 无效选项，请重新选择")


if __name__ == '__main__':
    main()
