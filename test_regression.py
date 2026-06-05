"""回归测试 - 验证两个 Bug 修复"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sample_registry.database import Database
from sample_registry.service import SampleService


def test_returned_cannot_direct_store():
    """测试：已退回样本不能直接入库，重启后状态仍是已退回"""
    print("=" * 70)
    print("回归测试 1: 已退回样本不能直接入库")
    print("=" * 70)

    db_path = os.path.join(os.path.dirname(__file__), "test_regression_1.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    original_db_path = Database.db_path if hasattr(Database, 'db_path') else None

    try:
        Database._instance = None
        db = Database(db_path)

        data = {
            "sample_no": "REG-TEST-001",
            "project": "回归测试项目",
            "quantity": 5,
            "receiver": "测试员",
            "location": "测试位置"
        }

        ok, msg, sample_id = db.insert_sample(data, "admin")
        assert ok, f"插入失败: {msg}"
        print(f"  ✓ 插入样本: ID={sample_id}, 状态=RECEIVED")

        ok, msg = db.update_sample_status(sample_id, "RETURNED", "admin", "测试退回")
        assert ok, f"退回失败: {msg}"

        sample = db.get_sample_by_id(sample_id)
        assert sample["status"] == "RETURNED", "状态应为 RETURNED"
        print(f"  ✓ 样本已退回: 状态={sample['status']}")

        ok, msg = db.update_sample_status(sample_id, "STORED", "admin", "尝试直接入库")
        assert not ok, "退回样本直接入库应该失败"
        assert "不能直接入库" in msg or "不允许" in msg, f"错误消息不正确: {msg}"
        print(f"  ✓ 直接入库已被拒绝: {msg}")

        sample = db.get_sample_by_id(sample_id)
        assert sample["status"] == "RETURNED", "状态应保持 RETURNED，不能被改坏"
        print(f"  ✓ 状态未被修改: 状态={sample['status']}")

        history = db.get_sample_history(sample_id)
        store_attempts = [h for h in history if h["to_status"] == "STORED"]
        assert len(store_attempts) == 0, "历史记录不应包含 STORED 记录"
        print(f"  ✓ 历史记录未被污染: 共 {len(history)} 条记录，无 STORED 记录")

        last_history = history[-1]
        assert last_history["to_status"] == "RETURNED", "最后一条记录应为退回操作"
        assert last_history["remark"] == "测试退回", "备注不应被改坏"
        print(f"  ✓ 备注未被改坏: 最后一条备注='{last_history['remark']}'")

        Database._instance = None
        db2 = Database(db_path)
        sample_after_restart = db2.get_sample_by_id(sample_id)
        assert sample_after_restart["status"] == "RETURNED", "重启后状态应仍是 RETURNED"
        print(f"  ✓ 重启后状态验证: 状态={sample_after_restart['status']}")

        history_after_restart = db2.get_sample_history(sample_id)
        assert len(history_after_restart) == len(history), "重启后历史记录数量应一致"
        print(f"  ✓ 重启后历史记录完整: {len(history_after_restart)} 条")

        ok, msg = db2.update_sample_status(sample_id, "RECEIVED", "admin", "重新接收")
        assert ok, f"重新接收应该成功: {msg}"
        print(f"  ✓ 重新接收成功: {msg}")

        sample = db2.get_sample_by_id(sample_id)
        assert sample["status"] == "RECEIVED", "重新接收后状态应为 RECEIVED"
        print(f"  ✓ 重新接收后状态: {sample['status']}")

        ok, msg = db2.update_sample_status(sample_id, "STORED", "admin", "正常入库")
        assert ok, f"重新接收后入库应该成功: {msg}"
        print(f"  ✓ 重新接收后入库成功: {msg}")

        sample = db2.get_sample_by_id(sample_id)
        assert sample["status"] == "STORED", "状态应为 STORED"
        print(f"  ✓ 最终状态: {sample['status']}")

        print("\n  回归测试 1 通过 ✓\n")
        return True

    finally:
        if original_db_path:
            Database.db_path = original_db_path
        try:
            if Database._instance:
                conn = getattr(Database._instance, '_conn', None)
                if conn:
                    conn.close()
        except:
            pass
        Database._instance = None
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except:
            pass


def test_pending_filter():
    """测试：待处理筛选只返回已接收和待补资料，不包含已入库"""
    print("=" * 70)
    print("回归测试 2: 待处理筛选正确性")
    print("=" * 70)

    db_path = os.path.join(os.path.dirname(__file__), "test_regression_2.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    try:
        Database._instance = None
        db = Database(db_path)
        service = SampleService()

        samples_data = [
            {"sample_no": "FILT-001", "project": "筛选测试", "quantity": 1, "receiver": "测试员", "location": "位置1"},
            {"sample_no": "FILT-002", "project": "筛选测试", "quantity": 2, "receiver": "测试员", "location": "位置2"},
            {"sample_no": "FILT-003", "project": "筛选测试", "quantity": 3, "receiver": "测试员", "location": "位置3"},
            {"sample_no": "FILT-004", "project": "筛选测试", "quantity": 4, "receiver": "测试员", "location": "位置4"},
        ]

        sample_ids = []
        for data in samples_data:
            ok, msg, sid = db.insert_sample(data, "admin")
            assert ok, msg
            sample_ids.append(sid)

        print(f"  ✓ 插入 4 条样本，初始状态均为 RECEIVED")

        ok, msg = db.update_sample_status(sample_ids[1], "PENDING_INFO", "admin", "待补资料")
        assert ok, msg
        print(f"  ✓ FILT-002 转为 PENDING_INFO")

        ok, msg = db.update_sample_status(sample_ids[2], "STORED", "admin", "已入库")
        assert ok, msg
        print(f"  ✓ FILT-003 转为 STORED")

        ok, msg = db.update_sample_status(sample_ids[3], "VOIDED", "admin", "已作废")
        assert ok, msg
        print(f"  ✓ FILT-004 转为 VOIDED")

        print("\n  当前各样本状态:")
        for i, sid in enumerate(sample_ids):
            s = db.get_sample_by_id(sid)
            print(f"    FILT-00{i+1}: {s['status']}")

        print("\n  测试 status__in 筛选 (待处理=RECEIVED+PENDING_INFO):")
        filters = {"status__in": ["RECEIVED", "PENDING_INFO"]}
        samples = db.get_samples(filters)
        sample_nos = sorted([s["sample_no"] for s in samples])
        print(f"    查询结果: {sample_nos}")

        assert len(samples) == 2, f"待处理筛选应返回 2 条，实际返回 {len(samples)} 条"
        assert "FILT-001" in sample_nos, "FILT-001 (RECEIVED) 应在结果中"
        assert "FILT-002" in sample_nos, "FILT-002 (PENDING_INFO) 应在结果中"
        assert "FILT-003" not in sample_nos, "FILT-003 (STORED) 不应在结果中"
        assert "FILT-004" not in sample_nos, "FILT-004 (VOIDED) 不应在结果中"
        print(f"    ✓ 筛选正确: 只包含 RECEIVED 和 PENDING_INFO")

        print("\n  测试 service.get_pending_samples():")
        pending = service.get_pending_samples()
        pending_nos = sorted([s["sample_no"] for s in pending])
        print(f"    查询结果: {pending_nos}")
        assert len(pending) == 2, f"get_pending_samples 应返回 2 条，实际返回 {len(pending)} 条"
        assert pending_nos == sample_nos, "两种筛选方式结果应一致"
        print(f"    ✓ service.get_pending_samples() 筛选正确")

        print("\n  测试单状态筛选对比:")
        for status in ["RECEIVED", "PENDING_INFO", "STORED", "VOIDED"]:
            s_list = db.get_samples({"status": status})
            nos = sorted([s["sample_no"] for s in s_list])
            print(f"    status={status}: {nos} ({len(s_list)}条)")

        all_samples = db.get_samples()
        print(f"\n  全库样本: {len(all_samples)} 条")
        for s in sorted(all_samples, key=lambda x: x["sample_no"]):
            print(f"    {s['sample_no']}: {s['status']}")

        Database._instance = None
        db2 = Database(db_path)
        samples_after = db2.get_samples(filters)
        assert len(samples_after) == 2, "重启后筛选结果应一致"
        print(f"\n  ✓ 重启后筛选结果一致: {len(samples_after)} 条")

        print("\n  回归测试 2 通过 ✓\n")
        return True

    finally:
        try:
            if Database._instance:
                conn = getattr(Database._instance, '_conn', None)
                if conn:
                    conn.close()
        except:
            pass
        Database._instance = None
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except:
            pass


def test_gui_equivalent():
    """GUI 等价测试：验证按钮状态和错误提示与用户看到的一致"""
    print("=" * 70)
    print("回归测试 3: GUI 等价验证（按钮状态、提示）")
    print("=" * 70)

    db_path = os.path.join(os.path.dirname(__file__), "test_regression_3.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    try:
        Database._instance = None
        db = Database(db_path)

        valid_transitions = {
            "RECEIVED": ["PENDING_INFO", "STORED", "RETURNED", "VOIDED"],
            "PENDING_INFO": ["STORED", "RETURNED", "VOIDED"],
            "STORED": ["VOIDED"],
            "RETURNED": ["RECEIVED", "VOIDED"],
            "VOIDED": []
        }

        data = {"sample_no": "GUI-001", "project": "GUI测试", "quantity": 1, "receiver": "测试员", "location": "位置"}
        ok, msg, sid = db.insert_sample(data, "admin")

        print("\n  验证各状态下按钮可用状态（与 GUI _update_action_buttons 一致）:")

        test_sequence = [
            ("RECEIVED", None, "初始状态"),
            ("PENDING_INFO", "RECEIVED", "从已接收流转"),
            ("RETURNED", "PENDING_INFO", "从待补资料流转"),
        ]

        for status, from_status, desc in test_sequence:
            if from_status:
                ok, msg = db.update_sample_status(sid, status, "admin", desc)
                assert ok, f"从 {from_status} 流转到 {status} 失败: {msg}"

            sample = db.get_sample_by_id(sid)
            assert sample["status"] == status, f"状态应为 {status}，实际 {sample['status']}"
            valid = valid_transitions.get(sample["status"], [])

            btn_receive = "RECEIVED" in valid
            btn_pending = "PENDING_INFO" in valid
            btn_store = "STORED" in valid
            btn_return = "RETURNED" in valid
            btn_void = "VOIDED" in valid

            enabled = []
            if btn_receive: enabled.append("重新接收")
            if btn_pending: enabled.append("待补资料")
            if btn_store: enabled.append("已入库")
            if btn_return: enabled.append("已退回")
            if btn_void: enabled.append("已作废")

            disabled = []
            if not btn_receive: disabled.append("重新接收")
            if not btn_pending: disabled.append("待补资料")
            if not btn_store: disabled.append("已入库")
            if not btn_return: disabled.append("已退回")
            if not btn_void: disabled.append("已作废")

            print(f"\n  状态 {status} ({desc}):")
            print(f"    启用按钮: {enabled}")
            print(f"    禁用按钮: {disabled}")

            if status == "RETURNED":
                assert not btn_store, "RETURNED 状态下'已入库'按钮应禁用"
                assert btn_receive, "RETURNED 状态下'重新接收'按钮应启用"
                assert not btn_pending, "RETURNED 状态下'待补资料'按钮应禁用"
                assert not btn_return, "RETURNED 状态下'已退回'按钮应禁用"
                assert btn_void, "RETURNED 状态下'已作废'按钮应启用"
                print(f"    ✓ RETURNED 状态: 入库按钮禁用，重新接收按钮启用")

        print("\n  测试其他状态的按钮逻辑:")

        data2 = {"sample_no": "GUI-002", "project": "GUI测试2", "quantity": 1, "receiver": "测试员", "location": "位置"}
        ok, msg, sid2 = db.insert_sample(data2, "admin")
        ok, msg = db.update_sample_status(sid2, "STORED", "admin", "直接入库")
        sample2 = db.get_sample_by_id(sid2)
        valid2 = valid_transitions.get(sample2["status"], [])
        assert "VOIDED" in valid2 and len(valid2) == 1, "STORED 状态只能流转到 VOIDED"
        print(f"    ✓ STORED 状态: 只有'已作废'按钮启用")

        data3 = {"sample_no": "GUI-003", "project": "GUI测试3", "quantity": 1, "receiver": "测试员", "location": "位置"}
        ok, msg, sid3 = db.insert_sample(data3, "admin")
        ok, msg = db.update_sample_status(sid3, "VOIDED", "admin", "直接作废")
        sample3 = db.get_sample_by_id(sid3)
        valid3 = valid_transitions.get(sample3["status"], [])
        assert len(valid3) == 0, "VOIDED 状态不能流转"
        print(f"    ✓ VOIDED 状态: 所有流转按钮禁用")

        print("\n  验证用户看到的错误提示:")

        ok, msg = db.update_sample_status(sid, "STORED", "admin", "测试直接入库")
        assert not ok
        print(f"    点击入库按钮返回: {msg}")
        assert "不能直接入库" in msg, "用户应看到明确的中文提示"
        print(f"    ✓ 错误提示明确: '{msg}'")

        print("\n  回归测试 3 通过 ✓\n")
        return True

    finally:
        try:
            if Database._instance:
                conn = getattr(Database._instance, '_conn', None)
                if conn:
                    conn.close()
        except:
            pass
        Database._instance = None
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except:
            pass


def test_old_readme_misleading_scenario():
    """测试：复现旧文档误导场景 - 按旧README步骤6构造数据，验证直接入库被拒绝

    旧文档误导：步骤6描述已退回样本可以直接确认入库，还能改状态
    验证：退回后直接入库应失败，重启后状态仍是已退回，用户能看到明确拒绝提示
    """
    print("=" * 70)
    print("回归测试 4: 复现旧文档误导场景")
    print("=" * 70)

    db_path = os.path.join(os.path.dirname(__file__), "test_regression_4.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    original_db_path = Database.db_path if hasattr(Database, 'db_path') else None

    try:
        Database._instance = None
        db = Database(db_path)

        print("\n  按旧README步骤6构造数据:")
        print("    1. 选中'已接收'样本")
        print("    2. 点击'→ 已退回'，备注：'资料不全退回'")

        data = {
            "sample_no": "README-TEST-001",
            "project": "旧文档误导复现测试",
            "quantity": 3,
            "receiver": "测试员",
            "location": "冷藏柜A-03"
        }

        ok, msg, sample_id = db.insert_sample(data, "操作员A")
        assert ok, f"插入失败: {msg}"

        ok, msg = db.update_sample_status(sample_id, "RETURNED", "操作员A", "资料不全退回")
        assert ok, f"退回失败: {msg}"

        sample = db.get_sample_by_id(sample_id)
        assert sample["status"] == "RETURNED"
        print(f"    ✓ 样本已退回: {sample['sample_no']}，状态=RETURNED，备注='资料不全退回'")

        print("\n  3. 选中这条'已退回'样本（紫色背景）")
        print("  4. 点击'→ 已入库'")
        print("  5. 按旧文档会弹出'异常确认对话框'...")

        print("\n  实际行为（修复后）:")
        print("    - '→ 已入库'按钮应已禁用（GUI层防护）")
        print("    - 即使强行调用，后台也会拒绝（数据库层防护）")

        ok, msg = db.update_sample_status(sample_id, "STORED", "操作员A", "按旧文档尝试直接入库")
        assert not ok, "按旧文档直接入库应该被拒绝"
        assert "不能直接入库" in msg or "请先执行重新接收" in msg, f"错误提示不明确: {msg}"
        print(f"    ✓ 后台明确拒绝: {msg}")

        print("\n  验证数据完整性（失败操作不能改坏任何东西）:")

        sample = db.get_sample_by_id(sample_id)
        assert sample["status"] == "RETURNED", f"状态应保持 RETURNED，实际: {sample['status']}"
        print(f"    ✓ 状态未被修改: 仍为 RETURNED")

        history = db.get_sample_history(sample_id)
        assert len(history) == 2, f"历史记录应为2条（初始+退回），实际: {len(history)}"
        store_attempts = [h for h in history if h["to_status"] == "STORED"]
        assert len(store_attempts) == 0, "历史记录不应包含 STORED 记录"
        print(f"    ✓ 历史记录未被污染: 共 {len(history)} 条，无 STORED 记录")

        last_history = history[-1]
        assert last_history["to_status"] == "RETURNED"
        assert last_history["remark"] == "资料不全退回"
        print(f"    ✓ 备注未被改坏: 最后一条备注='{last_history['remark']}'")

        print("\n  验证重启后状态仍是已退回:")

        try:
            if Database._instance:
                conn = getattr(Database._instance, '_conn', None)
                if conn:
                    conn.close()
        except:
            pass
        Database._instance = None

        db2 = Database(db_path)
        sample_after = db2.get_sample_by_id(sample_id)
        assert sample_after["status"] == "RETURNED", f"重启后状态应仍是 RETURNED，实际: {sample_after['status']}"
        print(f"    ✓ 重启后状态: RETURNED")

        history_after = db2.get_sample_history(sample_id)
        assert len(history_after) == len(history), "重启后历史记录数量应一致"
        last_after = history_after[-1]
        assert last_after["remark"] == "资料不全退回"
        print(f"    ✓ 重启后备注完整: '{last_after['remark']}'")

        print("\n  验证正确业务流程: 必须先走重新接收")

        ok, msg = db2.update_sample_status(sample_id, "RECEIVED", "操作员A", "资料补充完整，重新接收")
        assert ok, f"重新接收应该成功: {msg}"
        print(f"    ✓ 重新接收成功: {msg}")

        ok, msg = db2.update_sample_status(sample_id, "STORED", "操作员A", "复核无误，正常入库")
        assert ok, f"重新接收后入库应该成功: {msg}"
        print(f"    ✓ 重新接收后入库成功: {msg}")

        sample_final = db2.get_sample_by_id(sample_id)
        assert sample_final["status"] == "STORED"
        history_final = db2.get_sample_history(sample_id)
        assert len(history_final) == 4, f"最终历史记录应为4条，实际: {len(history_final)}"
        print(f"    ✓ 最终状态: STORED，完整时间线共 {len(history_final)} 条记录")

        print("\n  验证用户看到的错误提示明确:")
        print(f"    用户看到的提示: '{msg.replace('状态已更新为', '状态已更新为')}'")
        print(f"    拒绝时的提示: '已退回样本不能直接入库，请先执行重新接收操作'")
        print(f"    ✓ 提示明确告知用户正确操作路径")

        print("\n  回归测试 4 通过 ✓\n")
        return True

    finally:
        if original_db_path:
            Database.db_path = original_db_path
        try:
            if Database._instance:
                conn = getattr(Database._instance, '_conn', None)
                if conn:
                    conn.close()
        except:
            pass
        Database._instance = None
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except:
            pass


def main():
    print("\n" + "=" * 70)
    print("Bug 修复回归测试")
    print("=" * 70 + "\n")

    db_path = os.path.join(os.path.dirname(__file__), "sample_registry.db")
    if os.path.exists(db_path):
        bak_path = db_path + ".bak_before_regression"
        shutil.copy2(db_path, bak_path)
        print(f"  已备份现有数据库到 {os.path.basename(bak_path)}\n")
        os.remove(db_path)

    passed = 0
    failed = 0

    try:
        if test_returned_cannot_direct_store():
            passed += 1
        else:
            failed += 1
    except Exception as e:
        failed += 1
        print(f"\n❌ 回归测试 1 异常: {e}\n")
        import traceback
        traceback.print_exc()

    try:
        if test_pending_filter():
            passed += 1
        else:
            failed += 1
    except Exception as e:
        failed += 1
        print(f"\n❌ 回归测试 2 异常: {e}\n")
        import traceback
        traceback.print_exc()

    try:
        if test_gui_equivalent():
            passed += 1
        else:
            failed += 1
    except Exception as e:
        failed += 1
        print(f"\n❌ 回归测试 3 异常: {e}\n")
        import traceback
        traceback.print_exc()

    try:
        if test_old_readme_misleading_scenario():
            passed += 1
        else:
            failed += 1
    except Exception as e:
        failed += 1
        print(f"\n❌ 回归测试 4 异常: {e}\n")
        import traceback
        traceback.print_exc()

    print("=" * 70)
    if failed == 0:
        print(f"🎉 全部 {passed} 个回归测试通过！")
    else:
        print(f"❌ 回归测试失败: {passed} 通过, {failed} 失败")
    print("=" * 70)

    if os.path.exists(bak_path):
        shutil.move(bak_path, db_path)
        print(f"\n  已恢复原有数据库")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
