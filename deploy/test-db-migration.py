import os
import sys
from pathlib import Path

# 仓库内相对定位：本脚本位于 <repo>/deploy/，后端代码在 <repo>/backend/
BACKEND = str(Path(__file__).resolve().parent.parent / "backend")
mode = sys.argv[1] if len(sys.argv) > 1 else "mysql"

if mode == "mysql":
    os.environ["DB_BACKEND"] = "mysql"
    os.environ["MYSQL_HOST"] = "127.0.0.1"
    os.environ["MYSQL_PORT"] = "13306"
    os.environ["MYSQL_USER"] = "root"
    os.environ["MYSQL_PASSWORD"] = ""
    os.environ["MYSQL_DATABASE"] = "pm_assistant"
else:
    os.environ["DB_BACKEND"] = "sqlite"
    os.environ["AGENT_DATA_DIR"] = "/tmp/pm_sqlite_test"

sys.path.insert(0, BACKEND)
import db  # noqa: E402

print("== 后端 ==", "mysql" if db._IS_MYSQL else "sqlite")
print("TEXT 默认值用表达式 =", db._TEXT_DEFAULT_AS_EXPR)

if db._IS_MYSQL:
    ddl = db._mysql_ddl(db._SCHEMA, db._TEXT_DEFAULT_AS_EXPR)
    print("-- DDL 改写自检 --")
    print("   AUTO_INCREMENT 次数 =", ddl.count("AUTO_INCREMENT"))
    print("   DEFAULT ('') 次数   =", ddl.count("DEFAULT (''"))
    print("   反引号表名          =", "`memories_longterm`" in ddl)
    print("   反引号保留字 `key`   =", "`key`" in ddl)
    print("   反引号保留字 `condition` =", "`condition`" in ddl)
    print("   残留 AUTOINCREMENT  =", "AUTOINCREMENT" in ddl)
    print("   残留 REAL           =", " REAL " in ddl)
    print("   表数量              =", ddl.count("CREATE TABLE"))

n = db.query("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=?", (db.Config.mysql_database,)) \
    if db._IS_MYSQL else db.query("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table'")
print("-- 已建表数量 --", n[0]["n"])

print("-- CRUD --")
pid = db.execute(
    "INSERT INTO projects (name, folder_path, project_type, project_code, description, created_at, updated_at)"
    " VALUES (?,?,?,?,?,?,?)",
    ("迁移验证项目", "/tmp/x", "测试", "T1", "", db.now(), db.now()),
)
print("   insert project id =", pid)
print("   select project    =", db.query("SELECT id, name FROM projects WHERE id=?", (pid,)))
print("   LIKE 查询         =", db.query("SELECT COUNT(*) AS n FROM projects WHERE name LIKE ?", ("%迁移%",)))

mid = db.execute(
    "INSERT INTO memories_longterm (project_id, `key`, value, category, status, note, created_at, updated_at)"
    " VALUES (?,?,?,?,'active',?,?,?)",
    (pid, "k1", "v1", "cat", "", db.now(), db.now()),
)
print("   insert memory id  =", mid)
db.execute("UPDATE memories_longterm SET `key`=?, value=? WHERE id=?", ("k2", "v2", mid))
print("   memory 更新后     =", db.query("SELECT `key`, value FROM memories_longterm WHERE id=?", (mid,)))

vid = db.execute(
    "INSERT INTO plan_versions (project_id, version, kind, label, status, basis_event, `condition`,"
    " result_summary, cost_summary, schedule_impact_days, cost_impact_value, is_formal, created_at)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (pid, "V1", "冻结基准", "基线", "已冻结", "", "无", "", "", 0, 0, 1, db.now()),
)
print("   insert version id =", vid)
print("   version 选中      =", db.query("SELECT version, `condition` FROM plan_versions WHERE id=?", (vid,)))

print("-- 清理 --")
db.execute("DELETE FROM plan_versions WHERE project_id=?", (pid,))
db.execute("DELETE FROM memories_longterm WHERE project_id=?", (pid,))
db.execute("DELETE FROM projects WHERE id=?", (pid,))
print("   完成")
