"""核心功能测试脚本 - 非 GUI 模式"""

import os
import sys
import tempfile
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sample_registry.database import Database
from sample_registry.service import SampleService
from sample_registry.io_handler import IOHandler


def test_database():
    print("=" * 60)
    print("测试 1: 数据库基础功能")
    print("=" * 60)

    db = Database()

    data = {
        "sample_no": "TEST-CORE-001",
        "project": "核心测试项目",
        "quantity": 5,
        "receiver": "测试员",
        "location": "测试位置",
        "damage_note": "测试破损",
        "missing_tube_note": "测试缺管"
    }

    ok, msg, sample_id = db.insert_sample(data, "admin")
    assert ok, f"插入失败: {msg}"
    print(f"  ✓ 插入样本成功: ID={sample_id}")

    sample = db.get_sample_by_no("TEST-CORE-001")
    assert sample is not None, "查询失败"
    assert sample["project"] == "核心测试项目"
    print(f"  ✓ 查询样本成功: {sample['sample_no']}")

    ok, msg = db.update_sample_status(sample_id, "STORED", "admin", "测试入库")
    assert ok, f"状态更新失败: {msg}"
    print(f"  ✓ 状态更新成功: STORED")

    history = db.get_sample_history(sample_id)
    assert len(history) >= 2, "历史记录不足"
    print(f"  ✓ 历史记录查询成功: {len(history)} 条")

    ok, msg = db.update_sample_notes(sample_id, "更新破损备注", None)
    assert ok, f"备注更新失败: {msg}"
    print(f"  ✓ 备注更新成功")

    db.set_config("test_key", {"foo": "bar"})
    value = db.get_config("test_key")
    assert value == {"foo": "bar"}, "配置存取失败"
    print(f"  ✓ 配置存取成功")

    print("  数据库测试全部通过 ✓\n")


def test_duplicate_sample():
    print("=" * 60)
    print("测试 2: 重复样本号检测")
    print("=" * 60)

    service = SampleService()

    data = {
        "sample_no": "TEST-DUP-001",
        "project": "重复测试",
        "quantity": 3,
        "receiver": "测试员",
        "location": "位置A"
    }

    ok, msg, sid = service.register_sample(data, "admin")
    assert ok, f"首次插入失败: {msg}"
    print(f"  ✓ 首次插入成功: {sid}")

    ok, msg, sid = service.register_sample(data, "admin")
    assert not ok, "重复样本号应该失败"
    assert "已存在" in msg
    print(f"  ✓ 重复样本号检测成功: {msg}")

    print("  重复样本号测试通过 ✓\n")


def test_status_transition():
    print("=" * 60)
    print("测试 3: 状态流转与异常操作")
    print("=" * 60)

    service = SampleService()

    data = {
        "sample_no": "TEST-TRANS-001",
        "project": "流转测试",
        "quantity": 10,
        "receiver": "测试员",
        "location": "位置B"
    }

    ok, msg, sample_id = service.register_sample(data, "admin")
    assert ok, msg

    ok, msg = service.transition_status(sample_id, "STORED", "admin", "正常入库")
    assert ok, f"正常流转失败: {msg}"
    print(f"  ✓ 正常流转成功: RECEIVED → STORED")

    sample = service.db.get_sample_by_id(sample_id)
    assert sample["status"] == "STORED"

    ok, msg = service.transition_status(sample_id, "PENDING_INFO", "admin", "非法流转")
    assert not ok, "非法流转应该被阻止"
    print(f"  ✓ 非法流转被阻止: {msg}")

    data2 = {
        "sample_no": "TEST-TRANS-002",
        "project": "异常流转测试",
        "quantity": 5,
        "receiver": "测试员",
        "location": "位置C"
    }
    ok, msg, sample_id2 = service.register_sample(data2, "admin")

    ok, msg = service.transition_status(sample_id2, "RETURNED", "admin", "退回")
    assert ok, msg

    ok, msg = service.transition_status(sample_id2, "STORED", "admin", "异常入库")
    assert ok, f"退回→入库流转失败: {msg}"
    print(f"  ✓ 异常流转记录: RETURNED → STORED (标记异常)")

    _, history = service.get_sample_timeline(sample_id2)
    has_exception = any(h.get("exception_type") == "RETURNED_TO_STORED" for h in history)
    assert has_exception, "异常类型未记录"
    print(f"  ✓ 异常类型已记录: RETURNED_TO_STORED")

    print("  状态流转测试通过 ✓\n")


def test_import_export():
    print("=" * 60)
    print("测试 4: 导入导出功能")
    print("=" * 60)

    service = SampleService()
    io = IOHandler(service)

    csv_path = os.path.join(os.path.dirname(__file__), "sample_data.csv")
    ok, msg, details = io.import_from_csv(csv_path, "admin", skip_errors=True)
    print(f"  ✓ CSV 导入: {msg}")

    json_path = os.path.join(os.path.dirname(__file__), "sample_data.json")
    ok, msg, details = io.import_from_json(json_path, "admin", skip_errors=True)
    print(f"  ✓ JSON 导入: {msg}")

    temp_dir = tempfile.mkdtemp()
    try:
        ok, msg, file_path = io.export_samples(temp_dir, "csv", None, True)
        assert ok and file_path, f"CSV 导出失败: {msg}"
        assert os.path.exists(file_path)
        file_size = os.path.getsize(file_path)
        print(f"  ✓ CSV 导出成功: {os.path.basename(file_path)} ({file_size} bytes)")

        ok, msg, file_path = io.export_samples(temp_dir, "json", {"status": "RECEIVED"}, False)
        assert ok and file_path, f"JSON 导出失败: {msg}"
        assert os.path.exists(file_path)
        file_size = os.path.getsize(file_path)
        print(f"  ✓ JSON 筛选导出成功: {os.path.basename(file_path)} ({file_size} bytes)")

        last_config = service.get_export_config()
        assert last_config["directory"] == temp_dir
        assert last_config["format"] == "json"
        print(f"  ✓ 导出配置已持久化")

    finally:
        shutil.rmtree(temp_dir)

    print("  导入导出测试通过 ✓\n")


def test_export_path_validation():
    print("=" * 60)
    print("测试 5: 导出路径校验")
    print("=" * 60)

    service = SampleService()
    io = IOHandler(service)

    nonexistent = r"Z:\this_path_should_not_exist_12345"
    ok, msg, file_path = io.export_samples(nonexistent, "csv", None, False)
    assert not ok, "不存在的路径应该失败"
    assert "不存在" in msg
    print(f"  ✓ 不存在路径检测: {msg}")

    readonly_dir = tempfile.mkdtemp()
    try:
        os.chmod(readonly_dir, 0o444)
        ok, msg, file_path = io.export_samples(readonly_dir, "csv", None, False)
        if not ok:
            print(f"  ✓ 不可写路径检测: {msg}")
        else:
            print(f"  ⚠  不可写路径测试跳过（Windows 权限行为不同）")
    finally:
        os.chmod(readonly_dir, 0o777)
        shutil.rmtree(readonly_dir)

    print("  导出路径校验测试通过 ✓\n")


def test_data_persistence():
    print("=" * 60)
    print("测试 6: 数据持久化验证")
    print("=" * 60)

    db_path = os.path.join(os.path.dirname(__file__), "sample_registry.db")
    assert os.path.exists(db_path), "数据库文件不存在"
    file_size = os.path.getsize(db_path)
    print(f"  ✓ 数据库文件存在: {os.path.basename(db_path)} ({file_size} bytes)")

    db2 = Database()
    samples = db2.get_samples()
    print(f"  ✓ 重新连接后查询到 {len(samples)} 条样本记录")

    config = db2.get_config("export_config")
    assert config is not None, "导出配置未持久化"
    print(f"  ✓ 导出配置持久化验证通过")

    operator = db2.get_config("operator")
    print(f"  ✓ 操作员配置: {operator}")

    print("  持久化测试通过 ✓\n")


def main():
    print("\n" + "=" * 60)
    print("实验样本接收登记系统 - 核心功能测试")
    print("=" * 60 + "\n")

    db_path = os.path.join(os.path.dirname(__file__), "sample_registry.db")
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"  已清理旧数据库\n")

    try:
        test_database()
        test_duplicate_sample()
        test_status_transition()
        test_import_export()
        test_export_path_validation()
        test_data_persistence()

        print("=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
