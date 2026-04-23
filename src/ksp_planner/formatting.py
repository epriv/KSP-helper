"""Rich formatting helpers — presentation only, no computation."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ksp_planner.dv_map import ACTION_SUFFIXES, AEROBRAKE_RESIDUAL_PCT


def fmt_dist(m: float | None) -> str:
    if m is None:
        return "—"
    abs_m = abs(m)
    if abs_m >= 1e9:
        return f"{m / 1e9:,.3f} Gm"
    if abs_m >= 1e6:
        return f"{m / 1e6:,.3f} Mm"
    if abs_m >= 1_000:
        return f"{m / 1_000:,.3f} km"
    return f"{m:,.1f} m"


def fmt_time(s: float | None) -> str:
    if s is None or s <= 0:
        return "—"
    days_unit = 6 * 3600  # 1 Kerbin day = 6 h
    days = int(s // days_unit)
    rem = s - days * days_unit
    hours = int(rem // 3600)
    mins = int((rem % 3600) // 60)
    secs = int(rem % 60)
    if days:
        return f"{days}d {hours}h {mins:02d}m"
    if hours:
        return f"{hours}h {mins:02d}m {secs:02d}s"
    if mins:
        return f"{mins}m {secs:02d}s"
    return f"{secs}s"


def fmt_mu(mu: float) -> str:
    return f"{mu:.3e} m³/s²"


def fmt_angle(deg: float | None) -> str:
    return "—" if deg is None else f"{deg:.3f}°"


def bodies_table(bodies: list[dict]) -> Table:
    t = Table(title="Celestial bodies", box=box.ROUNDED)
    t.add_column("Slug", style="cyan")
    t.add_column("Name")
    t.add_column("Type")
    t.add_column("Radius", justify="right")
    t.add_column("μ", justify="right")
    t.add_column("SOI", justify="right")
    t.add_column("Atm", justify="right")
    for b in bodies:
        atm = fmt_dist(b["atm_height_m"]) if b["atm_height_m"] else "—"
        soi = fmt_dist(b["soi_m"]) if b["soi_m"] else "∞"
        t.add_row(
            b["slug"], b["name"], b["body_type"],
            fmt_dist(b["radius_m"]), fmt_mu(b["mu_m3s2"]),
            soi, atm,
        )
    return t


def antennas_table(antennas: list[dict]) -> Table:
    t = Table(title="Antennas", box=box.ROUNDED)
    t.add_column("Name", style="cyan")
    t.add_column("Reference range", justify="right")
    t.add_column("Relay", justify="center")
    t.add_column("Combinable", justify="center")
    for a in antennas:
        t.add_row(
            a["name"], fmt_dist(a["range_m"]),
            "✓" if a["is_relay"] else "",
            "✓" if a["combinable"] else "",
        )
    return t


def plans_table(plans: list[dict]) -> Table:
    t = Table(title="Saved plans", box=box.ROUNDED)
    t.add_column("Name", style="cyan")
    t.add_column("Kind")
    t.add_column("Updated")
    for p in plans:
        t.add_row(p["name"], p["kind"], p["updated_at"])
    return t


def plan_detail_panel(plan: dict) -> Panel:
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim")
    meta.add_column()
    meta.add_row("Kind", plan["kind"])
    meta.add_row("Created", plan["created_at"])
    meta.add_row("Updated", plan["updated_at"])

    cfg = Table.grid(padding=(0, 2))
    cfg.add_column(style="dim")
    cfg.add_column()
    for k, v in plan["config"].items():
        cfg.add_row(str(k), str(v))

    return Panel(
        Group(meta, Text(""), Text("Config", style="bold"), cfg),
        title=f"[bold]{plan['name']}[/]",
        box=box.ROUNDED,
    )


def dsn_table(levels: list[dict]) -> Table:
    t = Table(title="Deep Space Network levels", box=box.ROUNDED)
    t.add_column("Level", justify="center")
    t.add_column("Reference range", justify="right")
    for lvl in levels:
        t.add_row(str(lvl["level"]), fmt_dist(lvl["range_m"]))
    return t


def body_detail_panel(body: dict, parent: dict | None) -> Panel:
    KERBIN_G = 9.81

    g = body["mu_m3s2"] / body["radius_m"] ** 2
    sync_alt = (
        body["sync_orbit_m"] - body["radius_m"] if body["sync_orbit_m"] else None
    )

    physical = Table.grid(padding=(0, 2))
    physical.add_column(style="dim")
    physical.add_column()
    physical.add_row("Radius", fmt_dist(body["radius_m"]))
    physical.add_row("μ", fmt_mu(body["mu_m3s2"]))
    physical.add_row("Surface gravity", f"{g:.3f} m/s²  ({g / KERBIN_G:.3f} g)")
    physical.add_row("Sidereal day", fmt_time(body["sidereal_day_s"]))
    physical.add_row("Sync orbit altitude", fmt_dist(sync_alt))
    physical.add_row("SOI", fmt_dist(body["soi_m"]) if body["soi_m"] else "∞")
    physical.add_row("Atmosphere top", fmt_dist(body["atm_height_m"]))
    physical.add_row("Has oxygen", "yes" if body["has_oxygen"] else "no")

    renderables: list[RenderableType] = [Text("Physical", style="bold"), physical]

    if body["sma_m"] is not None:
        orbital = Table.grid(padding=(0, 2))
        orbital.add_column(style="dim")
        orbital.add_column()
        orbital.add_row("Parent", parent["name"] if parent else "—")
        orbital.add_row("Semi-major axis", fmt_dist(body["sma_m"]))
        orbital.add_row("Eccentricity", f"{body['eccentricity']:.4f}")
        orbital.add_row("Inclination", fmt_angle(body["inclination_deg"]))
        orbital.add_row("Arg. of periapsis", fmt_angle(body["arg_periapsis_deg"]))
        orbital.add_row("LAN", fmt_angle(body["lan_deg"]))
        orbital.add_row("Mean anomaly @ epoch", fmt_angle(body["mean_anomaly_epoch_deg"]))
        from ksp_planner.orbital import orbital_period

        period = orbital_period(body["sma_m"], parent["mu_m3s2"]) if parent else None
        orbital.add_row("Orbital period", fmt_time(period))
        renderables += [Text(""), Text("Orbit", style="bold"), orbital]

    return Panel(Group(*renderables), title=f"[bold]{body['name']}[/]", box=box.ROUNDED)


def dv_trip_panel(trip, from_slug: str, to_slug: str) -> Panel:
    """Render a `TripPlan` as a per-leg table + raw, aerobrake, and margin totals.

    When the trip has intermediate stops, a `stop: <action> (<slug>)` row is
    inserted between legs for each intermediate stop.

    The `aero` column is tri-state:
        - "✓ −N%"   : edge is can_aerobrake=True and trip.aerobrake is True
                      (N = 100 − AEROBRAKE_RESIDUAL_PCT, i.e. the discount applied)
        - "✓ off"   : edge is can_aerobrake=True but trip.aerobrake is False
        - ""        : edge cannot be aerobraked

    The totals block renders an extra "With aerobrake" row when trip.aerobrake
    is True, even if the savings are zero (keeps output shape predictable).
    """
    intermediate_stops = trip.stops[1:-1]

    legs_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="dim")
    legs_table.add_column("From")
    legs_table.add_column("→")
    legs_table.add_column("To")
    legs_table.add_column("Δv", justify="right")
    legs_table.add_column("aero", justify="center", no_wrap=True, min_width=7)

    credit_pct = 100 - AEROBRAKE_RESIDUAL_PCT

    def _aero_cell(edge) -> str:
        if not edge.can_aerobrake:
            return ""
        return f"✓ −{credit_pct:g}%" if trip.aerobrake else "✓ off"

    for leg_idx, leg in enumerate(trip.legs):
        for edge in leg:
            legs_table.add_row(
                edge.from_slug,
                "→",
                edge.to_slug,
                f"{edge.dv_m_s:>7,.0f} m/s",
                _aero_cell(edge),
            )
        # Emit stop annotation after each leg except the last.
        if leg_idx < len(intermediate_stops):
            stop = intermediate_stops[leg_idx]
            legs_table.add_row(
                f"[dim italic]— stop: {stop.action} —[/]",
                "",
                "",
                "",
                "",
            )

    totals = Table.grid(padding=(0, 2))
    totals.add_column(style="dim")
    totals.add_column(justify="right")
    totals.add_row("Raw total", f"[bold]{trip.total_raw:,.0f} m/s[/]")
    if trip.aerobrake:
        savings = trip.total_raw - trip.total_aerobraked
        totals.add_row(
            "With aerobrake",
            f"[bold]{trip.total_aerobraked:,.0f} m/s[/]  [dim](−{savings:,.0f})[/]",
        )
        planned = trip.total_aerobraked_planned
    else:
        planned = trip.total_planned
    totals.add_row(
        f"Planned (+{trip.margin_pct:g}% margin)",
        f"[bold green]{planned:,.0f} m/s[/]",
    )

    # Title includes the via chain in body(action) form when present
    if intermediate_stops:
        via_chain = " → ".join(
            f"{s.slug.removesuffix(ACTION_SUFFIXES[s.action])}({s.action})"
            for s in intermediate_stops
        )
        title = f"[bold]Δv trip — {from_slug} → {via_chain} → {to_slug}[/]"
    else:
        title = f"[bold]Δv trip — {from_slug} → {to_slug}[/]"

    return Panel(
        Group(legs_table, Text(""), totals),
        title=title,
        box=box.ROUNDED,
    )


def comm_report_panel(r: dict) -> Panel:
    status_color = "green" if r["coverage_ok"] else "red"
    status_glyph = "✓ COVERAGE OK" if r["coverage_ok"] else "✗ COVERAGE FAILS"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim")
    grid.add_column()
    grid.add_row("Satellites", str(r["n_sats"]))
    grid.add_row("Antenna", f"{r['antenna']}")
    grid.add_row("DSN level", str(r["dsn_level"]))
    grid.add_row("Min elevation", f"{r['min_elev_deg']}°")

    orbit = Table.grid(padding=(0, 2))
    orbit.add_column(style="dim")
    orbit.add_column()
    orbit.add_row("Altitude", fmt_dist(r["orbit_altitude_m"]))
    orbit.add_row("Orbit radius", fmt_dist(r["orbit_radius_m"]))
    orbit.add_row("Period", fmt_time(r["period_s"]))

    ranges = Table.grid(padding=(0, 2))
    ranges.add_column(style="dim")
    ranges.add_column()
    ranges.add_row("Sat ↔ Sat", fmt_dist(r["range_sat_to_sat_m"]))
    ranges.add_row("Sat ↔ DSN", fmt_dist(r["range_sat_to_dsn_m"]))
    ranges.add_row("Separation", fmt_dist(r["sat_separation_m"]))

    status = Table.grid(padding=(0, 2))
    status.add_column()
    status.add_row(f"[{status_color} bold]{status_glyph}[/]")
    status.add_row(f"[dim]Margin:[/] {fmt_dist(r['coverage_margin_m'])}")
    if r["suggestion"]:
        status.add_row(f"[yellow]{r['suggestion']}[/]")

    body_renderables: list[RenderableType] = [
        grid, Text(""),
        Text("Required orbit", style="bold"), orbit, Text(""),
        Text("Comm ranges", style="bold"), ranges, Text(""),
        status,
    ]
    return Panel(
        Group(*body_renderables),
        title=f"[bold]Comm network — {r['body']}[/]",
        box=box.DOUBLE,
    )
