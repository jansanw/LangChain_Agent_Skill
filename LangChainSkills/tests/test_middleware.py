# -*- coding: utf-8 -*-
"""
SkillMiddleware 单元测试
"""

import pytest
from unittest.mock import Mock, MagicMock

from core import SkillRegistry, BaseSkill, SkillMetadata
from middleware import SkillMiddleware
from langchain_core.tools import tool, BaseTool
from langgraph.types import Command


class MockSkill(BaseSkill):
    """测试用 Mock Skill"""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="test_skill",
            description="Test skill",
            version="1.0.0"
        )

    def get_loader_tool(self) -> BaseTool:
        @tool
        def skill_test_skill(runtime) -> Command:
            """Load test_skill capabilities."""
            return Command(update={"skills_loaded": ["test_skill"]})
        return skill_test_skill

    def get_tools(self) -> list:
        @tool
        def test_tool(param: str) -> str:
            """A test tool."""
            return f"Result: {param}"
        return [test_tool]


class TestSkillMiddleware:
    """SkillMiddleware 测试类"""

    def test_middleware_init(self):
        """测试中间件初始化"""
        registry = SkillRegistry()
        middleware = SkillMiddleware(registry, verbose=True)
        
        assert middleware.registry is registry
        assert middleware.verbose is True

    def test_get_skills_loaded_dict_state(self):
        """测试从字典状态获取 skills_loaded"""
        registry = SkillRegistry()
        middleware = SkillMiddleware(registry)
        
        state = {"skills_loaded": ["skill1", "skill2"]}
        result = middleware._get_skills_loaded(state)
        
        assert result == ["skill1", "skill2"]

    def test_get_skills_loaded_none_state(self):
        """测试空状态"""
        registry = SkillRegistry()
        middleware = SkillMiddleware(registry)
        
        result = middleware._get_skills_loaded(None)
        assert result == []

    def test_get_skills_loaded_empty_dict(self):
        """测试空字典状态"""
        registry = SkillRegistry()
        middleware = SkillMiddleware(registry)
        
        state = {}
        result = middleware._get_skills_loaded(state)
        assert result == []

    def test_get_filtered_tools_empty(self):
        """测试空 skills 的工具过滤"""
        registry = SkillRegistry()
        skill = MockSkill()
        registry.register(skill)
        
        middleware = SkillMiddleware(registry)
        tools = middleware._get_filtered_tools([])
        
        # 空时只返回 loader tools
        assert len(tools) == 1

    def test_get_filtered_tools_loaded(self):
        """测试已加载 skills 的工具过滤"""
        registry = SkillRegistry()
        skill = MockSkill()
        registry.register(skill)
        
        middleware = SkillMiddleware(registry)
        tools = middleware._get_filtered_tools(["test_skill"])
        
        # 加载后返回所有工具
        assert len(tools) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])