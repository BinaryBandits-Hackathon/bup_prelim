"""PuLP-based energy optimizer for the GridWise challenge."""

import pulp
from app.models import (
    OptimizeRequest, DirectiveInterpretation, DirectiveType,
    HourlyPlanEntry, BatteryAction, OptimizeResponse
)


def optimize_energy(
    request: OptimizeRequest,
    directives: list[DirectiveInterpretation]
) -> OptimizeResponse:
    """Build and solve the LP, return a complete OptimizeResponse."""

    hours_data = sorted(request.hours, key=lambda h: h.hour)
    bat = request.battery
    H = 24  # planning horizon

    # ─── Compute effective solar (apply solar_reduction directives) ───
    effective_solar = [h.solar_kwh for h in hours_data]
    for d in directives:
        if d.applies and d.directive_type == DirectiveType.SOLAR_REDUCTION and d.structured_adjustment:
            factor = d.structured_adjustment.get("factor", 1.0)
            for hour in d.structured_adjustment.get("hours", []):
                if 0 <= hour < H:
                    effective_solar[hour] = hours_data[hour].solar_kwh * factor

    # ─── Collect directive constraints ───
    no_charge_hours = set()
    no_discharge_hours = set()
    min_reserve = {}  # hour -> minimum_energy_kwh
    max_grid = {}     # hour -> max_grid_kwh

    for d in directives:
        if not d.applies or not d.structured_adjustment:
            continue
        adj_hours = d.structured_adjustment.get("hours", [])

        if d.directive_type == DirectiveType.NO_CHARGE_WINDOW:
            no_charge_hours.update(adj_hours)

        elif d.directive_type == DirectiveType.NO_DISCHARGE_WINDOW:
            no_discharge_hours.update(adj_hours)

        elif d.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE:
            reserve = d.structured_adjustment.get("minimum_energy_kwh", 0)
            for hour in adj_hours:
                min_reserve[hour] = max(min_reserve.get(hour, 0), reserve)

        elif d.directive_type == DirectiveType.MAX_GRID_WINDOW:
            cap = d.structured_adjustment.get("max_grid_kwh", float('inf'))
            for hour in adj_hours:
                if hour not in max_grid:
                    max_grid[hour] = cap
                else:
                    max_grid[hour] = min(max_grid[hour], cap)

    # ─── Build LP ───
    prob = pulp.LpProblem("GridWise", pulp.LpMinimize)

    # Decision variables
    grid = [pulp.LpVariable(f"grid_{h}", lowBound=0) for h in range(H)]
    solar_used = [pulp.LpVariable(f"solar_{h}", lowBound=0, upBound=effective_solar[h]) for h in range(H)]
    charge = [pulp.LpVariable(f"charge_{h}", lowBound=0, upBound=bat.max_charge_kwh_per_hour) for h in range(H)]
    discharge = [pulp.LpVariable(f"discharge_{h}", lowBound=0, upBound=bat.max_discharge_kwh_per_hour) for h in range(H)]
    bat_energy = [pulp.LpVariable(f"bat_{h}", lowBound=bat.minimum_energy_kwh, upBound=bat.capacity_kwh) for h in range(H)]

    # Objective: minimize total grid electricity cost
    prob += pulp.lpSum(grid[h] * hours_data[h].tariff_bdt_per_kwh for h in range(H))

    for h in range(H):
        # Energy balance: grid + solar + discharge = demand + charge
        prob += (
            grid[h] + solar_used[h] + discharge[h]
            == hours_data[h].demand_kwh + charge[h],
            f"balance_{h}"
        )

        # Battery state transitions
        if h == 0:
            prob += bat_energy[h] == bat.initial_energy_kwh + charge[h] - discharge[h], f"bat_trans_{h}"
        else:
            prob += bat_energy[h] == bat_energy[h - 1] + charge[h] - discharge[h], f"bat_trans_{h}"

        # ─── Directive constraints ───
        if h in no_charge_hours:
            prob += charge[h] == 0, f"no_charge_{h}"

        if h in no_discharge_hours:
            prob += discharge[h] == 0, f"no_discharge_{h}"

        if h in min_reserve:
            prob += bat_energy[h] >= min_reserve[h], f"min_reserve_{h}"

        if h in max_grid:
            prob += grid[h] <= max_grid[h], f"max_grid_{h}"

    # End-of-day battery neutrality
    prob += bat_energy[H - 1] == bat.initial_energy_kwh, "end_of_day"

    # ─── Solve ───
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=15)
    status = prob.solve(solver)

    if pulp.LpStatus[status] != "Optimal":
        # Fallback: try without time limit
        solver2 = pulp.PULP_CBC_CMD(msg=False)
        status = prob.solve(solver2)

    # ─── Extract solution ───
    hourly_plan = []
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for h in range(H):
        g = round(pulp.value(grid[h]) or 0, 4)
        s = round(pulp.value(solar_used[h]) or 0, 4)
        ch = round(pulp.value(charge[h]) or 0, 4)
        dis = round(pulp.value(discharge[h]) or 0, 4)
        be = round(pulp.value(bat_energy[h]) or 0, 4)

        # Determine battery action
        if ch > 0.001:
            action = BatteryAction.CHARGE
            bat_kwh = ch
        elif dis > 0.001:
            action = BatteryAction.DISCHARGE
            bat_kwh = dis
        else:
            action = BatteryAction.IDLE
            bat_kwh = 0.0

        hourly_plan.append(HourlyPlanEntry(
            hour=h,
            grid_kwh=round(g, 2),
            solar_used_kwh=round(s, 2),
            battery_action=action,
            battery_kwh=round(bat_kwh, 2),
            battery_energy_after_kwh=round(be, 2)
        ))

        total_grid += g
        total_cost += g * hours_data[h].tariff_bdt_per_kwh
        peak_grid = max(peak_grid, g)

    # Build summary
    active_directives = [d for d in directives if d.applies]
    if active_directives:
        dir_desc = ", ".join(d.directive_type.value for d in active_directives)
        summary = f"Applied {len(active_directives)} directive(s) ({dir_desc}), "
    else:
        summary = "No active directives. "
    summary += f"optimized 24-hour schedule to minimize grid cost at {round(total_cost, 2)} BDT."

    return OptimizeResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=directives,
        hourly_plan=hourly_plan,
        total_grid_kwh=round(total_grid, 2),
        total_cost_bdt=round(total_cost, 2),
        peak_grid_kwh=round(peak_grid, 2),
        plan_summary=summary
    )
