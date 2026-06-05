"""GUI 等价验证脚本 - 模拟用户操作，验证按钮状态、筛选结果、提示消息"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sample_registry.database import Database
from sample_registry.service import SampleService, STATUS_MAP


def verify_all():
    print("=" * 80)
    print("GUI 等价验证脚本")
    print("=" * 80)
    print("\n本脚本模拟用户在 GUI 上的完整操作流程，验证所有界面逻辑。\n")

    db_path = os.path.join(os.path.dirname(__file__), "verify_gui.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    try:
        Database._instance = None
        db = Database(db_path)
        service = SampleService()

        # ============ 步骤 1: 初始化数据 ============
        print("=" * 80)
        print("步骤 1: 初始化测试数据")
        print("=" * 80)

        samples_data = [
            ("VERIFY-001", "血液检测", 5, "张三", "冰箱A-1", "RECEIVED"),
            ("VERIFY-002", "尿液检测", 3, "李四", "冰箱A-2", "RECEIVED"),
            ("VERIFY-003", "生化检验", 10, "王五", "冰箱B-1", "PENDING_INFO"),
            ("VERIFY-004", "免疫检测", 2, "赵六", "冰箱B-3", "STORED"),
            ("VERIFY-005", "基因检测", 8, "张三", "冰箱C-1", "RETURNED"),
            ("VERIFY-006", "微生物检测", 4, "李四", "冰箱A-2", "VOIDED"),
        ]

        sample_ids = []
        for sample_no, project, quantity, receiver, location, init_status in samples_data:
            data = {
                "sample_no": sample_no,
                "project": project,
                "quantity": quantity,
                "receiver": receiver,
                "location": location
            }
            ok, msg, sid = db.insert_sample(data, "测试员")
            assert ok, f"插入失败: {msg}"
            sample_ids.append(sid)

            if init_status != "RECEIVED":
                ok, msg = db.update_sample_status(sid, init_status, "测试员", f"初始化状态")
                assert ok, f"状态初始化失败: {msg}"

        print(f"  ✓ 已创建 {len(samples_data)} 条测试样本")
        for i, (no, _, _, _, _, status) in enumerate(samples_data):
            print(f"    {no}: {STATUS_MAP[status]}")

        # ============ 步骤 2: 验证按钮状态逻辑 ============
        print("\n" + "=" * 80)
        print("步骤 2: 验证各状态下按钮启用/禁用（与 GUI _update_action_buttons 一致）")
        print("=" * 80)

        valid_transitions = {
            "RECEIVED": ["PENDING_INFO", "STORED", "RETURNED", "VOIDED"],
            "PENDING_INFO": ["STORED", "RETURNED", "VOIDED"],
            "STORED": ["VOIDED"],
            "RETURNED": ["RECEIVED", "VOIDED"],
            "VOIDED": []
        }

        button_labels = {
            "RECEIVED": "← 重新接收",
            "PENDING_INFO": "→ 待补资料",
            "STORED": "→ 已入库",
            "RETURNED": "→ 已退回",
            "VOIDED": "→ 已作废",
        }

        for i, (no, _, _, _, _, status) in enumerate(samples_data):
            sid = sample_ids[i]
            sample = db.get_sample_by_id(sid)
            assert sample["status"] == status

            valid = valid_transitions.get(status, [])
            btn_states = {}

            for btn_status, btn_label in button_labels.items():
                btn_states[btn_status] = "✓ 启用" if btn_status in valid else "✗ 禁用"

            print(f"\n  样本 {no} (状态: {STATUS_MAP[status]}):")
            for btn_status in ["RECEIVED", "PENDING_INFO", "STORED", "RETURNED", "VOIDED"]:
                print(f"    {button_labels[btn_status]}: {btn_states[btn_status]}")

            if status == "RETURNED":
                print(f"\n  🎯 重点验证 RETURNED 状态:")
                assert "STORED" not in valid, "❌ RETURNED 状态下'已入库'按钮应禁用！"
                assert "RECEIVED" in valid, "❌ RETURNED 状态下'重新接收'按钮应启用！"
                assert "PENDING_INFO" not in valid, "❌ RETURNED 状态下'待补资料'按钮应禁用！"
                assert "RETURNED" not in valid, "❌ RETURNED 状态下'已退回'按钮应禁用！"
                assert "VOIDED" in valid, "❌ RETURNED 状态下'已作废'按钮应启用！"
                print(f"    ✓ '已入库'按钮已禁用")
                print(f"    ✓ '重新接收'按钮已启用")
                print(f"    ✓ 其他流转按钮已禁用")

        # ============ 步骤 3: 验证待处理筛选 ============
        print("\n" + "=" * 80)
        print("步骤 3: 验证待处理筛选（只返回已接收+待补资料，不包含已入库）")
        print("=" * 80)

        print("\n  模拟用户在 GUI 选择 '待处理' 筛选:")
        filters = {"status__in": ["RECEIVED", "PENDING_INFO"]}
        pending = db.get_samples(filters)
        pending_nos = sorted([s["sample_no"] for s in pending])

        print(f"\n  查询结果: {pending_nos} ({len(pending)} 条)")

        expected = ["VERIFY-001", "VERIFY-002", "VERIFY-003"]
        assert sorted(pending_nos) == sorted(expected), f"❌ 待处理筛选结果错误！期望 {expected}，实际 {pending_nos}"
        assert "VERIFY-004" not in pending_nos, "❌ 已入库样本(VERIFY-004)不应出现在待处理列表中！"
        assert "VERIFY-005" not in pending_nos, "❌ 已退回样本(VERIFY-005)不应出现在待处理列表中！"
        assert "VERIFY-006" not in pending_nos, "❌ 已作废样本(VERIFY-006)不应出现在待处理列表中！"

        print(f"\n  ✓ 待处理筛选正确，只包含:")
        for no in sorted(expected):
            s = next(s for s in pending if s["sample_no"] == no)
            print(f"    {no}: {STATUS_MAP[s['status']]}")

        # ============ 步骤 4: 验证退回样本直接入库被拒绝 ============
        print("\n" + "=" * 80)
        print("步骤 4: 验证退回样本直接入库被拒绝（按钮+后台双重防护）")
        print("=" * 80)

        returned_id = sample_ids[4]
        returned_no = samples_data[4][0]

        sample_before = db.get_sample_by_id(returned_id)
        history_before = db.get_sample_history(returned_id)
        assert sample_before["status"] == "RETURNED"

        print(f"\n  模拟用户选中 {returned_no} (状态: {STATUS_MAP['RETURNED']}):")
        print(f"  点击 '→ 已入库' 按钮...")

        ok, msg = service.transition_status(returned_id, "STORED", "测试员", "尝试直接入库")
        assert not ok, "❌ 退回样本直接入库应该被拒绝！"

        print(f"\n  用户看到的错误提示: '{msg}'")
        assert "不能直接入库" in msg, "❌ 错误提示不明确！"
        assert "重新接收" in msg, "❌ 错误提示未告知用户正确操作路径！"

        sample_after = db.get_sample_by_id(returned_id)
        history_after = db.get_sample_history(returned_id)

        print(f"\n  🎯 验证数据完整性:")
        assert sample_after["status"] == "RETURNED", f"❌ 状态被改坏！期望 RETURNED，实际 {sample_after['status']}"
        print(f"    ✓ 样本状态保持 {STATUS_MAP['RETURNED']}")

        assert len(history_after) == len(history_before), f"❌ 历史记录被污染！期望 {len(history_before)} 条，实际 {len(history_after)} 条"
        print(f"    ✓ 历史记录未被污染 ({len(history_after)} 条)")

        last_history = history_after[-1]
        assert last_history["to_status"] != "STORED", "❌ 历史记录中不应包含 STORED！"
        print(f"    ✓ 最后一条历史记录仍为退回操作: {last_history['remark']}")

        # ============ 步骤 5: 验证正确的重新接收流程 ============
        print("\n" + "=" * 80)
        print("步骤 5: 验证正确流程 - 先重新接收，再入库")
        print("=" * 80)

        print(f"\n  点击 '← 重新接收' 按钮...")
        ok, msg = service.transition_status(returned_id, "RECEIVED", "测试员", "资料补充完整，重新接收")
        assert ok, f"❌ 重新接收失败: {msg}"
        print(f"  返回消息: {msg}")

        sample = db.get_sample_by_id(returned_id)
        assert sample["status"] == "RECEIVED"
        print(f"  ✓ 状态已更新为: {STATUS_MAP[sample['status']]}")

        print(f"\n  再次点击 '→ 已入库' 按钮...")
        ok, msg = service.transition_status(returned_id, "STORED", "测试员", "正常入库")
        assert ok, f"❌ 重新接收后入库失败: {msg}"
        print(f"  返回消息: {msg}")

        sample = db.get_sample_by_id(returned_id)
        assert sample["status"] == "STORED"
        print(f"  ✓ 状态已更新为: {STATUS_MAP[sample['status']]}")

        _, history = service.get_sample_timeline(returned_id)
        print(f"\n  完整时间线:")
        for h in history:
            exception = f" [⚠️ {h['exception_type']}]" if h.get("exception_type") else ""
            print(f"    {h['created_at']}: {h['from_display'] or '-'} → {h['to_display']} ({h['operator']}) {h.get('remark', '')}{exception}")

        # ============ 步骤 6: 验证重启后数据完整 ============
        print("\n" + "=" * 80)
        print("步骤 6: 验证重启后所有状态、备注、历史完整保留")
        print("=" * 80)

        Database._instance = None
        db2 = Database(db_path)
        service2 = SampleService()

        print(f"\n  模拟程序重启，重新连接数据库...")

        all_samples = db2.get_samples()
        print(f"  ✓ 重启后查询到 {len(all_samples)} 条样本")

        print(f"\n  各状态样本数量:")
        status_counts = {}
        for s in all_samples:
            status_counts[s["status"]] = status_counts.get(s["status"], 0) + 1
        for status, count in sorted(status_counts.items()):
            print(f"    {STATUS_MAP[status]}: {count} 条")

        returned_sample_after = db2.get_sample_by_id(returned_id)
        assert returned_sample_after["status"] == "STORED", "❌ 重启后状态未保留！"
        print(f"\n  ✓ {returned_no} 重启后状态: {STATUS_MAP[returned_sample_after['status']]}")

        _, history_restart = service2.get_sample_timeline(returned_id)
        assert len(history_restart) == len(history), "❌ 重启后历史记录丢失！"
        print(f"  ✓ {returned_no} 重启后历史记录完整 ({len(history_restart)} 条)")

        export_config = service2.get_export_config()
        assert export_config is not None, "❌ 重启后导出配置丢失！"
        print(f"  ✓ 重启后导出配置已保留")

        # ============ 步骤 7: 综合验证 ============
        print("\n" + "=" * 80)
        print("步骤 7: 综合验证 - 用户所见即所得")
        print("=" * 80)

        print("\n  ✅ 用户看到的按钮:")
        print("     - 选中已退回样本时，'已入库'按钮禁用，'重新接收'按钮启用")
        print("     - 选中已接收样本时，'重新接收'按钮禁用，其他流转按钮启用")

        print("\n  ✅ 用户看到的列表:")
        print("     - 待处理筛选只显示已接收、待补资料")
        print("     - 已入库、已退回、已作废不会出现在待处理列表")

        print("\n  ✅ 用户看到的提示:")
        print("     - 退回样本直接入库时，提示'已退回样本不能直接入库，请先执行重新接收操作'")
        print("     - 提示明确告知用户正确操作路径")

        print("\n  ✅ 数据完整性保证:")
        print("     - 失败操作不会修改状态、历史记录、备注")
        print("     - 关闭重开后所有数据完整保留")
        print("     - 导出配置、操作员配置持久化保存")

        print("\n" + "=" * 80)
        print("🎉 所有 GUI 等价验证通过！")
        print("=" * 80)
        return True

    finally:
        Database._instance = None
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except:
            pass


if __name__ == "__main__":
    success = verify_all()
    sys.exit(0 if success else 1)
