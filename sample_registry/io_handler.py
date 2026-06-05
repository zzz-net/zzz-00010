"""导入导出模块 - 支持 CSV/JSON 格式，按条件筛选导出"""

import os
import csv
import json
import tempfile
import shutil
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from .service import SampleService, STATUS_MAP


class IOHandler:
    def __init__(self, service: SampleService):
        self.service = service

    def import_from_csv(self, file_path: str, operator: str, skip_errors: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        """从 CSV 导入样本
        必需列: sample_no, project, quantity, receiver, location
        可选列: damage_note, missing_tube_note
        """
        if not os.path.exists(file_path):
            return False, f"文件不存在: {file_path}", {}

        if not os.access(file_path, os.R_OK):
            return False, f"文件不可读: {file_path}", {}

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                samples_data = []
                for row in reader:
                    row = {k.strip(): v.strip() for k, v in row.items() if k}
                    samples_data.append(row)
        except UnicodeDecodeError:
            try:
                with open(file_path, "r", encoding="gbk") as f:
                    reader = csv.DictReader(f)
                    samples_data = []
                    for row in reader:
                        row = {k.strip(): v.strip() for k, v in row.items() if k}
                        samples_data.append(row)
            except Exception as e:
                return False, f"文件编码错误，仅支持 UTF-8 和 GBK: {str(e)}", {}
        except Exception as e:
            return False, f"读取文件失败: {str(e)}", {}

        if not samples_data:
            return False, "CSV 文件为空", {}

        required_fields = ["sample_no", "project", "quantity", "receiver", "location"]
        csv_columns = list(samples_data[0].keys())
        missing_fields = [f for f in required_fields if f not in csv_columns]
        if missing_fields:
            return False, f"CSV 缺少必需列: {', '.join(missing_fields)}", {}

        for row in samples_data:
            if "批次号" in row and "batch_no" not in row:
                row["batch_no"] = row["批次号"]
            elif "batch_no" in row and "批次号" not in row:
                row["批次号"] = row["batch_no"]

            if "batch_no" in row and not row["batch_no"]:
                del row["batch_no"]
            if "批次号" in row and not row["批次号"]:
                del row["批次号"]

        return self.service.bulk_import_samples(samples_data, operator, skip_errors)

    def import_from_json(self, file_path: str, operator: str, skip_errors: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        """从 JSON 导入样本"""
        if not os.path.exists(file_path):
            return False, f"文件不存在: {file_path}", {}

        if not os.access(file_path, os.R_OK):
            return False, f"文件不可读: {file_path}", {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict) and "samples" in data:
                samples_data = data["samples"]
            elif isinstance(data, list):
                samples_data = data
            else:
                return False, "JSON 格式错误，应为数组或包含 samples 字段的对象", {}
        except json.JSONDecodeError as e:
            return False, f"JSON 解析失败: {str(e)}", {}
        except Exception as e:
            return False, f"读取文件失败: {str(e)}", {}

        if not samples_data:
            return False, "JSON 数据为空", {}

        for row in samples_data:
            if "批次号" in row and "batch_no" not in row:
                row["batch_no"] = row["批次号"]
            elif "batch_no" in row and "批次号" not in row:
                row["批次号"] = row["batch_no"]

            if "batch_no" in row and not row["batch_no"]:
                del row["batch_no"]
            if "批次号" in row and not row["批次号"]:
                del row["批次号"]

        return self.service.bulk_import_samples(samples_data, operator, skip_errors)

    def export_to_csv(
        self,
        file_path: str,
        samples: List[Dict[str, Any]],
        include_history: bool = False
    ) -> Tuple[bool, str]:
        """导出到 CSV
        先写入临时文件，成功后再覆盖原文件，防止出错时覆盖原记录
        """
        directory = os.path.dirname(file_path)
        ok, msg = self.service.validate_export_path(directory)
        if not ok:
            return False, msg

        if os.path.exists(file_path) and not os.access(file_path, os.W_OK):
            return False, f"目标文件不可写: {file_path}"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_fd, temp_path = tempfile.mkstemp(suffix=".csv", prefix=f"export_{timestamp}_")
        os.close(temp_fd)

        try:
            with open(temp_path, "w", encoding="utf-8-sig", newline="") as f:
                fieldnames = [
                    "样本编号", "批次号", "项目", "数量", "接收人", "存放位置",
                    "状态", "破损备注", "缺管备注", "创建时间", "更新时间"
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for s in samples:
                    writer.writerow({
                        "样本编号": s.get("sample_no", ""),
                        "批次号": s.get("batch_no", ""),
                        "项目": s.get("project", ""),
                        "数量": s.get("quantity", ""),
                        "接收人": s.get("receiver", ""),
                        "存放位置": s.get("location", ""),
                        "状态": STATUS_MAP.get(s.get("status", ""), s.get("status", "")),
                        "破损备注": s.get("damage_note", ""),
                        "缺管备注": s.get("missing_tube_note", ""),
                        "创建时间": s.get("created_at", ""),
                        "更新时间": s.get("updated_at", "")
                    })

                if include_history:
                    f.write("\n\n--- 状态历史 ---\n\n")
                    history_fields = [
                        "样本编号", "原状态", "新状态", "操作人",
                        "备注", "异常类型", "操作时间"
                    ]
                    history_writer = csv.DictWriter(f, fieldnames=history_fields)
                    history_writer.writeheader()

                    for s in samples:
                        _, history = self.service.get_sample_timeline(s["id"])
                        for h in history:
                            history_writer.writerow({
                                "样本编号": s.get("sample_no", ""),
                                "原状态": h.get("from_display", ""),
                                "新状态": h.get("to_display", ""),
                                "操作人": h.get("operator", ""),
                                "备注": h.get("remark", ""),
                                "异常类型": h.get("exception_type", ""),
                                "操作时间": h.get("created_at", "")
                            })

            if os.path.exists(file_path):
                backup_path = f"{file_path}.bak_{timestamp}"
                shutil.copy2(file_path, backup_path)

            shutil.move(temp_path, file_path)

            return True, f"导出成功，共 {len(samples)} 条记录"
        except PermissionError:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False, "权限不足，无法写入文件"
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False, f"导出失败: {str(e)}"

    def export_to_json(
        self,
        file_path: str,
        samples: List[Dict[str, Any]],
        include_history: bool = False
    ) -> Tuple[bool, str]:
        """导出到 JSON
        先写入临时文件，成功后再覆盖原文件，防止出错时覆盖原记录
        """
        directory = os.path.dirname(file_path)
        ok, msg = self.service.validate_export_path(directory)
        if not ok:
            return False, msg

        if os.path.exists(file_path) and not os.access(file_path, os.W_OK):
            return False, f"目标文件不可写: {file_path}"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_fd, temp_path = tempfile.mkstemp(suffix=".json", prefix=f"export_{timestamp}_")
        os.close(temp_fd)

        try:
            export_data = []
            for s in samples:
                item = {
                    "sample_no": s.get("sample_no", ""),
                    "batch_no": s.get("batch_no", ""),
                    "project": s.get("project", ""),
                    "quantity": s.get("quantity", ""),
                    "receiver": s.get("receiver", ""),
                    "location": s.get("location", ""),
                    "status": s.get("status", ""),
                    "status_display": STATUS_MAP.get(s.get("status", ""), s.get("status", "")),
                    "damage_note": s.get("damage_note", ""),
                    "missing_tube_note": s.get("missing_tube_note", ""),
                    "created_at": s.get("created_at", ""),
                    "updated_at": s.get("updated_at", "")
                }

                if include_history:
                    _, history = self.service.get_sample_timeline(s["id"])
                    item["history"] = [
                        {
                            "from_status": h.get("from_status", ""),
                            "from_display": h.get("from_display", ""),
                            "to_status": h.get("to_status", ""),
                            "to_display": h.get("to_display", ""),
                            "operator": h.get("operator", ""),
                            "remark": h.get("remark", ""),
                            "exception_type": h.get("exception_type", ""),
                            "created_at": h.get("created_at", "")
                        }
                        for h in history
                    ]

                export_data.append(item)

            output = {
                "export_time": datetime.now().isoformat(timespec="seconds"),
                "count": len(export_data),
                "samples": export_data
            }

            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            if os.path.exists(file_path):
                backup_path = f"{file_path}.bak_{timestamp}"
                shutil.copy2(file_path, backup_path)

            shutil.move(temp_path, file_path)

            return True, f"导出成功，共 {len(samples)} 条记录"
        except PermissionError:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False, "权限不足，无法写入文件"
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False, f"导出失败: {str(e)}"

    def export_samples(
        self,
        directory: str,
        export_format: str = "csv",
        filters: Optional[Dict[str, Any]] = None,
        include_history: bool = False
    ) -> Tuple[bool, str, Optional[str]]:
        """按条件导出样本
        返回 (成功, 消息, 文件路径)
        """
        ok, msg = self.service.validate_export_path(directory)
        if not ok:
            return False, msg, None

        samples = self.service.get_samples(filters)
        if not samples:
            return False, "没有符合条件的样本可导出", None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"samples_export_{timestamp}.{export_format}"
        file_path = os.path.join(directory, filename)

        config = {
            "directory": directory,
            "format": export_format,
            "filters": filters or {}
        }
        self.service.save_export_config(config)

        if export_format == "csv":
            ok, msg = self.export_to_csv(file_path, samples, include_history)
        elif export_format == "json":
            ok, msg = self.export_to_json(file_path, samples, include_history)
        else:
            return False, f"不支持的导出格式: {export_format}", None

        return ok, msg, file_path if ok else None
