import logging

from config import CATEGORY_PRIORITY

logger = logging.getLogger(__name__)


def ordered_categories_for_render(all_cats):
    """Return categories sorted by config.yaml category_priority order.

    Iterates CATEGORY_PRIORITY, keeping entries present in all_cats.
    Appends any remaining categories in their original order.
    """
    all_cats_set = set(all_cats)
    ordered = [c for c in CATEGORY_PRIORITY if c in all_cats_set]
    for c in all_cats:
        if c not in ordered:
            ordered.append(c)
    return ordered
