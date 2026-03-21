"""
Todo 管理器单元测试 (s11)
"""

import pytest

from coder.tools import TodoManager


class TestTodoManagerValidation:
    """测试 TodoManager 验证逻辑"""

    def test_todo_manager_max_items(self):
        """验证: 最多 20 个条目"""
        manager = TodoManager(max_items=20)
        items = [{"id": str(i), "text": f"Task {i}", "status": "pending"} for i in range(20)]
        # 20 个条目应该通过
        result = manager.update(items)
        assert "No todos." not in result
        assert "(0/20 completed)" in result

        # 21 个条目应该失败
        items.append({"id": "21", "text": "Task 21", "status": "pending"})
        with pytest.raises(ValueError, match="Too many todo items"):
            manager.update(items)

    def test_todo_manager_single_in_progress(self):
        """验证: 只能有一个 in_progress"""
        manager = TodoManager()
        items = [
            {"id": "1", "text": "Task 1", "status": "in_progress"},
            {"id": "2", "text": "Task 2", "status": "pending"},
        ]
        result = manager.update(items)
        assert "[>]" in result
        assert "[ ]" in result

        # 两个 in_progress 应该失败
        items[1]["status"] = "in_progress"
        with pytest.raises(ValueError, match="Only one todo can be in_progress"):
            manager.update(items)

    def test_todo_manager_invalid_status(self):
        """验证: 无效的 status 值"""
        manager = TodoManager()
        items = [{"id": "1", "text": "Task 1", "status": "invalid"}]
        with pytest.raises(ValueError, match="Invalid status"):
            manager.update(items)

    def test_todo_manager_empty_text(self):
        """验证: text 不能为空"""
        manager = TodoManager()
        items = [{"id": "1", "text": "", "status": "pending"}]
        with pytest.raises(ValueError, match="cannot be empty"):
            manager.update(items)

        # 纯空格也应该失败
        items[0]["text"] = "   "
        with pytest.raises(ValueError, match="cannot be empty"):
            manager.update(items)

    def test_todo_manager_missing_fields(self):
        """验证: 缺少必需字段"""
        manager = TodoManager()

        # 缺少 id
        with pytest.raises(ValueError, match="missing 'id'"):
            manager.update([{"text": "Task", "status": "pending"}])

        # 缺少 text
        with pytest.raises(ValueError, match="missing 'text'"):
            manager.update([{"id": "1", "status": "pending"}])

        # 缺少 status
        with pytest.raises(ValueError, match="missing 'status'"):
            manager.update([{"id": "1", "text": "Task"}])


class TestTodoManagerRender:
    """测试 TodoManager 渲染输出"""

    def test_todo_manager_render_pending(self):
        """渲染: pending 状态显示 [ ]"""
        manager = TodoManager()
        manager.update([{"id": "1", "text": "Task 1", "status": "pending"}])
        result = manager.render()
        assert "[ ]" in result
        assert "#1: Task 1" in result

    def test_todo_manager_render_in_progress(self):
        """渲染: in_progress 状态显示 [>]"""
        manager = TodoManager()
        manager.update([{"id": "1", "text": "Task 1", "status": "in_progress"}])
        result = manager.render()
        assert "[>]" in result
        assert "#1: Task 1" in result

    def test_todo_manager_render_completed(self):
        """渲染: completed 状态显示 [x]"""
        manager = TodoManager()
        manager.update([{"id": "1", "text": "Task 1", "status": "completed"}])
        result = manager.render()
        assert "[x]" in result
        assert "#1: Task 1" in result

    def test_todo_manager_render_completion_count(self):
        """渲染: 完成计数显示"""
        manager = TodoManager()
        manager.update(
            [
                {"id": "1", "text": "Task 1", "status": "completed"},
                {"id": "2", "text": "Task 2", "status": "pending"},
                {"id": "3", "text": "Task 3", "status": "completed"},
            ]
        )
        result = manager.render()
        assert "(2/3 completed)" in result

    def test_todo_manager_render_empty(self):
        """渲染: 空 todo 列表"""
        manager = TodoManager()
        result = manager.render()
        assert result == "No todos."


class TestNagReminderThreshold:
    """测试 Nag 提醒机制"""

    def test_nag_reminder_threshold(self):
        """验证: 计数器和注入逻辑（通过 AgentLoop 集成测试）"""
        # 这个测试主要在集成测试中验证
        # 这里只验证设置存在
        from coder.settings import settings

        assert hasattr(settings, "todo_nag_threshold")
        assert isinstance(settings.todo_nag_threshold, int)
        assert settings.todo_nag_threshold > 0
