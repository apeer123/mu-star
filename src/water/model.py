import csv
import os
import sys


def load_costs(costs_csv_path):
    if not os.path.exists(costs_csv_path):
        raise FileNotFoundError(f"Missing required costs file: {costs_csv_path}")

    costs = {}
    with open(costs_csv_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            comp = row.get("component", "").strip()
            if comp and "cost" in row and row["cost"].strip():
                try:
                    costs[comp] = float(row["cost"])
                except ValueError:
                    pass

    if not costs:
        raise ValueError(f"No valid cost entries found in {costs_csv_path}")

    return costs


def load_basin_parameters(params_csv_path):
    params = {}
    if not os.path.exists(params_csv_path):
        return params

    with open(params_csv_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = (row.get("basin") or row.get("catchment") or "").strip().upper()
            if b:
                try:
                    params[b] = {
                        "s_max": float(row.get("reservoir_capacity_m3", 0.0)),
                        "s_min": float(row.get("dead_storage_m3", 0.0)),
                        "hydro_max": float(row.get("hydropower_max_m3", 0.0)),
                        "mrf_target": float(row.get("mrf_target_m3", 0.0)),
                        "s_init": float(row.get("initial_storage_m3", row.get("reservoir_capacity_m3", 0.0)))
                    }
                except ValueError:
                    pass
    return params


def discover_available_basins(data_dir):
    unified_csv = os.path.join(data_dir, "catchment_data_monthly_m3.csv")
    if not os.path.exists(unified_csv):
        raise FileNotFoundError(f"Missing unified input data file: {unified_csv}")

    basins = []
    with open(unified_csv, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = [h.strip().lower() for h in next(reader)]
        catch_idx = 1
        for idx, h in enumerate(header):
            if h in ["catchment", "basin", "basin_name", "bassin"]:
                catch_idx = idx
                break
        for r in reader:
            if r and len(r) > catch_idx:
                b = r[catch_idx].strip()
                if b and b not in basins:
                    basins.append(b)
    basins.sort()
    return basins


def load_basin_timeseries(data_dir, target_basin="J"):
    target = target_basin.strip().upper()
    unified_csv = os.path.join(data_dir, "catchment_data_monthly_m3.csv")

    dates = []
    inflow_m3 = []
    dem_targets = []

    with open(unified_csv, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = (row.get("catchment") or row.get("basin") or "").strip().upper()
            if b == target:
                d = row["date"].strip()
                dates.append(d)
                inflow_m3.append(float(row.get("inflow", 0.0)))
                dem_targets.append({
                    "municipal": float(row.get("demand_municipal", 0.0)),
                    "industrial": float(row.get("demand_industrial", 0.0)),
                    "irrigation": float(row.get("demand_irrigation", 0.0))
                })

    if not dates:
        raise ValueError(f"No records found for basin '{target_basin}' in {unified_csv}")

    return dates, inflow_m3, dem_targets


def solve_downscaled_simulation(basin, data_dir, costs, basin_params):
    dates, inflow_m3, dem_targets = load_basin_timeseries(data_dir, target_basin=basin)
    n_months = len(dates)
    n_years = n_months / 12.0

    b_key = basin.upper()
    if b_key not in basin_params:
        raise ValueError(
            f"Basin '{basin}' not found in {os.path.join(data_dir, 'basin_parameters.csv')}. "
            f"All basins must be configured in basin_parameters.csv (enter 0.0 if no reservoir or hydropower)."
        )

    bp = basin_params[b_key]
    s_max = bp["s_max"]
    s_min = bp["s_min"]
    hydro_max = bp["hydro_max"]
    mrf_target = bp["mrf_target"]
    s_init = bp["s_init"]

    s_current = s_init

    storage_m3 = []
    delta_storage_m3 = []
    hydropower_m3 = []
    municipal_m3 = []
    industrial_m3 = []
    irrigation_m3 = []
    sea_m3 = []

    for t in range(n_months):
        inf = inflow_m3[t]
        tgt_muni = dem_targets[t]["municipal"]
        tgt_indu = dem_targets[t]["industrial"]
        tgt_irri = dem_targets[t]["irrigation"]

        total_water = s_current + inf
        avail_for_release = max(0.0, total_water - s_min)

        deliv_mrf = min(avail_for_release, mrf_target)
        avail_for_release -= deliv_mrf

        deliv_muni = min(avail_for_release, tgt_muni)
        avail_for_release -= deliv_muni

        deliv_indu = min(avail_for_release, tgt_indu)
        avail_for_release -= deliv_indu

        deliv_irri = min(avail_for_release, tgt_irri)
        avail_for_release -= deliv_irri

        total_release = deliv_mrf + deliv_muni + deliv_indu + deliv_irri

        remaining_storage = total_water - total_release
        if remaining_storage > s_max:
            spill = remaining_storage - s_max
            s_next = s_max
        else:
            spill = 0.0
            s_next = max(0.0, remaining_storage)

        q_hydro = min(total_release, hydro_max)
        q_sea = deliv_mrf + spill

        delta_s = s_next - s_current
        s_current = s_next

        storage_m3.append(round(s_current, 1))
        delta_storage_m3.append(round(delta_s, 1))
        hydropower_m3.append(round(q_hydro, 1))
        municipal_m3.append(round(deliv_muni, 1))
        industrial_m3.append(round(deliv_indu, 1))
        irrigation_m3.append(round(deliv_irri, 1))
        sea_m3.append(round(q_sea, 1))

    residuals = []
    for t in range(n_months):
        tot_d = municipal_m3[t] + industrial_m3[t] + irrigation_m3[t]
        res = inflow_m3[t] - tot_d - sea_m3[t] - delta_storage_m3[t]
        residuals.append(res)

    max_err = max(abs(r) for r in residuals)

    sum_inf = sum(inflow_m3)
    sum_muni = sum(municipal_m3)
    sum_indu = sum(industrial_m3)
    sum_irri = sum(irrigation_m3)
    sum_hydro = sum(hydropower_m3)
    sum_dem = sum_muni + sum_indu + sum_irri
    sum_sea = sum(sea_m3)

    rel_muni = sum(1 for t in range(n_months) if municipal_m3[t] >= dem_targets[t]["municipal"] - 1.0) / n_months * 100
    rel_indu = sum(1 for t in range(n_months) if industrial_m3[t] >= dem_targets[t]["industrial"] - 1.0) / n_months * 100
    rel_irri = sum(1 for t in range(n_months) if irrigation_m3[t] >= dem_targets[t]["irrigation"] - 1.0) / n_months * 100

    return {
        "basin": basin.upper(),
        "n_months": n_months,
        "inflow_Mm3_yr": round(sum_inf / n_years / 1e6, 2),
        "demands_Mm3_yr": round(sum_dem / n_years / 1e6, 2),
        "municipal_Mm3_yr": round(sum_muni / n_years / 1e6, 2),
        "industrial_Mm3_yr": round(sum_indu / n_years / 1e6, 2),
        "irrigation_Mm3_yr": round(sum_irri / n_years / 1e6, 2),
        "sea_Mm3_yr": round(sum_sea / n_years / 1e6, 2),
        "hydro_Mm3_yr": round(sum_hydro / n_years / 1e6, 2),
        "max_err_m3": max_err,
        "rel_muni_pct": round(rel_muni, 1),
        "rel_indu_pct": round(rel_indu, 1),
        "rel_irri_pct": round(rel_irri, 1)
    }


def solve_all_basins():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    costs_csv = os.path.join(data_dir, "costs.csv")
    params_csv = os.path.join(data_dir, "basin_parameters.csv")

    costs = load_costs(costs_csv)
    basin_params = load_basin_parameters(params_csv)
    basins = discover_available_basins(data_dir)

    print("\n" )
    print(f"CATCHMENTs WATER BALANCE SIMULATION ({len(basins)} BASINS)")
    print("\n" )
    summary_list = []
    for b in basins:
        res = solve_downscaled_simulation(basin=b, data_dir=data_dir, costs=costs, basin_params=basin_params)
        summary_list.append(res)
        status = "PASSED (0.000000 m³)" if res["max_err_m3"] < 1e-4 else "FAIL"
        print(f"  Basin {b:>2}: Inflow = {res['inflow_Mm3_yr']:>6.2f} Mm³/yr | "
              f"Demands = {res['demands_Mm3_yr']:>6.2f} Mm³/yr | "
              f"Sea = {res['sea_Mm3_yr']:>6.2f} Mm³/yr | "
              f"Muni Rel = {res['rel_muni_pct']:>5.1f}% | Mass Balance: {status}")

    out_dir = os.path.join(base_dir, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    summary_csv = os.path.join(out_dir, "all_basins_water_balance_summary.csv")

    with open(summary_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "basin",
            "inflow_Mm3_yr",
            "demands_delivered_Mm3_yr",
            "municipal_Mm3_yr",
            "industrial_Mm3_yr",
            "irrigation_Mm3_yr",
            "sea_discharge_Mm3_yr",
            "hydropower_Mm3_yr",
            "max_residual_m3",
            "municipal_reliability_pct",
            "industrial_reliability_pct",
            "irrigation_reliability_pct"
        ])
        for r in summary_list:
            writer.writerow([
                r["basin"],
                r["inflow_Mm3_yr"],
                r["demands_Mm3_yr"],
                r["municipal_Mm3_yr"],
                r["industrial_Mm3_yr"],
                r["irrigation_Mm3_yr"],
                r["sea_Mm3_yr"],
                r["hydro_Mm3_yr"],
                f"{r['max_err_m3']:.6f}",
                r["rel_muni_pct"],
                r["rel_indu_pct"],
                r["rel_irri_pct"]
            ])

    print(f" {len(basins)} catchments mass balance closure.")
    print(f"summary saved to:\n  {summary_csv}")


if __name__ == "__main__":
    solve_all_basins()
