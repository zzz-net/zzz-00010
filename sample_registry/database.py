"""数据库模块 - SQLite 持久化存储"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_registry.db")


class Database:
    _instance = None

    def __new__(cls, db_path: str = DB_PATH):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db_path = db_path
            cls._instance._init_db()
        return cls._instance

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sample_no TEXT NOT NULL UNIQUE,
                    project TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    receiver TEXT NOT NULL,
                    location TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'RECEIVED',
                    damage_note TEXT,
                    missing_tube_note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sample_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sample_id INTEGER NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    remark TEXT,
                    exception_type TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_samples_status ON samples(status);
                CREATE INDEX IF NOT EXISTS idx_samples_project ON samples(project);
                CREATE INDEX IF NOT EXISTS idx_samples_created_at ON samples(created_at);
                CREATE INDEX IF NOT EXISTS idx_history_sample_id ON sample_history(sample_id);
            """)

    def get_config(self, key: str, default: Any = None) -> Any:
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    return row["value"]
            return default

    def set_config(self, key: str, value: Any) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False))
            )

    def insert_sample(self, sample_data: Dict[str, Any], operator: str) -> Tuple[bool, str, Optional[int]]:
        """插入新样本，返回 (成功, 消息, 样本ID)"""
        now = datetime.now().isoformat(timespec="seconds")

        existing = self.get_sample_by_no(sample_data["sample_no"])
        if existing:
            return False, f"样本编号 {sample_data['sample_no']} 已存在", None

        try:
            with self._get_conn() as conn:
                cur = conn.execute(
                    """INSERT INTO samples 
                       (sample_no, project, quantity, receiver, location, status,
                        damage_note, missing_tube_note, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sample_data["sample_no"],
                        sample_data["project"],
                        sample_data["quantity"],
                        sample_data["receiver"],
                        sample_data["location"],
                        "RECEIVED",
                        sample_data.get("damage_note"),
                        sample_data.get("missing_tube_note"),
                        now,
                        now
                    )
                )
                sample_id = cur.lastrowid

                conn.execute(
                    """INSERT INTO sample_history
                       (sample_id, from_status, to_status, operator, remark, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (sample_id, "", "RECEIVED", operator, "样本接收登记", now)
                )
            return True, "样本登记成功", sample_id
        except Exception as e:
            return False, f"数据库错误: {str(e)}", None

    def get_sample_by_no(self, sample_no: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM samples WHERE sample_no = ?",
                (sample_no,)
            ).fetchone()
            return dict(row) if row else None

    def get_sample_by_id(self, sample_id: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM samples WHERE id = ?",
                (sample_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_samples(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """获取样本列表，支持按状态、项目、日期范围筛选"""
        query = "SELECT * FROM samples WHERE 1=1"
        params: List[Any] = []

        if filters:
            if filters.get("status"):
                query += " AND status = ?"
                params.append(filters["status"])
            if filters.get("status__in") and isinstance(filters["status__in"], list) and filters["status__in"]:
                placeholders = ",".join(["?"] * len(filters["status__in"]))
                query += f" AND status IN ({placeholders})"
                params.extend(filters["status__in"])
            if filters.get("project"):
                query += " AND project LIKE ?"
                params.append(f"%{filters['project']}%")
            if filters.get("date_from"):
                query += " AND date(created_at) >= date(?)"
                params.append(filters["date_from"])
            if filters.get("date_to"):
                query += " AND date(created_at) <= date(?)"
                params.append(filters["date_to"])

        query += " ORDER BY created_at DESC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_sample_history(self, sample_id: int) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sample_history WHERE sample_id = ? ORDER BY created_at ASC",
                (sample_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def update_sample_status(
        self,
        sample_id: int,
        new_status: str,
        operator: str,
        remark: str = "",
        exception_type: str = "",
        force: bool = False
    ) -> Tuple[bool, str]:
        """更新样本状态，返回 (成功, 消息)"""
        sample = self.get_sample_by_id(sample_id)
        if not sample:
            return False, "样本不存在"

        old_status = sample["status"]
        now = datetime.now().isoformat(timespec="seconds")

        valid_transitions = {
            "RECEIVED": ["PENDING_INFO", "STORED", "RETURNED", "VOIDED"],
            "PENDING_INFO": ["STORED", "RETURNED", "VOIDED"],
            "STORED": ["VOIDED"],
            "RETURNED": ["RECEIVED", "VOIDED"],
            "VOIDED": []
        }

        if not force and new_status not in valid_transitions.get(old_status, []):
            if old_status == "RETURNED" and new_status == "STORED":
                return False, "已退回样本不能直接入库，请先执行重新接收操作"
            return False, f"不允许从 {old_status} 直接流转到 {new_status}"

        try:
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE samples SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, now, sample_id)
                )
                conn.execute(
                    """INSERT INTO sample_history
                       (sample_id, from_status, to_status, operator, remark, exception_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (sample_id, old_status, new_status, operator, remark, exception_type or None, now)
                )
            return True, f"状态已更新为 {new_status}"
        except Exception as e:
            return False, f"数据库错误: {str(e)}"

    def update_sample_notes(
        self,
        sample_id: int,
        damage_note: Optional[str] = None,
        missing_tube_note: Optional[str] = None
    ) -> Tuple[bool, str]:
        """更新破损/缺管备注"""
        sample = self.get_sample_by_id(sample_id)
        if not sample:
            return False, "样本不存在"

        now = datetime.now().isoformat(timespec="seconds")
        updates = []
        params = []

        if damage_note is not None:
            updates.append("damage_note = ?")
            params.append(damage_note)
        if missing_tube_note is not None:
            updates.append("missing_tube_note = ?")
            params.append(missing_tube_note)

        if not updates:
            return True, "无更新"

        updates.append("updated_at = ?")
        params.append(now)
        params.append(sample_id)

        query = f"UPDATE samples SET {', '.join(updates)} WHERE id = ?"

        try:
            with self._get_conn() as conn:
                conn.execute(query, params)
            return True, "备注更新成功"
        except Exception as e:
            return False, f"数据库错误: {str(e)}"

    def get_all_projects(self) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project FROM samples ORDER BY project"
            ).fetchall()
            return [row["project"] for row in rows]
