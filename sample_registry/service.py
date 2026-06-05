"""业务逻辑层 - 校验、状态流转、异常处理"""

import os
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from .database import Database

STATUS_MAP = {
    "RECEIVED": "已接收",
    "PENDING_INFO": "待补资料",
    "STORED": "已入库",
    "RETURNED": "已退回",
    "VOIDED": "已作废"
}

STATUS_COLORS = {
    "RECEIVED": "#4CAF50",
    "PENDING_INFO": "#FF9800",
    "STORED": "#2196F3",
    "RETURNED": "#9C27B0",
    "VOIDED": "#F44336"
}


class ValidationError(Exception):
    """校验异常"""
    pass


class SampleService:
    def __init__(self):
        self.db = Database()

    def validate_sample_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """校验样本数据，返回 (是否通过, 错误列表)"""
        errors = []

        required_fields = ["sample_no", "project", "quantity", "receiver", "location"]
        for field in required_fields:
            if field not in data or not data[field]:
                errors.append(f"{field} 不能为空")

        if "sample_no" in data and data["sample_no"]:
            if not re.match(r'^[A-Za-z0-9_-]{1,50}$', data["sample_no"]):
                errors.append("样本编号只能包含字母、数字、下划线和短横线，长度1-50")

        if "quantity" in data and data["quantity"]:
            try:
                qty = int(data["quantity"])
                if qty <= 0 or qty > 10000:
                    errors.append("数量必须在 1-10000 之间")
            except (ValueError, TypeError):
                errors.append("数量必须是整数")

        if "receiver" in data and data["receiver"]:
            if len(data["receiver"]) > 50:
                errors.append("接收人姓名不能超过50字符")

        if "location" in data and data["location"]:
            if len(data["location"]) > 100:
                errors.append("存放位置不能超过100字符")

        if "project" in data and data["project"]:
            if len(data["project"]) > 100:
                errors.append("项目名称不能超过100字符")

        return len(errors) == 0, errors

    def register_sample(self, data: Dict[str, Any], operator: str) -> Tuple[bool, str, Optional[int]]:
        """登记新样本"""
        ok, errors = self.validate_sample_data(data)
        if not ok:
            return False, "; ".join(errors), None

        if isinstance(data.get("quantity"), str):
            data["quantity"] = int(data["quantity"])

        existing = self.db.get_sample_by_no(data["sample_no"])
        if existing:
            return False, f"样本编号 {data['sample_no']} 已存在", None

        return self.db.insert_sample(data, operator)

    def bulk_import_samples(
        self,
        samples_data: List[Dict[str, Any]],
        operator: str,
        skip_errors: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """批量导入样本
        返回 (整体成功, 汇总消息, 详情统计)
        """
        results = {
            "success": 0,
            "failed": 0,
            "errors": [],
            "sample_ids": []
        }

        original_records = []
        for data in samples_data:
            original_records.append(dict(data))

        for idx, data in enumerate(samples_data, 1):
            try:
                ok, errors = self.validate_sample_data(data)
                if not ok:
                    results["failed"] += 1
                    results["errors"].append(f"第{idx}行: {'; '.join(errors)}")
                    if not skip_errors:
                        return False, f"导入失败，第{idx}行: {'; '.join(errors)}", results
                    continue

                if isinstance(data.get("quantity"), str):
                    data["quantity"] = int(data["quantity"])

                ok, msg, sample_id = self.db.insert_sample(data, operator)
                if ok:
                    results["success"] += 1
                    results["sample_ids"].append(sample_id)
                else:
                    results["failed"] += 1
                    results["errors"].append(f"第{idx}行: {msg}")
                    if not skip_errors:
                        return False, f"导入失败，第{idx}行: {msg}", results
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"第{idx}行: 未知错误 {str(e)}")
                if not skip_errors:
                    return False, f"导入失败，第{idx}行: 未知错误", results

        if results["failed"] > 0 and not skip_errors:
            return False, f"导入完成，成功 {results['success']} 条，失败 {results['failed']} 条", results

        return True, f"导入完成，成功 {results['success']} 条，失败 {results['failed']} 条", results

    def transition_status(
        self,
        sample_id: int,
        new_status: str,
        operator: str,
        remark: str = "",
        force: bool = False
    ) -> Tuple[bool, str]:
        """状态流转"""
        sample = self.db.get_sample_by_id(sample_id)
        if not sample:
            return False, "样本不存在"

        if new_status not in STATUS_MAP:
            return False, f"无效状态: {new_status}"

        if sample["status"] == new_status:
            return False, "状态未变化"

        exception_type = ""
        if sample["status"] == "RETURNED" and new_status == "STORED" and not force:
            exception_type = "RETURNED_TO_STORED"
            remark = f"{remark} [异常: 退回样本直接入库]".strip()

        return self.db.update_sample_status(
            sample_id, new_status, operator, remark, exception_type, force
        )

    def get_samples(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """获取样本列表，自动添加状态中文名称"""
        samples = self.db.get_samples(filters)
        for s in samples:
            s["status_display"] = STATUS_MAP.get(s["status"], s["status"])
            s["status_color"] = STATUS_COLORS.get(s["status"], "#666666")
        return samples

    def get_pending_samples(self) -> List[Dict[str, Any]]:
        """获取待处理样本（已接收、待补资料）"""
        return self.get_samples({"status__in": ["RECEIVED", "PENDING_INFO"]})

    def get_sample_timeline(self, sample_id: int) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """获取样本详情和时间线"""
        sample = self.db.get_sample_by_id(sample_id)
        if not sample:
            return None, []

        sample["status_display"] = STATUS_MAP.get(sample["status"], sample["status"])
        history = self.db.get_sample_history(sample_id)

        for h in history:
            h["from_display"] = STATUS_MAP.get(h["from_status"], h["from_status"]) if h["from_status"] else "-"
            h["to_display"] = STATUS_MAP.get(h["to_status"], h["to_status"])

        return sample, history

    def update_notes(
        self,
        sample_id: int,
        damage_note: Optional[str] = None,
        missing_tube_note: Optional[str] = None
    ) -> Tuple[bool, str]:
        """更新备注"""
        return self.db.update_sample_notes(sample_id, damage_note, missing_tube_note)

    def get_export_config(self) -> Dict[str, Any]:
        """获取上次导出配置"""
        return self.db.get_config("export_config", {
            "directory": os.path.expanduser("~"),
            "format": "csv",
            "filters": {}
        })

    def save_export_config(self, config: Dict[str, Any]) -> None:
        """保存导出配置"""
        self.db.set_config("export_config", config)

    def get_last_export_path(self) -> Optional[str]:
        """获取上次导出路径"""
        config = self.get_export_config()
        if config and "directory" in config:
            return config["directory"]
        return None

    def validate_export_path(self, path: str) -> Tuple[bool, str]:
        """校验导出路径"""
        if not path:
            return False, "导出路径不能为空"

        if not os.path.exists(path):
            return False, f"导出目录不存在: {path}"

        if not os.path.isdir(path):
            return False, f"导出路径不是目录: {path}"

        if not os.access(path, os.W_OK):
            return False, f"导出目录不可写: {path}"

        return True, "路径有效"

    def get_all_projects(self) -> List[str]:
        """获取所有项目名称"""
        return self.db.get_all_projects()

    def get_operator(self) -> str:
        """获取当前操作员（从配置或默认）"""
        return self.db.get_config("operator", "admin")

    def set_operator(self, operator: str) -> None:
        """保存操作员"""
        self.db.set_config("operator", operator)
