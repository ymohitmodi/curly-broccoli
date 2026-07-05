"""Skill registry. Importing this package registers all built-in skills.

To add your own skill:
  1. create darkfactory/skills/my_skill.py with a @register class
  2. add a cadence entry in config/harness.yaml under schedule:
  3. (optional) write playbooks/my_skill.md — it is injected into every prompt
"""

from .base import SKILLS, SkillContext, register  # noqa: F401
from . import (  # noqa: F401  (import for side-effect: registration)
    product_research,
    supplier_sourcing,
    keyword_seo,
    listing_writer,
    launch_strategist,
    ad_optimizer,
    review_miner,
    inventory_planner,
    evolution_skill,
    digest,
)
