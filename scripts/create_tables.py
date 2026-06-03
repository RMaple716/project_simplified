"""
执行建表脚本 - 创建业务数据表和基础数据表
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import dotenv
dotenv.load_dotenv()

def execute_sql_file(sql_file_path):
    """执行SQL文件"""
    print("=" * 70)
    print("📝 执行建表脚本")
    print("=" * 70)

    if not os.path.exists(sql_file_path):
        print(f"❌ SQL文件不存在: {sql_file_path}")
        return False

    try:
        import psycopg2
        from src.database import DATABASE_URL

        # 读取SQL文件
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        print(f"\n✅ 已读取SQL文件: {sql_file_path}")
        print(f"   文件大小: {len(sql_content)} 字节")

        # 连接到数据库并执行
        print("\n正在执行SQL...")
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True  # 自动提交每条语句

        cursor = conn.cursor()

        # 使用execute执行整个脚本（PostgreSQL支持多语句）
        cursor.execute(sql_content)

        cursor.close()
        conn.close()

        print("✅ SQL执行完成！")
        return True

    except Exception as e:
        print(f"\n❌ 执行失败: {type(e).__name__}")
        print(f"错误信息: {str(e)[:500]}")
        return False


def verify_tables():
    """验证表是否创建成功"""
    print("\n" + "=" * 70)
    print("🔍 验证表结构")
    print("=" * 70)

    try:
        from src.models.db_models import UserRequirement, Task, Itinerary, City, Attraction, Hotel, Restaurant, Location
        from src.database import SessionLocal

        db = SessionLocal()

        tables = {
            'user_requirements': UserRequirement,
            'tasks': Task,
            'itineraries': Itinerary,
            'cities': City,
            'attractions': Attraction,
            'hotels': Hotel,
            'restaurants': Restaurant,
            'locations': Location
        }

        all_exist = True
        for table_name, model in tables.items():
            try:
                count = db.query(model).count()
                print(f"✅ {table_name}: 存在 ({count} 条记录)")
            except Exception as e:
                print(f"❌ {table_name}: 不存在或无法访问")
                print(f"   错误: {str(e)[:100]}")
                all_exist = False

        db.close()

        if all_exist:
            print("\n✨ 所有表都已成功创建！")
        else:
            print("\n⚠️  部分表创建失败，请检查错误信息")

        return all_exist

    except Exception as e:
        print(f"\n❌ 验证失败: {str(e)}")
        return False


if __name__ == "__main__":
    # 只执行database_schema.sql文件（它已包含所有表结构）
    sql_file = os.path.join(os.path.dirname(__file__), '..', 'database_schema.sql')

    print(f"\n📋 正在执行: {os.path.basename(sql_file)}")
    all_success = execute_sql_file(sql_file)

    if all_success:
        verify_tables()

        print("\n" + "=" * 70)
        print("🎉 下一步操作:")
        print("=" * 70)
        print("1. 运行完整测试:")
        print("   python scripts/test_full_integration.py")
        print("\n2. 启动服务:")
        print("   python src/index.py")
        print("=" * 70)
    else:
        print("\n❌ 建表失败，请检查数据库连接和权限")
