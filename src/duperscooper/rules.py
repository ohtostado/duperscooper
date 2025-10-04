"""Rule engine for applying deletion rules to scan results."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import yaml


@dataclass
class RuleCondition:
    """
    Represents a single rule condition that can be evaluated against file/album data.

    Supported operators:
    - Equality: ==, !=
    - Comparison: <, >, <=, >=
    - Membership: in, not in
    - String: contains, matches (regex)
    """

    field: str
    operator: Literal["==", "!=", "<", ">", "<=", ">=", "in", "not in", "contains", "matches"]  # fmt: skip
    value: Union[str, int, float, bool, List[Any]]

    def evaluate(self, item: Dict[str, Any]) -> bool:
        """
        Evaluate this condition against an item.

        Args:
            item: Dictionary containing file/album data with extracted fields

        Returns:
            True if condition matches, False otherwise
        """
        # Get field value from item
        if self.field not in item:
            return False

        field_value = item[self.field]

        # Evaluate based on operator
        if self.operator == "==":
            return field_value == self.value
        elif self.operator == "!=":
            return field_value != self.value
        elif self.operator == "<":
            return field_value < self.value  # type: ignore
        elif self.operator == ">":
            return field_value > self.value  # type: ignore
        elif self.operator == "<=":
            return field_value <= self.value  # type: ignore
        elif self.operator == ">=":
            return field_value >= self.value  # type: ignore
        elif self.operator == "in":
            return field_value in self.value  # type: ignore
        elif self.operator == "not in":
            return field_value not in self.value  # type: ignore
        elif self.operator == "contains":
            return str(self.value) in str(field_value)
        elif self.operator == "matches":
            return bool(re.search(str(self.value), str(field_value)))
        else:
            return False


@dataclass
class Rule:
    """
    Represents a rule with multiple conditions combined with boolean logic.

    A rule determines whether to "keep" or "delete" an item based on conditions.
    Higher priority rules are evaluated first.
    """

    name: str
    action: Literal["keep", "delete"]
    conditions: List[RuleCondition] = field(default_factory=list)
    logic: Literal["AND", "OR"] = "AND"
    priority: int = 50

    def evaluate(self, item: Dict[str, Any]) -> bool:
        """
        Evaluate all conditions against an item.

        Args:
            item: Dictionary containing file/album data with extracted fields

        Returns:
            True if this rule matches (all conditions pass), False otherwise
        """
        if not self.conditions:
            return False

        if self.logic == "AND":
            return all(condition.evaluate(item) for condition in self.conditions)
        else:  # OR
            return any(condition.evaluate(item) for condition in self.conditions)


class RuleEngine:
    """
    Evaluates rules against file/album data to determine keep/delete actions.

    Rules are evaluated in priority order (highest first). The first matching
    rule determines the action. If no rules match, the default action is used.
    """

    def __init__(self, default_action: Literal["keep", "delete"] = "keep"):
        """
        Initialize rule engine.

        Args:
            default_action: Action to take if no rules match (default: keep)
        """
        self.rules: List[Rule] = []
        self.default_action = default_action

    def add_rule(self, rule: Rule) -> None:
        """
        Add a rule to the engine.

        Args:
            rule: Rule to add
        """
        self.rules.append(rule)
        # Keep rules sorted by priority (highest first)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def evaluate(self, item: Dict[str, Any]) -> Literal["keep", "delete"]:
        """
        Evaluate all rules against an item.

        Args:
            item: Dictionary containing file/album data with extracted fields

        Returns:
            Action to take: "keep" or "delete"
        """
        for rule in self.rules:
            if rule.evaluate(item):
                return rule.action

        return self.default_action

    @staticmethod
    def get_strategy(
        strategy: str, format_param: Optional[str] = None
    ) -> "RuleEngine":
        """
        Get a rule engine with built-in strategy pre-loaded.

        Args:
            strategy: Strategy name (eliminate-duplicates, keep-lossless, keep-format, custom)
            format_param: Format to keep (required for keep-format strategy)

        Returns:
            RuleEngine configured with the specified strategy
        """
        engine = RuleEngine(default_action="keep")

        if strategy == "eliminate-duplicates":
            # Keep best quality only
            engine.add_rule(
                Rule(
                    name="Keep best quality",
                    action="keep",
                    priority=100,
                    conditions=[
                        RuleCondition(field="is_best", operator="==", value=True)
                    ],
                )
            )
            engine.add_rule(
                Rule(
                    name="Delete non-best",
                    action="delete",
                    priority=10,
                    conditions=[
                        RuleCondition(field="is_best", operator="==", value=False)
                    ],
                )
            )

        elif strategy == "keep-lossless":
            # Keep lossless, delete lossy
            engine.add_rule(
                Rule(
                    name="Keep lossless files",
                    action="keep",
                    priority=100,
                    conditions=[
                        RuleCondition(field="is_lossless", operator="==", value=True)
                    ],
                )
            )
            engine.add_rule(
                Rule(
                    name="Delete lossy files",
                    action="delete",
                    priority=10,
                    conditions=[
                        RuleCondition(field="is_lossless", operator="==", value=False)
                    ],
                )
            )

        elif strategy == "keep-format":
            # Keep specific format, delete others
            if not format_param:
                raise ValueError("--format required for keep-format strategy")

            engine.add_rule(
                Rule(
                    name=f"Keep {format_param} files",
                    action="keep",
                    priority=100,
                    conditions=[
                        RuleCondition(
                            field="format", operator="==", value=format_param.upper()
                        )
                    ],
                )
            )
            engine.add_rule(
                Rule(
                    name=f"Delete non-{format_param} files",
                    action="delete",
                    priority=10,
                    conditions=[
                        RuleCondition(
                            field="format", operator="!=", value=format_param.upper()
                        )
                    ],
                )
            )

        elif strategy == "custom":
            # Custom strategy loaded from config file (handled by load_from_config)
            pass

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        return engine

    @staticmethod
    def load_from_config(config_path: Path) -> "RuleEngine":
        """
        Load rules from YAML or JSON config file.

        Args:
            config_path: Path to config file (.yaml, .yml, or .json)

        Returns:
            RuleEngine configured from the file
        """
        with open(config_path, "r") as f:
            if config_path.suffix in [".yaml", ".yml"]:
                config = yaml.safe_load(f)
            elif config_path.suffix == ".json":
                import json

                config = json.load(f)
            else:
                raise ValueError(
                    f"Unsupported config format: {config_path.suffix}. Use .yaml, .yml, or .json"
                )

        # Get default action
        default_action = config.get("default_action", "keep")
        engine = RuleEngine(default_action=default_action)

        # Load rules
        for rule_data in config.get("rules", []):
            # Parse conditions
            conditions = []
            for cond_data in rule_data.get("conditions", []):
                conditions.append(
                    RuleCondition(
                        field=cond_data["field"],
                        operator=cond_data["operator"],
                        value=cond_data["value"],
                    )
                )

            # Create rule
            rule = Rule(
                name=rule_data.get("name", "Unnamed rule"),
                action=rule_data["action"],
                conditions=conditions,
                logic=rule_data.get("logic", "AND"),
                priority=rule_data.get("priority", 50),
            )
            engine.add_rule(rule)

        return engine
