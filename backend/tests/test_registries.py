"""Scaffold sanity checks — cheap, no API calls, no model weights."""

from __future__ import annotations

import pytest

from app.config import prompts as P
from app.config.anatomy import CATEGORY_MOUNT, RULERS, ruler_for_category
from app.core.assets import ASSET_TYPES, ASSET_TYPES_BY_KEY, Pipeline
from app.core.formats import FORMATS, FORMATS_BY_KEY, MASTER_LONG_EDGE


def test_seven_image_asset_types_in_v1():
    assert len(ASSET_TYPES) == 7
    assert all(a.kind == "image" for a in ASSET_TYPES)


def test_every_asset_type_has_a_prompt():
    for asset in ASSET_TYPES:
        assert asset.prompt_key in P.PROMPTS, asset.key


def test_every_asset_format_key_is_real():
    for asset in ASSET_TYPES:
        for key in asset.formats:
            assert key in FORMATS_BY_KEY, f"{asset.key} -> {key}"


def test_format_matrix_matches_spec():
    assert len(FORMATS) == 7
    assert FORMATS_BY_KEY["shopify_product"].width == 2048
    # We generate at the largest edge so every export downscales.
    assert MASTER_LONG_EDGE == 2048


def test_every_category_maps_to_a_ruler():
    for category, mount in CATEGORY_MOUNT.items():
        assert mount in RULERS
        assert ruler_for_category(category).mm > 0


@pytest.mark.parametrize("key", sorted(P.PROMPTS))
def test_prompt_renders_with_all_placeholders(key):
    rendered = P.PROMPTS[key].render(
        name="Cascade Drop Earrings",
        desc="Waterproof gold-tone with a freshwater pearl.",
        dimensions="36 mm drop x 12 mm wide",
        category="earrings",
        view="three-quarter profile",
        mount_area="earlobe",
        concept=P.DEFAULT_CONCEPT,
    )
    assert "{" not in rendered, "unfilled placeholder"
    assert P.BRAND_SUFFIX in rendered


def test_product_preserving_prompts_carry_the_preamble():
    for key, tpl in P.PROMPTS.items():
        rendered = tpl.render(
            name="X", desc="Y", dimensions="10 mm", category="ring",
            view="v", mount_area="m", concept="c",
        )
        if tpl.preserves_product:
            assert rendered.startswith(P.PRESERVE_PREAMBLE), key
        else:
            # Scene-only prompts must NOT ask the model to preserve a product —
            # they are explicitly generating an empty body part (§4 step B).
            assert P.PRESERVE_PREAMBLE not in rendered, key


def test_composite_pipeline_covers_the_human_worn_shots():
    composite = {a.key for a in ASSET_TYPES if a.pipeline is Pipeline.COMPOSITE}
    assert composite == {"on_model", "skin_closeup"}
    assert ASSET_TYPES_BY_KEY["white_hero"].pipeline is Pipeline.DIRECT
