# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
"""The model catalogue — what this estate offers, under its own name.

Three cards, one per surface a client exposes:

    symon-sonnet  Symon Chat     quick questions and drafting
    symon-opus    Symon Coder    writing and running code
    symon-fable   Symon Work     longer tasks, research, documents
    symon-haiku   Symon Quick    short background work a client does for itself

They are branches of one dialect, not three engines. Today all three resolve to the
same `chat` unit and the same weights, and each card says so in `to_detail()`. The
split is a product boundary drawn now so that giving one of them its own checkpoint
later is a registry edit, not a re-architecture — `worker_unit` and `worker_model`
are per-card precisely so they can diverge.

`family_tier` is a wire field of the Messages dialect, emitted on every
`GET /v1/models` row under the name in FAMILY_TIER_FIELD. It is not a claim of
equivalence to anyone else's model. Clients that implement the dialect filter the
model list: a row is kept when its id matches one of the dialect's family patterns
OR the row carries the tier field, and an id that carries an upstream vendor's name
is commonly dropped outright. No `symon-*` id matches a family pattern, so without
the tier every row would be silently dropped and a picker would come back empty —
and the upstream checkpoint's own name could never be offered at all. The tier is
also how a client asking for "the default model of tier X" lands on a card, which is
why the three cards take three DIFFERENT tiers and each is the default of its tier:
two cards on one tier would be indistinguishable to a client that selects by tier.

A row as this gateway emits it (see `to_row()`):

    {"type": "model", "id": "symon-sonnet", "display_name": "Symon Chat",
     "created_at": "2026-09-18T00:00:00Z", "description": "...",
     "anthropic_family_tier": "sonnet", "is_family_default": true,
     "max_input_tokens": 16384, "max_output_tokens": 4096}

Everything above the wire — sampling defaults, the served context, which unit answers
— is this module's own data. Sampling defaults apply only where the caller left a
field unset; a caller's explicit value always wins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The tiers the dialect defines. A card outside this set is unusable by a conforming
# client, so the registry refuses it rather than shipping a row that gets dropped
# somewhere the operator cannot see.
FAMILY_TIERS: frozenset[str] = frozenset({"sonnet", "opus", "haiku", "fable", "mythos"})

# The dialect's field name for the tier, as clients read it on a /v1/models row. A
# protocol identifier: declared here once, used as an opaque constant everywhere else.
FAMILY_TIER_FIELD = "anthropic_family_tier"

# The surfaces a client exposes. Kept as data so a future first-party interface
# reads the same registry instead of re-deriving the mapping.
SURFACES: frozenset[str] = frozenset({"chat", "code", "cowork", "background"})


@dataclass(frozen=True, slots=True)
class Sampling:
    """Per-card request defaults.

    Applied only where the caller said nothing. A client that sets temperature has
    made a decision, and a profile that overrides it would be the gateway quietly
    disagreeing with the caller.
    """

    temperature: float | None = None
    top_p: float | None = None
    max_tokens_cap: int | None = None       # ceiling, never a floor

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.temperature is not None:
            payload.setdefault("temperature", self.temperature)
        if self.top_p is not None:
            payload.setdefault("top_p", self.top_p)
        if self.max_tokens_cap is not None:
            asked = payload.get("max_tokens")
            if isinstance(asked, int) and asked > self.max_tokens_cap:
                payload["max_tokens"] = self.max_tokens_cap
        return payload


@dataclass(frozen=True, slots=True)
class ModelCard:
    """One servable model.

    `worker_model` is the name the engine answers to, which may differ from the
    public `id`. Keeping the two separate is what lets the public name stay stable
    while the engine behind it is replaced.
    """

    id: str
    display_name: str
    family_tier: str
    surface: str
    description: str
    worker_unit: str                 # a name in units.REGISTRY
    worker_model: str                # what the engine was started with
    context_window: int              # tokens actually served, not the checkpoint maximum
    max_output_tokens: int
    created_at: str                  # ISO 8601, the date the card entered this registry
    upstream: str                    # provenance, never shown to a client
    licence: str
    is_family_default: bool = False
    sampling: Sampling = field(default_factory=Sampling)

    def validate(self) -> None:
        if self.family_tier not in FAMILY_TIERS:
            raise ValueError(
                f"{self.id}: family_tier {self.family_tier!r} is not one of "
                f"{sorted(FAMILY_TIERS)}; a conforming client drops the row"
            )
        if self.surface not in SURFACES:
            raise ValueError(f"{self.id}: surface {self.surface!r} is not one of {sorted(SURFACES)}")
        if not self.id or self.id != self.id.strip():
            raise ValueError(f"bad model id {self.id!r}")

    def to_row(self) -> dict[str, Any]:
        """The `GET /v1/models` row.

        `type`, `id`, `display_name` and `created_at` are the documented dialect
        shape. The tier field (FAMILY_TIER_FIELD), `is_family_default`, `description` and
        `max_input_tokens` are the fields the client additionally reads; the module
        docstring says why the tier is load-bearing.
        """
        return {
            "type": "model",
            "id": self.id,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "description": self.description,
            FAMILY_TIER_FIELD: self.family_tier,
            "is_family_default": self.is_family_default,
            "max_input_tokens": self.context_window,
            "max_output_tokens": self.max_output_tokens,
        }

    def to_detail(self) -> dict[str, Any]:
        """`GET /v1/models/{id}`: the row plus first-party provenance.

        Provenance is namespaced so a client parsing the dialect ignores it, and an
        operator reading the same endpoint can still see what the model actually is
        without a second tool. This is also where the shared-weights fact lives, so
        nobody has to infer it from three similar-looking rows.
        """
        row = self.to_row()
        row["x-symoneural"] = {
            "surface": self.surface,
            "unit": self.worker_unit,
            "worker_model": self.worker_model,
            "upstream": self.upstream,
            "licence": self.licence,
            "shares_weights_with": sorted(
                c.id for c in REGISTRY.values()
                if c.id != self.id
                and (c.worker_unit, c.worker_model) == (self.worker_unit, self.worker_model)
            ),
        }
        return row


# The context window is what the worker is STARTED with, not what the checkpoint
# could support. The checkpoint declares max_position_embeddings 131072; this host has
# one 15.92 GiB card holding 12.82 GiB of weights, so the served window is capped and
# the launcher and these numbers must agree. serve-chat-unit.sh takes it from
# SYM_MAX_MODEL_LEN, and /version re-reads the live value from the engine so a drift
# is reported rather than assumed away.
_CONTEXT = 16384
_UPSTREAM = "20B MXFP4 mixture-of-experts, 24 layers, 32 experts, 4 active; provenance in the estate model register"
_CREATED = "2026-09-18T00:00:00Z"

SYMON_CHAT = ModelCard(
    id="symon-sonnet",
    display_name="Symon Chat",
    family_tier="sonnet",
    surface="chat",
    description="Quick questions and drafting, served from this host.",
    worker_unit="chat",
    worker_model="symon-ai",
    context_window=_CONTEXT,
    max_output_tokens=4096,
    created_at=_CREATED,
    upstream=_UPSTREAM,
    licence="Apache-2.0",
    is_family_default=True,
    sampling=Sampling(temperature=0.7, max_tokens_cap=4096),
)

SYMON_CODER = ModelCard(
    id="symon-opus",
    display_name="Symon Coder",
    family_tier="opus",
    surface="code",
    description="Writing and running code against this estate.",
    worker_unit="chat",
    worker_model="symon-ai",
    context_window=_CONTEXT,
    max_output_tokens=8192,
    created_at=_CREATED,
    upstream=_UPSTREAM,
    licence="Apache-2.0",
    is_family_default=True,
    # Lower temperature for code: a wrong token in a diff is a compile error, not a
    # stylistic variation.
    sampling=Sampling(temperature=0.2, max_tokens_cap=8192),
)

SYMON_WORK = ModelCard(
    id="symon-fable",
    display_name="Symon Work",
    family_tier="fable",
    surface="cowork",
    description="Longer tasks: research, analysis and documents.",
    worker_unit="chat",
    worker_model="symon-ai",
    context_window=_CONTEXT,
    max_output_tokens=8192,
    created_at=_CREATED,
    upstream=_UPSTREAM,
    licence="Apache-2.0",
    is_family_default=True,
    sampling=Sampling(temperature=0.6, max_tokens_cap=8192),
)

SYMON_QUICK = ModelCard(
    id="symon-haiku",
    display_name="Symon Quick",
    family_tier="haiku",
    surface="background",
    description="Short background work: titles, summaries and classification.",
    worker_unit="chat",
    worker_model="symon-ai",
    context_window=_CONTEXT,
    max_output_tokens=2048,
    created_at=_CREATED,
    upstream=_UPSTREAM,
    licence="Apache-2.0",
    is_family_default=True,
    # Background work wants the obvious answer, not an interesting one.
    sampling=Sampling(temperature=0.3, max_tokens_cap=2048),
)

# WHY A FOURTH CARD ON A SURFACE NOBODY OPENS
# -------------------------------------------
# A client does not only use the model a person picks. It resolves a tier name to a
# model id for its own background work — titling a conversation, summarising, deciding
# what to do next — and it does that through one environment variable per tier, set
# from whichever discovered row claims that tier. MEASURED against a reference client
# on 2026-09-18: with no row claiming `haiku`, that variable is set to the empty string
# for every session, and the background work either falls back or fails quietly.
#
# So `background` is a surface in the sense that matters here — a job the deployment
# serves — even though no tab opens onto it. The card points at the same unit as the
# others; what it adds is that a client asking for the quick tier gets an answer from
# us rather than nothing.

REGISTRY: dict[str, ModelCard] = {}

# WHY THE IDS CARRY A TIER WORD
# -----------------------------
# A model id is a wire identifier, and clients of this dialect filter the /v1/models
# rows they will offer. MEASURED against a reference client on 2026-09-18: a row
# survives only when its id matches `^(sonnet|opus|haiku|fable|mythos)(-[\d.]+)?$`
# or contains one of `claude`, `anthropic`, or a tier word; ids containing a
# competitor token are rejected outright. `symon-chat` satisfies none of those, so
# every row was discovered and then dropped, and the picker stayed empty while the
# request path worked perfectly.
#
# So the id carries the tier word the protocol requires and `display_name` carries
# ours: the picker shows "Symon Chat", the wire says "symon-sonnet". The tier word is
# a protocol identifier, not a claim about whose model this is; the same applies to
# the tier field these cards already emit.
#
# The former ids stay valid as aliases so anything written against them keeps working.
ALIASES: dict[str, str] = {
    "symon-chat": "symon-sonnet",
    "symon-coder": "symon-opus",
    "symon-work": "symon-fable",
}


def register(card: ModelCard) -> ModelCard:
    card.validate()
    if card.id in REGISTRY:
        raise ValueError(f"duplicate model id {card.id!r}")
    if card.is_family_default and any(
        c.is_family_default and c.family_tier == card.family_tier for c in REGISTRY.values()
    ):
        raise ValueError(f"{card.id}: tier {card.family_tier} already has a default")
    if any(c.surface == card.surface for c in REGISTRY.values()):
        raise ValueError(f"{card.id}: surface {card.surface} already has a card")
    REGISTRY[card.id] = card
    return card


def model(model_id: str) -> ModelCard:
    resolved = ALIASES.get(model_id, model_id)
    try:
        return REGISTRY[resolved]
    except KeyError:
        known = sorted(set(REGISTRY) | set(ALIASES))
        raise KeyError(f"unknown model {model_id!r}; known: {known}") from None


def cards() -> list[ModelCard]:
    return list(REGISTRY.values())


def for_surface(surface: str) -> ModelCard | None:
    return next((c for c in REGISTRY.values() if c.surface == surface), None)


def worker_models() -> set[str]:
    """Every distinct engine-side name the registry depends on.

    /ready compares this with what the engine reports, so a card pointing at a model
    the engine is not serving is caught by a probe rather than by a caller.
    """
    return {c.worker_model for c in REGISTRY.values()}


for _card in (SYMON_CHAT, SYMON_CODER, SYMON_WORK, SYMON_QUICK):
    register(_card)
