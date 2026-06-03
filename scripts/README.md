# 📚 SQLAlchemy 自动同步建表功能

## 🎯 概述

本项目实现了类似 **Sequelize** 的自动同步建表功能，让你可以像使用 Node.js ORM 一样轻松管理 PostgreSQL 数据库表结构。

### 核心优势

- ✅ **零配置**: 无需编写 SQL，Python 代码定义即数据库结构
- ✅ **幂等性**: 多次执行不会重复创建，安全无忧
- ✅ **智能检测**: 自动识别缺失表和多余表
- ✅ **灵活操作**: 支持全量同步、增量更新、强制重建等多种模式
- ✅ **详细日志**: 完整的执行过程和表结构输出

---

## 🚀 快速开始

### 1️⃣ 命令行方式（推荐）

```bash
# 普通同步 - 只创建不存在的表
python scripts/sync_db.py

# 强制重建 - 删除所有表后重新创建（会丢失数据！）
python scripts/sync_db.py --force
```

### 2️⃣ 交互式管理

```bash
# 启动图形化管理界面
python scripts/db_migration.py
```

提供以下功能：
- 🔍 查看所有表状态
- 📊 检查表结构差异
- ➕ 创建/删除单个表
- ✏️ 添加/删除列

### 3️⃣ 代码集成

```python
from src.database import engine, Base

# 在应用启动时自动同步
Base.metadata.create_all(bind=engine)
```

---

## 📖 使用场景

### 场景 1: 首次初始化

```bash
# 第一次运行项目时
python scripts/sync_db.py
```

**输出示例:**
```
================================================================================
SQLAlchemy 自动同步建表工具
================================================================================
时间: 2026-05-24 20:44:11
模式: 普通同步
================================================================================

当前数据库状态:
  ✓ 已存在的表: 0 个
  ⚠ 缺失的表: 8 个
    - attractions
    - cities
    - hotels
    ...

📝 正在创建表...
✅ 表创建完成

🔍 验证表结构...
✅ 所有表已成功创建

============================================================
表: cities
============================================================

列 (8个):
  - city_id                   VARCHAR(50)          NOT NULL
  - city_name                 VARCHAR(100)         NOT NULL
  ...

✅ 数据库同步完成！
```

### 场景 2: 新增模型后同步

当你添加了新的数据库模型类：

```python
# src/models/db_models.py
class NewModel(Base):
    __tablename__ = "new_models"
    id = Column(String(50), primary_key=True)
    name = Column(String(100))
```

然后运行：
```bash
python scripts/sync_db.py
```

系统会自动检测并创建 `new_models` 表。

### 场景 3: 开发环境重置

```bash
# 清空所有数据并重新创建
python scripts/sync_db.py --force
```

⚠️ **警告**: 此操作会删除所有数据，仅用于开发环境！

### 场景 4: 查看数据库状态

```bash
python scripts/db_migration.py
```

选择选项 `2` 查看数据库与代码定义的差异。

---

## 🛠️ 脚本说明

### 1. `scripts/sync_db.py` - 基础同步工具

**功能:**
- 自动创建所有缺失的表
- 显示详细的表结构（列、索引、外键）
- 支持强制重建模式

**用法:**
```bash
python scripts/sync_db.py              # 普通同步
python scripts/sync_db.py --force      # 强制重建
```

### 2. `scripts/db_migration.py` - 高级迁移工具

**功能:**
- 交互式菜单管理
- 单个表的创建/删除
- 列的添加/删除
- 表结构差异分析

**用法:**
```bash
python scripts/db_migration.py
```

**菜单选项:**
```
1. 查看所有表状态
2. 检查表结构差异
3. 创建单个表
4. 删除单个表
5. 添加列
6. 删除列
7. 退出
```

### 3. `scripts/sync_examples.py` - 使用示例

**功能:**
- 演示各种使用场景
- 展示如何在代码中集成
- 验证表结构和数据

**用法:**
```bash
python scripts/sync_examples.py
```

---

## 📊 当前数据库表

### 基础数据表
| 表名 | 说明 | 记录数 |
|------|------|--------|
| `cities` | 城市信息 | 5 |
| `attractions` | 景点信息 | 7 |
| `locations` | 地点信息（交通枢纽等） | 13 |
| `hotels` | 酒店信息 | 9 |
| `restaurants` | 餐厅信息 | 11 |

### 业务数据表
| 表名 | 说明 | 用途 |
|------|------|------|
| `user_requirements` | 用户需求 | 存储用户提交的旅游需求 |
| `tasks` | 任务分解 | 智能体任务执行结果 |
| `itineraries` | 行程方案 | 生成的旅游行程（支持收藏） |

---

## 🔧 配置说明

### 数据库连接

编辑 `src/database.py`:

```python
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:123456@localhost:5432/postgres"
)
```

或通过环境变量：

```bash
export DATABASE_URL="postgresql://user:password@host:port/dbname"
```

### 启用 SQL 日志（调试用）

```python
engine = create_engine(
    DATABASE_URL,
    echo=True,  # 设置为 True 可查看执行的 SQL
)
```

---

## 💡 最佳实践

### 1. 开发环境

```bash
# 每次修改模型后
python scripts/sync_db.py --force
```

### 2. 测试环境

```python
# tests/conftest.py
import pytest
from src.database import engine, Base

@pytest.fixture(scope="session")
def test_db():
    """创建测试数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
```

### 3. 生产环境

⚠️ **重要**: 生产环境应使用 **Alembic** 进行版本化迁移，而不是直接同步！

```bash
# 安装 Alembic
pip install alembic

# 初始化
alembic init alembic

# 生成迁移脚本
alembic revision --autogenerate -m "add new table"

# 执行迁移
alembic upgrade head
```

---

## ❓ 常见问题

### Q1: 为什么表没有创建？

**原因**: 可能未导入模型文件

**解决**: 确保在 `sync_db.py` 中导入了所有模型：

```python
from src.models.db_models import (
    City, Attraction, Location, Hotel, Restaurant,
    UserRequirement, Task, Itinerary
)
```

### Q2: 如何只创建某个特定的表？

```bash
python scripts/db_migration.py
# 选择选项 3，输入表名
```

或在代码中：

```python
from scripts.db_migration import DatabaseMigration

migration = DatabaseMigration()
migration.create_single_table("cities")
```

### Q3: 强制重建后数据丢失怎么办？

**重要**: `--force` 参数会删除所有数据，仅用于开发环境！

生产环境应使用 Alembic 进行结构变更。

### Q4: 如何备份数据后再重建？

```bash
# 1. 导出数据
pg_dump -U postgres -d postgres > backup.sql

# 2. 重建表
python scripts/sync_db.py --force

# 3. 恢复数据（如果需要）
psql -U postgres -d postgres < backup.sql
```

---

## 📚 相关文档

- [详细使用说明](./SQLAlchemy自动同步建表说明.md)
- [SQLAlchemy 官方文档](https://docs.sqlalchemy.org/)
- [Alembic 迁移工具](https://alembic.sqlalchemy.org/)
- [PostgreSQL 官方文档](https://www.postgresql.org/docs/)

---

## 🤝 贡献指南

如需扩展此功能，可以考虑：

1. ✅ 集成 **Alembic** 实现版本化迁移
2. 🔄 添加 **数据种子** 功能（自动填充测试数据）
3. ↩️ 支持 **回滚** 操作
4. 📝 生成 **迁移历史记录**

---

**最后更新**: 2026-05-24  
**维护者**: Project Team
