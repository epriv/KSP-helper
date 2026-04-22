"""KSP Mission Planner CLI — Typer app, entry point for the `ksp` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ksp_planner import db as dblib
from ksp_planner import plans as plans_mod
from ksp_planner.comms import comm_network_report
from ksp_planner.dv_map import Stop, plan_trip, resolve_stop
from ksp_planner.formatting import (
    antennas_table,
    bodies_table,
    body_detail_panel,
    comm_report_panel,
    dsn_table,
    dv_trip_panel,
    fmt_time,
    plan_detail_panel,
    plans_table,
)
from ksp_planner.orbital import (
    burn_time,
    interbody_hohmann,
    surface_gravity,
    tsiolkovsky_dv,
    twr,
)

app = typer.Typer(
    help="KSP Mission Planner — local SQLite-backed calculators for Kerbal Space Program.",
    no_args_is_help=True,
)
console = Console()

DbOption = Annotated[
    Path,
    typer.Option("--db", help="Path to ksp.db", envvar="KSP_DB_PATH"),
]


def _require_db(path: Path) -> None:
    if not path.exists():
        console.print(f"[red]No database at {path}.[/] Run `make seed` first.")
        raise typer.Exit(2)


def _open(path: Path):
    _require_db(path)
    return dblib.connect(path)


@app.command()
def body(
    slug: Annotated[str, typer.Argument(help="Body slug, e.g. kerbin, mun, duna")],
    db: DbOption = Path("ksp.db"),
):
    """Show all known parameters for a body."""
    conn = _open(db)
    try:
        b = dblib.get_body(conn, slug.lower())
    except KeyError:
        console.print(f"[red]Unknown body:[/] {slug}")
        raise typer.Exit(1) from None
    parent = dblib.get_body(conn, _slug_by_id(conn, b["parent_id"])) if b["parent_id"] else None
    console.print(body_detail_panel(b, parent))


def _slug_by_id(conn, body_id: int) -> str:
    row = conn.execute("SELECT slug FROM bodies WHERE id = ?", (body_id,)).fetchone()
    return row["slug"]


@app.command()
def bodies(
    body_type: Annotated[
        str | None,
        typer.Option("--type", "-t", help="Filter: star | planet | moon"),
    ] = None,
    db: DbOption = Path("ksp.db"),
):
    """List celestial bodies."""
    conn = _open(db)
    console.print(bodies_table(dblib.list_bodies(conn, body_type)))


@app.command()
def antennas(db: DbOption = Path("ksp.db")):
    """List stock antennas and their reference ranges."""
    conn = _open(db)
    console.print(antennas_table(dblib.list_antennas(conn)))


@app.command()
def dsn(db: DbOption = Path("ksp.db")):
    """List Deep Space Network tracking station levels."""
    conn = _open(db)
    levels = [dict(r) for r in conn.execute("SELECT * FROM dsn_levels ORDER BY level")]
    console.print(dsn_table(levels))


def _do_comms(conn, cfg: dict) -> dict:
    b = dblib.get_body(conn, cfg["target"].lower())
    a = dblib.get_antenna(conn, cfg["antenna"])
    d = dblib.get_dsn(conn, cfg["dsn_level"])
    report = comm_network_report(b, cfg["sats"], a, d, cfg["min_elev"])
    console.print(comm_report_panel(report))
    return report


@app.command()
def comms(
    target: Annotated[str, typer.Argument(help="Target body slug")],
    sats: Annotated[int, typer.Option("--sats", "-n", min=2)] = 3,
    antenna: Annotated[str, typer.Option("--antenna", "-a")] = "RA-15 Relay Antenna",
    dsn_level: Annotated[int, typer.Option("--dsn", "-d", min=1, max=3)] = 2,
    min_elev: Annotated[float, typer.Option("--min-elev", "-e")] = 5.0,
    save: Annotated[
        str | None, typer.Option("--save", help="Save this config as a named plan")
    ] = None,
    db: DbOption = Path("ksp.db"),
):
    """Run the comm network calculator for a constellation around TARGET."""
    conn = _open(db)
    cfg = {
        "target": target, "sats": sats, "antenna": antenna,
        "dsn_level": dsn_level, "min_elev": min_elev,
    }
    try:
        _do_comms(conn, cfg)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None

    if save:
        plans_mod.save(db, save, "comms", cfg)
        console.print(f"[green]✓ saved as plan '{save}'[/]")


def _do_hohmann(conn, cfg: dict) -> dict:
    src = dblib.get_body(conn, cfg["source"].lower())
    tgt = dblib.get_body(conn, cfg["target"].lower())
    if src["parent_id"] != tgt["parent_id"] or src["parent_id"] is None:
        raise ValueError(
            f"bodies don't share a common parent: "
            f"{src['name']} (parent_id={src['parent_id']}) vs "
            f"{tgt['name']} (parent_id={tgt['parent_id']})"
        )
    parent = dblib.get_body(conn, _slug_by_id(conn, src["parent_id"]))
    result = interbody_hohmann(
        mu_parent=parent["mu_m3s2"],
        sma_source_m=src["sma_m"],
        sma_target_m=tgt["sma_m"],
        mu_source_body=src["mu_m3s2"],
        r_parking_source_m=src["radius_m"] + cfg["from_alt_km"] * 1000,
        mu_target_body=tgt["mu_m3s2"],
        r_parking_target_m=tgt["radius_m"] + cfg["to_alt_km"] * 1000,
    )
    console.print(
        f"[bold]Hohmann transfer[/] "
        f"{src['name']} (parking alt {cfg['from_alt_km']:g} km) → "
        f"{tgt['name']} (parking alt {cfg['to_alt_km']:g} km)"
    )
    console.print(f"  Ejection Δv     : {result['dv_eject_m_s']:,.1f} m/s")
    console.print(f"  Insertion Δv    : {result['dv_insert_m_s']:,.1f} m/s")
    console.print(f"  [bold]Total Δv        : {result['dv_total_m_s']:,.1f} m/s[/]")
    console.print(f"  Transfer time   : {fmt_time(result['transfer_time_s'])}")
    console.print(f"  v_∞ at source   : {result['v_hyp_source_m_s']:,.1f} m/s")
    console.print(f"  v_∞ at target   : {result['v_hyp_target_m_s']:,.1f} m/s")
    return result


@app.command()
def hohmann(
    source: Annotated[str, typer.Argument(help="Departure body slug")],
    target: Annotated[str, typer.Argument(help="Arrival body slug")],
    from_alt: Annotated[
        float, typer.Option("--from-alt", help="Source parking altitude (km)")
    ] = 100.0,
    to_alt: Annotated[
        float, typer.Option("--to-alt", help="Target parking altitude (km)")
    ] = 100.0,
    save: Annotated[
        str | None, typer.Option("--save", help="Save this config as a named plan")
    ] = None,
    db: DbOption = Path("ksp.db"),
):
    """Compute an inter-body Hohmann transfer (patched conics)."""
    conn = _open(db)
    cfg = {"source": source, "target": target, "from_alt_km": from_alt, "to_alt_km": to_alt}
    try:
        _do_hohmann(conn, cfg)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None

    if save:
        plans_mod.save(db, save, "hohmann", cfg)
        console.print(f"[green]✓ saved as plan '{save}'[/]")


def _do_twr(conn, cfg: dict) -> dict:
    b = dblib.get_body(conn, cfg["body"].lower())
    g = surface_gravity(b["mu_m3s2"], b["radius_m"])
    ratio = twr(cfg["thrust"], cfg["mass"], g)
    console.print(f"[bold]TWR at {b['name']}[/] (g = {g:.3f} m/s²)")
    console.print(f"  Thrust         : {cfg['thrust']:,.1f} N")
    console.print(f"  Mass           : {cfg['mass']:,.1f} kg")
    console.print(f"  [bold]TWR            : {ratio:.3f}[/]")
    if ratio < 1.0:
        console.print("  [red]Can't lift off — TWR < 1[/]")
    elif ratio > 3.0:
        console.print("  [yellow]High TWR — over-thrusted for most missions[/]")
    return {"twr": ratio, "g": g}


@app.command("twr")
def twr_cmd(
    thrust: Annotated[float, typer.Option("--thrust", "-t", help="Thrust in newtons")],
    mass: Annotated[float, typer.Option("--mass", "-m", help="Vessel mass in kg")],
    body_slug: Annotated[
        str, typer.Option("--body", "-b", help="Body for local gravity")
    ] = "kerbin",
    save: Annotated[
        str | None, typer.Option("--save", help="Save this config as a named plan")
    ] = None,
    db: DbOption = Path("ksp.db"),
):
    """Thrust-to-weight ratio at a body's surface gravity."""
    conn = _open(db)
    cfg = {"thrust": thrust, "mass": mass, "body": body_slug}
    try:
        _do_twr(conn, cfg)
    except KeyError:
        console.print(f"[red]Unknown body: {body_slug}[/]")
        raise typer.Exit(1) from None

    if save:
        plans_mod.save(db, save, "twr", cfg)
        console.print(f"[green]✓ saved as plan '{save}'[/]")


def _do_dv_budget(conn, cfg: dict) -> dict:
    dv = tsiolkovsky_dv(cfg["isp"], cfg["wet"], cfg["dry"])
    ratio = cfg["wet"] / cfg["dry"]
    console.print("[bold]Δv budget[/]")
    console.print(f"  Isp        : {cfg['isp']:g} s")
    console.print(f"  Wet mass   : {cfg['wet']:,.1f} kg")
    console.print(f"  Dry mass   : {cfg['dry']:,.1f} kg")
    console.print(f"  Mass ratio : {ratio:.3f}")
    console.print(f"  [bold]Δv         : {dv:,.1f} m/s[/]")
    thrust = cfg.get("thrust")
    if thrust is not None:
        t = burn_time(cfg["wet"], cfg["dry"], cfg["isp"], thrust)
        console.print(f"  Thrust     : {thrust:,.1f} N")
        console.print(f"  Burn time  : {fmt_time(t)}")
    return {"dv_m_s": dv}


@app.command("dv-budget")
def dv_budget(
    isp: Annotated[float, typer.Option("--isp", help="Specific impulse (s)")],
    wet: Annotated[float, typer.Option("--wet", help="Wet mass (kg)")],
    dry: Annotated[float, typer.Option("--dry", help="Dry mass (kg)")],
    thrust: Annotated[
        float | None,
        typer.Option("--thrust", help="Engine thrust (N); if given, burn time is shown"),
    ] = None,
    save: Annotated[
        str | None, typer.Option("--save", help="Save this config as a named plan")
    ] = None,
    db: DbOption = Path("ksp.db"),
):
    """Tsiolkovsky rocket equation: Δv from stage mass ratio and Isp."""
    cfg = {"isp": isp, "wet": wet, "dry": dry, "thrust": thrust}
    try:
        _do_dv_budget(None, cfg)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None

    if save:
        _require_db(db)
        plans_mod.save(db, save, "dv_budget", cfg)
        console.print(f"[green]✓ saved as plan '{save}'[/]")


def _parse_via(raw: str) -> tuple[str, str]:
    """Parse a --via value of the form 'body' or 'body:action'. Returns (body, action)."""
    parts = raw.split(":")
    if len(parts) == 1:
        body, action = parts[0], "orbit"
    elif len(parts) == 2:
        body, action = parts
    else:
        raise ValueError(f"expected body[:action], got {raw!r}")
    if not body:
        raise ValueError(f"expected body[:action], got {raw!r}")
    return body, action


@app.command()
def dv(
    from_slug: Annotated[str, typer.Argument(help="Departure node slug, e.g. kerbin_surface")],
    to_slug: Annotated[str, typer.Argument(help="Arrival node slug, e.g. mun_surface")],
    via: Annotated[
        list[str] | None,
        typer.Option(
            "--via",
            help="Intermediate stop as body[:action]. Repeatable. action ∈ land|orbit|flyby, default orbit.",  # noqa: E501
        ),
    ] = None,
    margin: Annotated[
        float,
        typer.Option("--margin", "-m", help="Margin percentage on the raw total"),
    ] = 5.0,
    db: DbOption = Path("ksp.db"),
):
    """Walk the canonical Δv chart from one node to another and total the cost."""
    conn = _open(db)
    graph = dblib.load_dv_graph(conn)

    stops: list[Stop] = [Stop(from_slug.lower())]
    for raw in via or []:
        try:
            body, action = _parse_via(raw)
            stops.append(resolve_stop(graph, body.lower(), action.lower()))
        except (ValueError, KeyError) as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(1) from None
    stops.append(Stop(to_slug.lower()))

    try:
        trip = plan_trip(graph, stops, margin_pct=margin)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None
    console.print(dv_trip_panel(trip, from_slug.lower(), to_slug.lower()))


plan_app = typer.Typer(help="Manage saved mission plans.", no_args_is_help=True)
app.add_typer(plan_app, name="plan")


@plan_app.command("list")
def plan_list(db: DbOption = Path("ksp.db")):
    """List all saved plans."""
    _require_db(db)
    all_plans = plans_mod.list_all(db)
    if not all_plans:
        console.print("[dim]No plans saved yet.[/]")
        return
    console.print(plans_table(all_plans))


@plan_app.command("show")
def plan_show(
    name: Annotated[str, typer.Argument(help="Plan name")],
    db: DbOption = Path("ksp.db"),
):
    """Show the stored config for a saved plan."""
    _require_db(db)
    try:
        plan = plans_mod.load(db, name)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None
    console.print(plan_detail_panel(plan))


_PLAN_RUNNERS = {
    "comms": _do_comms,
    "hohmann": _do_hohmann,
    "twr": _do_twr,
    "dv_budget": _do_dv_budget,
}


@plan_app.command("run")
def plan_run(
    name: Annotated[str, typer.Argument(help="Plan name")],
    db: DbOption = Path("ksp.db"),
):
    """Re-run a saved plan against the current calculator code."""
    conn = _open(db)
    try:
        plan = plans_mod.load(db, name)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None

    runner = _PLAN_RUNNERS.get(plan["kind"])
    if runner is None:
        console.print(f"[red]Plan kind {plan['kind']!r} not runnable from CLI yet.[/]")
        raise typer.Exit(1)
    try:
        runner(conn, plan["config"])
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None


@plan_app.command("delete")
def plan_delete(
    name: Annotated[str, typer.Argument(help="Plan name")],
    db: DbOption = Path("ksp.db"),
):
    """Delete a saved plan."""
    _require_db(db)
    if not plans_mod.delete(db, name):
        console.print(f"[red]No plan named {name!r}[/]")
        raise typer.Exit(1)
    console.print(f"[green]✓ deleted plan '{name}'[/]")


if __name__ == "__main__":
    app()

