"""Skills system: reusable prompt workflows loaded from YAML files.

Skills are pre-defined prompt templates that guide the LLM through specific
workflows using the available tools. They can be triggered by:
  - Slash commands: /review, /debug, /deploy
  - Keyword matching: "review this code", "debug the error"

Each skill defines:
  - A specialized system prompt that guides the LLM
  - Which model tier to use (fast/default/code)
  - Which tools are required
  - Trigger patterns (slash commands and/or keywords)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """Represents a single skill definition."""

    name: str
    description: str
    prompt: str  # The workflow prompt injected into system message
    model: str = "default"  # "fast" | "default" | "code"
    slash_command: str = ""  # e.g. "/review"
    triggers: list[str] = field(default_factory=list)  # keyword triggers
    tools_required: list[str] = field(default_factory=list)
    # Compiled trigger patterns (built at load time)
    _trigger_pattern: re.Pattern | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.triggers:
            # Build a regex that matches any trigger phrase
            escaped = [re.escape(t) for t in self.triggers]
            pattern = r"\b(" + "|".join(escaped) + r")\b"
            self._trigger_pattern = re.compile(pattern, re.IGNORECASE)

    def matches(self, user_input: str) -> bool:
        """Check if user input triggers this skill."""
        text = user_input.strip()

        # Check slash command first (exact match at start)
        if self.slash_command:
            cmd = self.slash_command if self.slash_command.startswith("/") else f"/{self.slash_command}"
            if text.lower().startswith(cmd.lower()):
                return True

        # Check keyword triggers
        return bool(self._trigger_pattern and self._trigger_pattern.search(text))

    def get_user_input_without_command(self, user_input: str) -> str:
        """Strip the slash command from user input, return the rest."""
        text = user_input.strip()
        if self.slash_command:
            cmd = self.slash_command if self.slash_command.startswith("/") else f"/{self.slash_command}"
            if text.lower().startswith(cmd.lower()):
                return text[len(cmd):].strip()
        return text


@dataclass
class SkillMatch:
    """Result of matching user input against skills."""

    skill: Skill
    user_input: str  # The cleaned user input (slash command stripped)

    @property
    def augmented_prompt(self) -> str:
        """Return the skill's prompt to be injected into the system message."""
        return self.skill.prompt


class SkillManager:
    """Loads and manages skill definitions."""

    def __init__(self, skills_dir: str | Path | None = None):
        self._skills: dict[str, Skill] = {}
        self._skills_dir = Path(skills_dir) if skills_dir else None

    @property
    def skills(self) -> dict[str, Skill]:
        return self._skills

    @property
    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def load_skills(self, skills_dir: str | Path | None = None) -> int:
        """Load all skill YAML files from the skills directory.

        Returns the number of skills loaded.
        """
        search_dir = Path(skills_dir) if skills_dir else self._skills_dir
        if not search_dir:
            # Default: look for 'skills' directory next to project root
            search_dir = Path(__file__).parent.parent.parent / "skills"

        if not search_dir.exists():
            logger.info(f"Skills directory not found: {search_dir}")
            return 0

        count = 0
        for yaml_file in sorted(search_dir.glob("*.yaml")):
            try:
                skill = self._load_skill_file(yaml_file)
                if skill:
                    self._skills[skill.name] = skill
                    count += 1
                    logger.info(f"Loaded skill: {skill.name} ({skill.slash_command or 'no command'})")
            except Exception as e:
                logger.error(f"Failed to load skill {yaml_file.name}: {e}")

        # Also load .yml files
        for yml_file in sorted(search_dir.glob("*.yml")):
            try:
                skill = self._load_skill_file(yml_file)
                if skill:
                    self._skills[skill.name] = skill
                    count += 1
                    logger.info(f"Loaded skill: {skill.name} ({skill.slash_command or 'no command'})")
            except Exception as e:
                logger.error(f"Failed to load skill {yml_file.name}: {e}")

        logger.info(f"Loaded {count} skills from {search_dir}")
        return count

    def _load_skill_file(self, path: Path) -> Skill | None:
        """Parse a single YAML skill file into a Skill object."""
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            return None

        name = data.get("name", path.stem)
        description = data.get("description", "")
        prompt = data.get("prompt", "")
        if not prompt:
            logger.warning(f"Skill {name} has no prompt, skipping")
            return None

        return Skill(
            name=name,
            description=description,
            prompt=prompt,
            model=data.get("model", "default"),
            slash_command=data.get("slash_command", f"/{name}"),
            triggers=data.get("triggers", []),
            tools_required=data.get("tools_required", []),
        )

    def register_skill(self, skill: Skill) -> None:
        """Register a skill programmatically (not from YAML)."""
        self._skills[skill.name] = skill

    def match(self, user_input: str) -> SkillMatch | None:
        """Try to match user input against registered skills.

        Returns a SkillMatch if a skill matches, None otherwise.
        Slash commands take priority over keyword triggers.
        """
        text = user_input.strip()

        # Priority 1: exact slash command match
        for skill in self._skills.values():
            if skill.slash_command:
                cmd = skill.slash_command if skill.slash_command.startswith("/") else f"/{skill.slash_command}"
                if text.lower().startswith(cmd.lower()):
                    clean_input = skill.get_user_input_without_command(text)
                    return SkillMatch(
                        skill=skill,
                        user_input=clean_input or text,
                    )

        # Priority 2: keyword trigger match
        for skill in self._skills.values():
            if skill._trigger_pattern and skill._trigger_pattern.search(text):
                return SkillMatch(
                    skill=skill,
                    user_input=text,
                )

        return None

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def get_help_text(self) -> str:
        """Generate help text listing all available skills."""
        if not self._skills:
            return "No skills available."

        lines = ["AVAILABLE SKILLS:", ""]
        for skill in self._skills.values():
            cmd = skill.slash_command or f"/{skill.name}"
            lines.append(f"  {cmd:20s} {skill.description}")
            if skill.triggers:
                triggers_str = ", ".join(f'"{t}"' for t in skill.triggers[:3])
                lines.append(f"  {'':20s} Triggers: {triggers_str}")
        return "\n".join(lines)
