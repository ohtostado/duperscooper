"""Tests for rules engine."""

import tempfile
from pathlib import Path

import pytest

from duperscooper.rules import Rule, RuleCondition, RuleEngine


class TestRuleCondition:
    """Test RuleCondition evaluation."""

    def test_equality_operator(self) -> None:
        """Test == operator."""
        cond = RuleCondition(field="format", operator="==", value="MP3")
        assert cond.evaluate({"format": "MP3"}) is True
        assert cond.evaluate({"format": "FLAC"}) is False

    def test_inequality_operator(self) -> None:
        """Test != operator."""
        cond = RuleCondition(field="format", operator="!=", value="MP3")
        assert cond.evaluate({"format": "FLAC"}) is True
        assert cond.evaluate({"format": "MP3"}) is False

    def test_less_than_operator(self) -> None:
        """Test < operator."""
        cond = RuleCondition(field="quality_score", operator="<", value=1000)
        assert cond.evaluate({"quality_score": 500}) is True
        assert cond.evaluate({"quality_score": 1500}) is False

    def test_greater_than_operator(self) -> None:
        """Test > operator."""
        cond = RuleCondition(field="quality_score", operator=">", value=1000)
        assert cond.evaluate({"quality_score": 1500}) is True
        assert cond.evaluate({"quality_score": 500}) is False

    def test_contains_operator(self) -> None:
        """Test contains operator."""
        cond = RuleCondition(field="path", operator="contains", value="/backup/")
        assert cond.evaluate({"path": "/music/backup/file.mp3"}) is True
        assert cond.evaluate({"path": "/music/main/file.mp3"}) is False

    def test_in_operator(self) -> None:
        """Test in operator."""
        cond = RuleCondition(field="format", operator="in", value=["MP3", "AAC", "OGG"])
        assert cond.evaluate({"format": "MP3"}) is True
        assert cond.evaluate({"format": "FLAC"}) is False

    def test_missing_field(self) -> None:
        """Test evaluation with missing field returns False."""
        cond = RuleCondition(field="nonexistent", operator="==", value="test")
        assert cond.evaluate({"format": "MP3"}) is False


class TestRule:
    """Test Rule evaluation with multiple conditions."""

    def test_single_condition_match(self) -> None:
        """Test rule with single matching condition."""
        rule = Rule(
            name="Test",
            action="delete",
            conditions=[RuleCondition(field="is_best", operator="==", value=False)],
        )
        assert rule.evaluate({"is_best": False}) is True
        assert rule.evaluate({"is_best": True}) is False

    def test_and_logic_all_match(self) -> None:
        """Test AND logic with all conditions matching."""
        rule = Rule(
            name="Delete low quality MP3s",
            action="delete",
            logic="AND",
            conditions=[
                RuleCondition(field="format", operator="==", value="MP3"),
                RuleCondition(field="quality_score", operator="<", value=192),
            ],
        )
        assert rule.evaluate({"format": "MP3", "quality_score": 128}) is True
        assert rule.evaluate({"format": "MP3", "quality_score": 320}) is False
        assert rule.evaluate({"format": "FLAC", "quality_score": 128}) is False

    def test_and_logic_partial_match(self) -> None:
        """Test AND logic with only some conditions matching."""
        rule = Rule(
            name="Test",
            action="delete",
            logic="AND",
            conditions=[
                RuleCondition(field="format", operator="==", value="MP3"),
                RuleCondition(field="quality_score", operator="<", value=192),
            ],
        )
        # Only one condition matches - should return False
        assert rule.evaluate({"format": "MP3", "quality_score": 320}) is False

    def test_or_logic(self) -> None:
        """Test OR logic with multiple conditions."""
        rule = Rule(
            name="Delete MP3 or AAC",
            action="delete",
            logic="OR",
            conditions=[
                RuleCondition(field="format", operator="==", value="MP3"),
                RuleCondition(field="format", operator="==", value="AAC"),
            ],
        )
        assert rule.evaluate({"format": "MP3"}) is True
        assert rule.evaluate({"format": "AAC"}) is True
        assert rule.evaluate({"format": "FLAC"}) is False

    def test_empty_conditions(self) -> None:
        """Test rule with no conditions returns False."""
        rule = Rule(name="Empty", action="delete", conditions=[])
        assert rule.evaluate({"format": "MP3"}) is False


class TestRuleEngine:
    """Test RuleEngine evaluation and priority handling."""

    def test_single_rule_match(self) -> None:
        """Test engine with single matching rule."""
        engine = RuleEngine()
        engine.add_rule(
            Rule(
                name="Delete non-best",
                action="delete",
                conditions=[RuleCondition(field="is_best", operator="==", value=False)],
            )
        )

        assert engine.evaluate({"is_best": False}) == "delete"
        assert engine.evaluate({"is_best": True}) == "keep"  # default action

    def test_priority_ordering(self) -> None:
        """Test that higher priority rules are evaluated first."""
        engine = RuleEngine(default_action="delete")

        # Add low priority rule
        engine.add_rule(
            Rule(
                name="Delete all",
                action="delete",
                priority=10,
                conditions=[
                    RuleCondition(field="format", operator="!=", value="NONEXISTENT")
                ],
            )
        )

        # Add high priority rule
        engine.add_rule(
            Rule(
                name="Keep best",
                action="keep",
                priority=100,
                conditions=[RuleCondition(field="is_best", operator="==", value=True)],
            )
        )

        # High priority rule should match first
        assert engine.evaluate({"is_best": True, "format": "MP3"}) == "keep"
        # Low priority rule should match
        assert engine.evaluate({"is_best": False, "format": "MP3"}) == "delete"

    def test_default_action(self) -> None:
        """Test default action when no rules match."""
        engine = RuleEngine(default_action="keep")
        engine.add_rule(
            Rule(
                name="Delete MP3",
                action="delete",
                conditions=[RuleCondition(field="format", operator="==", value="MP3")],
            )
        )

        # Rule doesn't match, use default
        assert engine.evaluate({"format": "FLAC"}) == "keep"

    def test_built_in_strategy_eliminate_duplicates(self) -> None:
        """Test eliminate-duplicates strategy."""
        engine = RuleEngine.get_strategy("eliminate-duplicates")

        assert engine.evaluate({"is_best": True}) == "keep"
        assert engine.evaluate({"is_best": False}) == "delete"

    def test_built_in_strategy_keep_lossless(self) -> None:
        """Test keep-lossless strategy."""
        engine = RuleEngine.get_strategy("keep-lossless")

        assert engine.evaluate({"is_lossless": True}) == "keep"
        assert engine.evaluate({"is_lossless": False}) == "delete"

    def test_built_in_strategy_keep_format(self) -> None:
        """Test keep-format strategy."""
        engine = RuleEngine.get_strategy("keep-format", format_param="FLAC")

        assert engine.evaluate({"format": "FLAC"}) == "keep"
        assert engine.evaluate({"format": "MP3"}) == "delete"

    def test_built_in_strategy_keep_format_requires_param(self) -> None:
        """Test keep-format strategy requires format parameter."""
        with pytest.raises(ValueError, match="--format required"):
            RuleEngine.get_strategy("keep-format")

    def test_load_from_yaml_config(self) -> None:
        """Test loading rules from YAML config file."""
        yaml_content = """
rules:
  - name: "Keep best quality"
    action: keep
    priority: 100
    conditions:
      - field: is_best
        operator: "=="
        value: true

  - name: "Delete low quality MP3s"
    action: delete
    priority: 50
    logic: AND
    conditions:
      - field: format
        operator: "=="
        value: "MP3"
      - field: quality_score
        operator: "<"
        value: 192

default_action: keep
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_path = Path(f.name)

        try:
            engine = RuleEngine.load_from_config(config_path)

            # Test high priority rule
            assert engine.evaluate({"is_best": True}) == "keep"

            # Test lower priority rule
            assert engine.evaluate({"format": "MP3", "quality_score": 128}) == "delete"

            # Test default action
            assert engine.evaluate({"format": "FLAC", "quality_score": 320}) == "keep"

        finally:
            config_path.unlink()

    def test_load_from_json_config(self) -> None:
        """Test loading rules from JSON config file."""
        import json

        config = {
            "rules": [
                {
                    "name": "Delete MP3",
                    "action": "delete",
                    "priority": 50,
                    "conditions": [
                        {"field": "format", "operator": "==", "value": "MP3"}
                    ],
                }
            ],
            "default_action": "keep",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            config_path = Path(f.name)

        try:
            engine = RuleEngine.load_from_config(config_path)
            assert engine.evaluate({"format": "MP3"}) == "delete"
            assert engine.evaluate({"format": "FLAC"}) == "keep"

        finally:
            config_path.unlink()
