# -*- coding: utf-8 -*-
"""
SkillRegistry 单元测试
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from core import SkillRegistry, BaseSkill, SkillMetadata
from langchain_core.tools import tool, BaseTool
from langgraph.types import Command


class MockSkill(BaseSkill):
    """测试用 Mock Skill"""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="mock_skill",
            description="Test skill for unit testing",
            version="1.0.0",
            tags=["test", "mock"],
            dependencies=[],
            author="Test"
        )

    def get_loader_tool(self) -> BaseTool:
        @tool
        def skill_mock_skill(runtime) -> Command:
            """Load mock_skill capabilities."""
            return Command(update={"skills_loaded": ["mock_skill"]})
        return skill_mock_skill

    def get_tools(self) -> list:
        @tool
        def mock_tool(param: str) -> str:
            """A mock tool for testing."""
            return f"Result: {param}"
        return [mock_tool]


class TestSkillRegistry:
    """SkillRegistry 测试类"""

    def test_registry_init(self):
        """测试 Registry 初始化"""
        registry = SkillRegistry()
        assert len(registry) == 0

    def test_registry_register(self):
        """测试 Skill 注册"""
        registry = SkillRegistry()
        skill = MockSkill()
        
        registry.register(skill)
        
        assert "mock_skill" in registry
        assert len(registry) == 1

    def test_registry_unregister(self):
        """测试 Skill 注销"""
        registry = SkillRegistry()
        skill = MockSkill()
        
        registry.register(skill)
        registry.unregister("mock_skill")
        
        assert "mock_skill" not in registry
        assert len(registry) == 0

    def test_registry_get(self):
        """测试 Skill 获取"""
        registry = SkillRegistry()
        skill = MockSkill()
        
        registry.register(skill)
        retrieved = registry.get("mock_skill")
        
        assert retrieved is skill

    def test_registry_get_metadata(self):
        """测试元数据获取"""
        registry = SkillRegistry()
        skill = MockSkill()
        
        registry.register(skill)
        metadata = registry.get_metadata("mock_skill")
        
        assert metadata.name == "mock_skill"
        assert metadata.description == "Test skill for unit testing"

    def test_registry_list_skills(self):
        """测试 Skill 列表"""
        registry = SkillRegistry()
        skill = MockSkill()
        
        registry.register(skill)
        skill_list = registry.list_skills()
        
        assert "mock_skill" in skill_list

    def test_registry_get_all_tools(self):
        """测试获取所有工具"""
        registry = SkillRegistry()
        skill = MockSkill()
        
        registry.register(skill)
        tools = registry.get_all_tools()
        
        # 应该包含 loader tool 和普通 tool
        assert len(tools) == 2

    def test_registry_get_tools_for_skills(self):
        """测试按 Skill 获取工具"""
        registry = SkillRegistry()
        skill = MockSkill()
        
        registry.register(skill)
        
        # 未加载时只有 loader tools
        tools_empty = registry.get_tools_for_skills([])
        assert len(tools_empty) == 1  # 只有 loader
        
        # 加载后包含所有工具
        tools_loaded = registry.get_tools_for_skills(["mock_skill"])
        assert len(tools_loaded) == 2  # loader + tool

    def test_registry_contains(self):
        """测试 __contains__ 方法"""
        registry = SkillRegistry()
        skill = MockSkill()
        
        registry.register(skill)
        
        assert "mock_skill" in registry
        assert "non_existent" not in registry

    def test_registry_len(self):
        """测试 __len__ 方法"""
        registry = SkillRegistry()
        assert len(registry) == 0
        
        skill = MockSkill()
        registry.register(skill)
        assert len(registry) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])