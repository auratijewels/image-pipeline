"""Brand-locked prompt library (§7).

PLACEHOLDER SET. These are written from the brand rules in §7 so the pipeline is
runnable end to end, but they are NOT the final copy — the Aurati_Gemini_Prompt_Kit
spreadsheet replaces the `template` strings verbatim once supplied. Keys and the
`{name} / {desc} / {dimensions} / {category}` placeholders are the contract; keep
them stable when swapping in the real kit.

Templates are also editable at runtime through the UI's prompt library, which
persists overrides to data/prompt_overrides.json.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- brand constants --------------------------------------------------------

NAVY = "#29354F"
MIDNIGHT = "#161C2B"
PLATINUM = "#EAEDF3"
TAGLINE = "Wear Confidence Everyday"

# Every product-preserving prompt must open with this. Non-negotiable (§7).
PRESERVE_PREAMBLE = (
    "Keep the uploaded piece 100% identical to the reference — exact shape, "
    "proportions, stones, links and gold finish. Do not redesign."
)

BRAND_SUFFIX = (
    f"Aurati Jewels brand palette: navy {NAVY}, midnight {MIDNIGHT}, platinum {PLATINUM}. "
    "Editorial fine-jewellery photography, natural colour, no oversaturation, no watermark, "
    "no text unless specified."
)


@dataclass(frozen=True)
class PromptTemplate:
    key: str
    label: str
    template: str
    preserves_product: bool = True
    negative: str = "distorted jewellery, extra stones, warped links, plastic sheen, text, watermark, logo"

    def render(self, **kwargs: object) -> str:
        body = self.template.format(**kwargs)
        head = f"{PRESERVE_PREAMBLE}\n\n" if self.preserves_product else ""
        return f"{head}{body}\n\n{BRAND_SUFFIX}"


# --- the seven v1 templates -------------------------------------------------

PROMPTS: dict[str, PromptTemplate] = {
    "white_hero": PromptTemplate(
        key="white_hero",
        label="Catalog Photo — White Hero",
        template=(
            "Studio product photograph of {name}, a {category} measuring {dimensions}. {desc} "
            "Pure seamless white background, soft large-softbox key with subtle fill, gentle "
            "contact shadow directly beneath the piece. Centred, sharp throughout, e-commerce hero framing "
            "with generous margin. Square composition."
        ),
    ),
    "branded_backdrop": PromptTemplate(
        key="branded_backdrop",
        label="Catalog Photo — Branded Backdrop",
        template=(
            "Product photograph of {name}, a {category} measuring {dimensions}, resting on midnight-navy "
            f"silk ({NAVY}) with soft folds catching a low raking light. {{desc}} "
            "Rich shadow depth, platinum rim highlight along the metal, luxurious and restrained. "
            "Square composition."
        ),
    ),
    "macro_waterproof": PromptTemplate(
        key="macro_waterproof",
        label="Catalog Photo — Macro / Waterproof",
        template=(
            "Extreme macro photograph of {name}, a {category} measuring {dimensions}. {desc} "
            "Tiny beaded water droplets sit on the surface and a shallow ripple of clear water spreads "
            "beneath it — the Aurati waterproof signature cue. Crisp specular highlights in the droplets, "
            "cool daylight, cream marble surface just visible. Square composition."
        ),
    ),
    "on_model": PromptTemplate(
        key="on_model",
        label="Human-Worn Photo — On Model (scene only)",
        # COMPOSITE asset: this generates the human WITHOUT the jewellery.
        # The real cut-out is scaled and composited in afterwards (§4 steps C–E).
        template=(
            "Photorealistic editorial portrait of a South Asian female model, {view}, wearing no jewellery "
            "at all on the {mount_area}. Soft natural daylight from a large window, clean warm-beige backdrop, "
            "relaxed confident expression, natural skin texture with visible pores, no retouching plastic look. "
            "The {mount_area} is fully visible, unobstructed by hair or clothing, and in sharp focus. "
            "Vertical 4:5 composition."
        ),
        preserves_product=False,
        negative="jewellery, earrings, necklace, ring, bracelet, hands covering face, hair over ears, text, watermark",
    ),
    "skin_closeup": PromptTemplate(
        key="skin_closeup",
        label="Human-Worn Photo — Skin Close-up (scene only)",
        # COMPOSITE asset: bare skin only; product is composited in.
        template=(
            "Macro photograph of bare human skin at the {mount_area}, no jewellery present, "
            "South Asian skin tone, soft directional daylight, fine natural skin texture and downy hair visible, "
            "very shallow depth of field falling off behind. Neutral out-of-focus background. "
            "Vertical 4:5 composition."
        ),
        preserves_product=False,
        negative="jewellery, metal, gemstone, text, watermark, plastic skin, heavy retouching",
    ),
    "flatlay": PromptTemplate(
        key="flatlay",
        label="Instagram Post — Creative Flat-lay",
        template=(
            "Overhead styled flat-lay featuring {name}, a {category} measuring {dimensions}, as the clear hero. "
            "{desc} Cream marble surface, a folded navy silk ribbon, dried white flowers and a small glass "
            "of water catching light. Negative space top-left for copy. Soft diffuse daylight, gentle shadows. "
            "Vertical 4:5 composition."
        ),
    ),
    "signature_concept": PromptTemplate(
        key="signature_concept",
        label="Signature Concept — Hero Campaign",
        template=(
            "Signature campaign image for {name}, a {category} measuring {dimensions}. {desc} "
            "Concept: {concept}. Dramatic single-source light, midnight-navy to platinum gradient, "
            "a suspended droplet of water frozen mid-fall near the piece. Cinematic, aspirational, "
            "gallery-print quality. Vertical 4:5 composition."
        ),
    ),
}

# Fallback concept when the user has not written one for a product.
DEFAULT_CONCEPT = (
    "the piece emerging from still dark water, surface tension breaking into a perfect ring of ripples"
)

# Optional overlay applied by the format exporter when the user enables it.
TAGLINE_OVERLAY = {"text": TAGLINE, "font": "Cormorant Garamond", "colour": PLATINUM}


def get_prompt(key: str) -> PromptTemplate:
    return PROMPTS[key]
