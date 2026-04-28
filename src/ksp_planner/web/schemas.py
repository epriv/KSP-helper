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
        """Adapt a pure TripPlan + the originating request into a DvResponse.

        Precondition: `req.from_` and `req.to` must already be the resolved node
        slugs (i.e. equal `trip.stops[0].slug` and `trip.stops[-1].slug`). Route
        handlers that resolve body slugs via `resolve_stop` are responsible for
        keeping these in sync — the adapter does not re-derive them from `trip`.
        """
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
            if i < len(trip.legs) - 1 and flat_legs:
                # Skip annotation if the preceding leg had no edges (degenerate A→A hop):
                # there's nothing to anchor `after_leg_idx` to. Stop annotations are
                # render hints; missing one for a degenerate self-loop is fine.
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


class CommsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(..., min_length=1)
    n_sats: int = Field(3, ge=2)
    antenna: str = Field(..., min_length=1)
    dsn_level: int = Field(2, ge=1, le=3)
    min_elev_deg: float = Field(5.0, ge=0, lt=90)


class CommsResponse(BaseModel):
    body_slug: str
    n_sats: int
    antenna_name: str
    dsn_level: int
    min_elev_deg: float
    orbit_altitude_km: float
    period_s: float
    range_sat_to_sat_km: float
    range_sat_to_dsn_km: float
    sat_separation_km: float
    coverage_ok: bool
    coverage_margin_km: float
    suggestion: str
    resonant_altitude_km: float
    resonant_period_s: float
    resonant_ratio: str
    equivalent_cli: str

    @classmethod
    def from_report(
        cls,
        report: dict,
        resonant: dict,
        body_radius_m: float,
        equiv_cli: str,
    ) -> CommsResponse:
        return cls(
            body_slug=report["body"],
            n_sats=report["n_sats"],
            antenna_name=report["antenna"],
            dsn_level=report["dsn_level"],
            min_elev_deg=report["min_elev_deg"],
            orbit_altitude_km=report["orbit_altitude_m"] / 1000,
            period_s=report["period_s"],
            range_sat_to_sat_km=report["range_sat_to_sat_m"] / 1000,
            range_sat_to_dsn_km=report["range_sat_to_dsn_m"] / 1000,
            sat_separation_km=report["sat_separation_m"] / 1000,
            coverage_ok=report["coverage_ok"],
            coverage_margin_km=report["coverage_margin_m"] / 1000,
            suggestion=report["suggestion"],
            resonant_altitude_km=(resonant["resonant_sma_m"] - body_radius_m) / 1000,
            resonant_period_s=resonant["resonant_period_s"],
            resonant_ratio=resonant["ratio"],
            equivalent_cli=equiv_cli,
        )


class SweetSpotOut(BaseModel):
    altitude_km: float
    period_s: float
    swath_km: float
    shift_km: float
    orbits_per_day: float
    days_to_coverage: float


class ScanningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(..., min_length=1)
    fov_deg: float = Field(5.0, gt=0, le=90)
    min_alt_km: float | None = Field(None, ge=0)
    max_alt_km: float | None = Field(None, ge=0)


class ScanningResponse(BaseModel):
    body_slug: str
    body_name: str
    fov_deg: float
    min_alt_km: float
    max_alt_km: float
    sweet_spots: list[SweetSpotOut]
