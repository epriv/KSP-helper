"""Pydantic request/response schemas for the web layer.

Same models validate Form data and JSON requests. Response models adapt
the pure calculator dataclasses (`TripPlan`, `Edge`, `Stop`) for serialisation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ksp_planner.dv_map import TripPlan


class StopInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(..., min_length=1)
    action: Literal["land", "orbit", "flyby"] = "orbit"


class DvRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(..., alias="from", min_length=1)
    to: str = Field(..., min_length=1)
    via: list[StopInput] = Field(default_factory=list)
    round_trip: bool = False
    aerobrake: bool = True
    margin_pct: float = Field(5.0, ge=0, le=100)


class LegOut(BaseModel):
    from_slug: str
    to_slug: str
    dv_m_s: float
    can_aerobrake: bool


class StopOut(BaseModel):
    """Intermediate (non-endpoint) stop annotation for the renderer."""

    slug: str
    action: Literal["land", "orbit", "flyby"]
    after_leg_idx: int  # render this annotation after legs[after_leg_idx]


class DvResponse(BaseModel):
    from_slug: str
    to_slug: str
    round_trip: bool
    aerobrake: bool
    margin_pct: float
    legs: list[LegOut]
    stops: list[StopOut]
    total_raw: float
    total_aerobraked: float
    total_planned: float
    total_aerobraked_planned: float
    equivalent_cli: str

    @classmethod
    def from_trip(cls, trip: TripPlan, req: DvRequest, equiv_cli: str) -> DvResponse:
        # Flatten legs: trip.legs is list[list[Edge]]; we render per-edge.
        # Insert StopOut annotations between legs[i] and legs[i+1] for intermediate stops.
        flat_legs: list[LegOut] = []
        stop_annotations: list[StopOut] = []
        for i, leg in enumerate(trip.legs):
            for edge in leg:
                flat_legs.append(
                    LegOut(
                        from_slug=edge.from_slug,
                        to_slug=edge.to_slug,
                        dv_m_s=edge.dv_m_s,
                        can_aerobrake=edge.can_aerobrake,
                    )
                )
            # After this leg's edges, if this isn't the last leg, the next stop
            # is intermediate (i.e. trip.stops[i+1]).
            if i < len(trip.legs) - 1:
                next_stop = trip.stops[i + 1]
                stop_annotations.append(
                    StopOut(
                        slug=next_stop.slug,
                        action=next_stop.action,
                        after_leg_idx=len(flat_legs) - 1,
                    )
                )
        return cls(
            from_slug=req.from_,
            to_slug=req.to,
            round_trip=req.round_trip,
            aerobrake=trip.aerobrake,
            margin_pct=trip.margin_pct,
            legs=flat_legs,
            stops=stop_annotations,
            total_raw=trip.total_raw,
            total_aerobraked=trip.total_aerobraked,
            total_planned=trip.total_planned,
            total_aerobraked_planned=trip.total_aerobraked_planned,
            equivalent_cli=equiv_cli,
        )


def equivalent_cli(req: DvRequest) -> str:
    """Build the CLI invocation that reproduces this request."""
    parts = ["uv run ksp dv", req.from_, req.to]
    for stop in req.via:
        parts.append(f"--via {stop.body}:{stop.action}")
    if req.round_trip:
        parts.append("--return")
    if not req.aerobrake:
        parts.append("--no-aerobrake")
    if req.margin_pct != 5.0:
        # Match Typer formatting: integer-like values print without trailing zeros.
        margin_str = f"{req.margin_pct:g}"
        parts.append(f"--margin {margin_str}")
    return " ".join(parts)
