from __future__ import annotations

import hashlib
import inspect
import json
import os
import statistics
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy import stats

from django.core.management.base import BaseCommand
from django.db import transaction

from rostering_app.converters import employees_to_core, shifts_to_core
from rostering_app.models import Company, Employee, Shift, ScheduleEntry

from rostering_app.services.kpi_calculator import KPICalculator
# Enhanced analytics is optional; guard import
try:
    from rostering_app.services.enhanced_analytics import EnhancedAnalytics
except Exception:  # pragma: no cover
    EnhancedAnalytics = None  # type: ignore

from scheduling_core import ILPScheduler
from scheduling_core.base import SchedulingProblem
from scheduling_core.genetic_algorithm import GeneticAlgorithmScheduler
from scheduling_core.simulated_annealing_compact import SimulatedAnnealingScheduler

HEURISTIC_ALGORITHMS = {"Genetic Algorithm", "Simulated Annealing"}

DEFAULT_TEST_CASES = [
    {"name": "small_company", "display_name": "Kleines Unternehmen (10 MA, 2 Schichten)",
     "employee_fixture": "rostering_app/fixtures/small_company/employees.json",
     "shift_fixture": "rostering_app/fixtures/small_company/shifts.json"},
    {"name": "medium_company", "display_name": "Mittleres Unternehmen (30 MA, 3 Schichten)",
     "employee_fixture": "rostering_app/fixtures/medium_company/employees.json",
     "shift_fixture": "rostering_app/fixtures/medium_company/shifts.json"},
    {"name": "bigger_company", "display_name": "Größeres Unternehmen (70 MA, 4 Schichten)",
     "employee_fixture": "rostering_app/fixtures/bigger_company/employees.json",
     "shift_fixture": "rostering_app/fixtures/bigger_company/shifts.json"},
    {"name": "large_company", "display_name": "Großes Unternehmen (100 MA, 5 Schichten)",
     "employee_fixture": "rostering_app/fixtures/large_company/employees.json",
     "shift_fixture": "rostering_app/fixtures/large_company/shifts.json"},
    {"name": "tight_company", "display_name": "Mittleres Unternehmen (eng) (18 MA, 3 Schichten)",
     "employee_fixture": "rostering_app/fixtures/tight_company/employees.json",
     "shift_fixture": "rostering_app/fixtures/tight_company/shifts.json"},
]

COMPANY_NAME_MAP = {
    "small_company": "Kleines Unternehmen",
    "medium_company": "Mittleres Unternehmen",
    "bigger_company": "Größeres Unternehmen",
    "large_company": "Großes Unternehmen",
    "tight_company": "Knappes Unternehmen",
}


class Command(BaseCommand):
    help = "Benchmark scheduling algorithms across different company sizes"

    def add_arguments(self, parser):
        parser.add_argument("--load-fixtures", action="store_true", help="Load fixtures and clear DB")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--algorithm", type=str, help="LinearProgramming, GeneticAlgorithm, CompactSA")
        parser.add_argument("--company", type=str, help="small_company, medium_company, bigger_company, large_company, tight_company")
        parser.add_argument("--runs", type=int, default=15)
        parser.add_argument("--base-seed", type=int, default=42)
        # enforce stochasticity through input shuffling
        parser.add_argument("--shuffle-inputs", action="store_true",
                            help="Shuffle employees/shifts order per run (only for heuristics by default).")
        parser.add_argument("--shuffle-scope", type=str, default="both", choices=["employees", "shifts", "both"],
                            help="Which inputs to shuffle when --shuffle-inputs is enabled.")
        parser.add_argument("--shuffle-seed-offset", type=int, default=50000,
                            help="Seed offset used for shuffling per run (base_seed + offset + run_idx).")
        parser.add_argument("--shuffle-ilp", action="store_true",
                            help="Also shuffle inputs for ILP (off by default).")

    def handle(self, *args, **opts):
        load_fixtures = opts.get("load_fixtures", False)
        algo_filter = opts.get("algorithm")
        company_filter = opts.get("company")
        runs_default = int(opts.get("runs", 15))
        base_seed = int(opts.get("base_seed", 42))
        shuffle_inputs = bool(opts.get("shuffle_inputs", False))
        shuffle_scope = opts.get("shuffle_scope", "both")
        shuffle_seed_offset = int(opts.get("shuffle_seed_offset", 50000))
        shuffle_ilp = bool(opts.get("shuffle_ilp", False))

        cases = list(DEFAULT_TEST_CASES)
        if company_filter:
            cases = [c for c in cases if c["name"] == company_filter]
            if not cases:
                self.stdout.write(self.style.ERROR(f"Company '{company_filter}' not found"))
                return

        algos = [ILPScheduler, GeneticAlgorithmScheduler, SimulatedAnnealingScheduler]
        if algo_filter:
            amap = {
                "LinearProgramming": ILPScheduler,
                "GeneticAlgorithm": GeneticAlgorithmScheduler,
                "CompactSA": SimulatedAnnealingScheduler,
            }
            if algo_filter not in amap:
                self.stdout.write(self.style.ERROR(f"Algorithm '{algo_filter}' not found"))
                return
            algos = [amap[algo_filter]]

        os.makedirs("export", exist_ok=True)

        if load_fixtures:
            self._reset_db()
            self._load_company_fixtures("rostering_app/fixtures/companies.json")
            for c in cases:
                self._load_fixtures(c["employee_fixture"], c["shift_fixture"])
            self.stdout.write(self.style.SUCCESS("Fixtures loaded."))
        else:
            self.stdout.write("Using existing DB contents")

        all_results: Dict[str, Any] = {}

        for tc in cases:
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write(f"Benchmarking: {tc['display_name']}")
            self.stdout.write("=" * 60 + "\n")

            company_name = COMPANY_NAME_MAP.get(tc["name"])
            company = (
                Company.objects.filter(name=company_name).first()
                if company_name
                else Company.objects.filter(name__icontains=tc["name"].split('_')[0]).first()
            )
            if not company:
                self.stdout.write(self.style.ERROR(f"Company not found for test case {tc['name']}"))
                continue

            base_problem = self._create_problem(company)

            results: Dict[str, Any] = {}
            for Alg in algos:
                alg = Alg(sundays_off=not company.sunday_is_workday)
                name = alg.name
                self.stdout.write(f"\nTesting {name}...")

                runs = runs_default if (name in HEURISTIC_ALGORITHMS or shuffle_ilp) else 1
                prev_signature = None

                run_results: List[Dict[str, Any]] = []
                all_runtimes: List[float] = []
                all_kpis: List[Dict[str, Any]] = []
                all_entries_counts: List[int] = []

                for run_idx in range(runs):
                    if runs > 1:
                        self.stdout.write(f"  Run {run_idx + 1}/{runs}...")

                    # Rebuild problem if we plan to shuffle inputs per run
                    problem = base_problem
                    if shuffle_inputs and (name in HEURISTIC_ALGORITHMS or shuffle_ilp):
                        problem = self._create_problem(company)  # fresh
                        shuffle_seed = base_seed + shuffle_seed_offset + run_idx
                        problem = self._maybe_shuffle_problem(problem, shuffle_seed, shuffle_scope)
                        self.stdout.write(f"    ↳ Shuffled {shuffle_scope} with seed {shuffle_seed}")

                    # Unique seeds for heuristics
                    if name in HEURISTIC_ALGORITHMS:
                        import random
                        random.seed(base_seed + run_idx)
                        np.random.seed(base_seed + run_idx)
                        # Try to also pass a seed directly into the algorithm if supported
                        try:
                            run_seed = base_seed + run_idx
                            # attribute
                            if hasattr(alg, "seed"):
                                setattr(alg, "seed", run_seed)
                            # setter
                            if hasattr(alg, "set_seed") and callable(getattr(alg, "set_seed")):
                                try:
                                    alg.set_seed(run_seed)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    t0 = time.time()
                    try:
                        # Try to pass seed kwarg if solve supports it
                        solve_kwargs: Dict[str, Any] = {}
                        try:
                            sig = inspect.signature(alg.solve)
                            if "seed" in sig.parameters and name in HEURISTIC_ALGORITHMS:
                                solve_kwargs["seed"] = base_seed + run_idx
                        except Exception:
                            pass

                        entries = alg.solve(problem, **solve_kwargs) if solve_kwargs else alg.solve(problem)
                        runtime = time.time() - t0

                        # Build signature & diff to previous run
                        signature, diff_pct = self._solution_signature(entries, prev_signature)
                        prev_signature = signature

                        # Persist entries for this run (clear only this algo/company)
                        self._clear_algorithm_company_entries(company, name)
                        self._save_entries(entries, name)

                        # Robustness simulation uses separate seed so it varies per run
                        import random as _r
                        _r.seed(base_seed + 10_000 + run_idx)
                        np.random.seed(base_seed + 10_000 + run_idx)

                        kpis = self._calculate_comprehensive_kpis(company, name)
                        # Attach diagnostics for transparency
                        kpis["__solution_hash"] = signature
                        kpis["__diff_vs_previous_percent"] = diff_pct

                        run_results.append({
                            "runtime": runtime,
                            "kpis": kpis,
                            "status": "success",
                            "entries_count": len(entries),
                            "solution_hash": signature,
                            "diff_vs_previous_percent": diff_pct,
                        })
                        all_runtimes.append(runtime)
                        all_kpis.append(kpis)
                        all_entries_counts.append(len(entries))

                        if runs > 1:
                            self.stdout.write(f"    ✓ Run {run_idx + 1} completed in {runtime:.2f}s; Δ={diff_pct:.2f}%")

                    except Exception as e:
                        runtime = time.time() - t0
                        run_results.append({"runtime": runtime, "kpis": None, "status": "failed", "error": str(e)})
                        all_runtimes.append(runtime)
                        self.stdout.write(f"    ✗ Run {run_idx + 1} failed: {e}")

                succ = [r for r in run_results if r["status"] == "success"]
                if succ:
                    runtime_stats = self._calculate_statistics(all_runtimes)
                    kpi_stats = self._calculate_kpi_statistics(all_kpis)
                    entries_stats = self._calculate_statistics(all_entries_counts)
                    results[name] = {
                        "runs": runs,
                        "successful_runs": len(succ),
                        "failed_runs": len(run_results) - len(succ),
                        "runtime_stats": runtime_stats,
                        "kpis_stats": kpi_stats,
                        "entries_count_stats": entries_stats,
                        "individual_runs": run_results,
                        "status": "success",
                    }
                    self.stdout.write(self.style.SUCCESS(
                        f"✓ {name} {len(succ)}/{runs} runs; avg {runtime_stats['mean']:.2f}s"))
                else:
                    results[name] = {
                        "runs": runs,
                        "successful_runs": 0,
                        "failed_runs": len(run_results),
                        "individual_runs": run_results,
                        "status": "failed",
                    }
                    self.stdout.write(self.style.ERROR(f"✗ {name} failed all {runs} runs"))

            # Save per-test-case results
            all_results[tc["name"]] = {
                "display_name": tc["display_name"],
                "results": results,
                "problem_size": {
                    "employees": len(base_problem.employees),
                    "shifts": len(base_problem.shifts),
                    "days": (base_problem.end_date - base_problem.start_date).days + 1,
                },
            }

            self._save_test_results(tc["name"], results, "export")
            self._maybe_generate_case_graphs(tc["name"], results, "export", company)

        # Overall summary
        self._maybe_generate_overall_graphs(all_results, "export")
        with open(os.path.join("export", "benchmark_results.json"), "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=4, default=str, allow_nan=False)

        self.stdout.write(self.style.SUCCESS("\nBenchmark complete! Results saved to export/"))

    # ------------------------------ helpers ---------------------------------
    def _reset_db(self):
        ScheduleEntry.objects.all().delete()
        Employee.objects.all().delete()
        Shift.objects.all().delete()
        Company.objects.all().delete()

    def _solution_signature(self, entries, prev_signature: str | None) -> Tuple[str, float]:
        tup = sorted((e.employee_id, e.date.isoformat(), e.shift_id) for e in entries)
        raw = json.dumps(tup, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        signature = hashlib.sha256(raw).hexdigest()
        prev_tup = getattr(self, "_prev_tup", None)
        if prev_signature is None or prev_tup is None:
            self._prev_tup = tup
            return signature, 0.0
        s1, s2 = set(prev_tup), set(tup)
        diff_pct = 100.0 * len(s1.symmetric_difference(s2)) / max(len(s1), len(s2)) if max(len(s1), len(s2)) else 0.0
        self._prev_tup = tup
        return signature, diff_pct

    def _clear_algorithm_company_entries(self, company, algorithm_name):
        deleted = ScheduleEntry.objects.filter(company=company, algorithm=algorithm_name).delete()[0]
        if deleted:
            self.stdout.write(f"Cleared {deleted} entries for {algorithm_name} at {company.name}")

    def _load_fixtures(self, employee_file: str, shift_file: str):
        with open(employee_file, "r", encoding="utf-8") as f:
            employees = json.load(f)
            for item in employees:
                fields = item["fields"]
                if "company" in fields:
                    fields["company"] = Company.objects.get(pk=fields["company"])
                Employee.objects.create(**fields)
        with open(shift_file, "r", encoding="utf-8") as f:
            shifts = json.load(f)
            for item in shifts:
                fields = item["fields"]
                if "company" in fields:
                    fields["company"] = Company.objects.get(pk=fields["company"])
                Shift.objects.create(**fields)

    def _load_company_fixtures(self, company_file: str):
        with open(company_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                fields = item["fields"]
                pk = item.get("pk")
                if pk is not None:
                    Company.objects.create(pk=pk, **fields)
                else:
                    Company.objects.create(**fields)

    def _create_problem(self, company) -> SchedulingProblem:
        emps_qs = Employee.objects.filter(company=company)
        employees = employees_to_core(emps_qs)
        shifts_qs = Shift.objects.filter(company=company)
        shifts = shifts_to_core(shifts_qs)
        return SchedulingProblem(
            employees=employees,
            shifts=shifts,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            company=company,
        )

    def _maybe_shuffle_problem(self, problem: SchedulingProblem, seed: int, scope: str) -> SchedulingProblem:
        import random
        rng = random.Random(seed)
        employees = list(problem.employees)
        shifts = list(problem.shifts)
        if scope in ("employees", "both"):
            rng.shuffle(employees)
        if scope in ("shifts", "both"):
            rng.shuffle(shifts)
        # Rebuild problem with same metadata but shuffled order
        return SchedulingProblem(
            employees=employees,
            shifts=shifts,
            start_date=problem.start_date,
            end_date=problem.end_date,
            company=problem.company,
        )

    @transaction.atomic
    def _save_entries(self, entries, algorithm_name: str):
        for entry in entries:
            employee = Employee.objects.get(id=entry.employee_id)
            ScheduleEntry.objects.create(
                employee_id=entry.employee_id,
                date=entry.date,
                shift_id=entry.shift_id,
                company=employee.company,
                algorithm=algorithm_name,
            )

    def _save_test_results(self, test_key: str, results: Dict[str, Any], export_dir: str) -> None:
        os.makedirs(export_dir, exist_ok=True)
        path = os.path.join(export_dir, f"{test_key}_results.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, default=str, allow_nan=False)

    # ------------------ KPI aggregation ---------------------------------
    def _calculate_comprehensive_kpis(self, company, algorithm_name) -> Dict[str, Any]:
        employees = list(Employee.objects.filter(company=company))
        start_date, end_date = date(2025, 1, 1), date(2025, 12, 31)

        kpi = KPICalculator(company)
        entries = ScheduleEntry.objects.filter(
            company=company, algorithm=algorithm_name, date__gte=start_date, date__lte=end_date
        )

        # Monthly rollups (aggregate values may be invariant across plans)
        monthly_stats: Dict[int, Dict[str, Any]] = {}
        for month in range(1, 13):
            month_start = date(2025, month, 1)
            month_end = date(2025, month, 28)
            while month_end.month == month:
                month_end += timedelta(days=1)
            month_end -= timedelta(days=1)

            company_analytics = kpi.calculate_company_analytics(entries, 2025, month, algorithm_name)

            # Contract buckets
            c32, c40 = [], []
            for emp in employees:
                emp_entries = [e for e in entries if (e.employee.id == emp.id and month_start <= e.date <= month_end)]
                emp_hours = sum(kpi.calculate_shift_hours_in_month(e.shift, e.date, month_start, month_end) for e in emp_entries)
                wh = getattr(emp, "max_hours_per_week", 0)
                if wh == 32:
                    c32.append(emp_hours)
                elif wh == 40:
                    c40.append(emp_hours)

            monthly_stats[month] = {
                "contract_32h_avg": statistics.mean(c32) if c32 else 0.0,
                "contract_40h_avg": statistics.mean(c40) if c40 else 0.0,
                "contract_32h_count": len(c32),
                "contract_40h_count": len(c40),
                "company_analytics": company_analytics,
            }

        coverage_stats = kpi.calculate_coverage_stats(entries, start_date, end_date)
        rest_details = kpi.check_rest_period_violations_detailed(entries, start_date, end_date)
        total_rest_violations = rest_details.get("total_violations", 0)

        # Per-employee fairness metrics (more plan-sensitive)
        employee_hours: List[float] = []
        util_32: List[float] = []
        util_40: List[float] = []
        overtime_list: List[float] = []

        entries_by_emp: Dict[int, List[Any]] = defaultdict(list)
        for e in entries:
            entries_by_emp[e.employee.id].append(e)
        for emp in employees:
            emp_entries = entries_by_emp.get(emp.id, [])
            actual = sum(kpi.calculate_shift_hours_in_range(e.shift, e.date, start_date, end_date) for e in emp_entries)
            employee_hours.append(actual)
            try:
                expected = kpi.calculate_expected_yearly_hours(emp, 2025)
            except Exception:
                expected = getattr(emp, "max_hours_per_week", 0) * 52
            util = (actual / expected) if expected > 0 else 0.0
            if getattr(emp, "max_hours_per_week", 0) == 32:
                util_32.append(util)
            elif getattr(emp, "max_hours_per_week", 0) == 40:
                util_40.append(util)
            overtime_list.append(max(actual - expected, 0.0))

        if employee_hours:
            hours_mean = statistics.mean(employee_hours)
            hours_stdev = statistics.stdev(employee_hours) if len(employee_hours) > 1 else 0.0
            hours_cv = (hours_stdev / hours_mean * 100) if hours_mean > 0 else 0.0
            gini = self._calculate_gini(employee_hours)
            sum_hours = sum(employee_hours)
            sum_sq_hours = sum(h*h for h in employee_hours)
            jain_index = (sum_hours * sum_hours) / (len(employee_hours) * sum_sq_hours) if sum_sq_hours > 0 else 0.0
            variance_hours = statistics.pvariance(employee_hours) if len(employee_hours) > 1 else 0.0
            gini_overtime = self._calculate_gini(overtime_list) if overtime_list else 0.0
        else:
            hours_mean = hours_stdev = hours_cv = gini = jain_index = variance_hours = gini_overtime = 0.0

        # Preference satisfaction (compare IDs)
        total_assigned = 0
        pref_matches = 0
        by_emp2: Dict[int, List[ScheduleEntry]] = defaultdict(list)
        for e in entries:
            by_emp2[e.employee.id].append(e)
        for emp in employees:
            preferred_ids = set(getattr(emp, "preferred_shifts", []))
            if not preferred_ids:
                continue
            emp_entries = by_emp2.get(emp.id, [])
            for e in emp_entries:
                if e.shift and e.shift.id in preferred_ids:
                    pref_matches += 1
            total_assigned += len(emp_entries)
        pref_satisfaction = (pref_matches / total_assigned * 100) if total_assigned else 0.0

        return {
            "monthly_stats": monthly_stats,
            "coverage_stats": coverage_stats,
            "constraint_violations": {
                "rest_period_violations": total_rest_violations,
                "total_violations": total_rest_violations,
                "rest_period_violations_detailed": rest_details,
            },
            "fairness_metrics": {
                "gini_coefficient": gini,
                "hours_std_dev": hours_stdev,
                "hours_cv": hours_cv,
                "min_hours": min(employee_hours) if employee_hours else 0.0,
                "max_hours": max(employee_hours) if employee_hours else 0.0,
                "avg_hours": hours_mean,
                "jain_index": jain_index,
                "gini_overtime": gini_overtime,
                "variance_hours": variance_hours,
            },
            "utilization": {
                "min": min(util_32 + util_40) if (util_32 or util_40) else 0.0,
                "max": max(util_32 + util_40) if (util_32 or util_40) else 0.0,
                "avg": statistics.mean(util_32 + util_40) if (util_32 or util_40) else 0.0,
                "by_contract": {
                    "32h": {
                        "min": min(util_32) if util_32 else 0.0,
                        "max": max(util_32) if util_32 else 0.0,
                        "avg": statistics.mean(util_32) if util_32 else 0.0,
                    },
                    "40h": {
                        "min": min(util_40) if util_40 else 0.0,
                        "max": max(util_40) if util_40 else 0.0,
                        "avg": statistics.mean(util_40) if util_40 else 0.0,
                    },
                },
            },
            "average_shift_utilization": (sum([s["coverage_percentage"] for s in coverage_stats]) / len(coverage_stats) / 100) if coverage_stats else 0.0,
            "preference_satisfaction_percent": pref_satisfaction,
        }

    # ---------- stats helpers ----------
    def _calculate_gini(self, values: List[float]) -> float:
        n = len(values)
        total = sum(values)
        if n <= 1 or total == 0:
            return 0.0
        sorted_values = sorted(values)
        cumsum = sum((i + 1) * v for i, v in enumerate(sorted_values))
        return (2 * cumsum) / (n * total) - (n + 1) / n

    def _calculate_statistics(self, values: List[float], confidence_level: float = 0.95) -> Dict[str, Any]:
        if not values:
            return {"mean": 0.0, "variance": 0.0, "std_dev": 0.0,
                    "confidence_interval": (0.0, 0.0), "min": 0.0, "max": 0.0, "count": 0}
        arr = np.array(values, dtype=float)
        mean = float(np.mean(arr))
        if len(arr) > 1:
            variance = float(np.var(arr, ddof=1))
            std_dev = float(np.std(arr, ddof=1))
            rel_thresh = max(abs(mean) * 1e-12, 1e-12)  # treat tiny noise as zero
            if variance < rel_thresh:
                variance = 0.0
                std_dev = 0.0
        else:
            variance = 0.0
            std_dev = 0.0
        if np.isnan(mean): mean = 0.0
        if np.isnan(variance): variance = 0.0
        if np.isnan(std_dev): std_dev = 0.0
        if len(arr) > 1 and variance > 0:
            try:
                sem = stats.sem(arr)
                if sem > 0:
                    lo, hi = stats.t.interval(confidence_level, len(arr) - 1, loc=mean, scale=sem)
                    ci = (float(lo), float(hi))
                    if np.isnan(ci[0]) or np.isnan(ci[1]):
                        ci = (mean, mean)
                else:
                    ci = (mean, mean)
            except Exception:
                ci = (mean, mean)
        else:
            ci = (mean, mean)
        return {"mean": mean, "variance": variance, "std_dev": std_dev,
                "confidence_interval": ci, "min": float(np.min(arr)), "max": float(np.max(arr)), "count": len(arr)}

    def _extract_numeric_values(self, src: Any, out: Dict[str, List[float]], prefix: str = "") -> None:
        if isinstance(src, dict):
            for k, v in src.items():
                key = f"{prefix}.{k}" if prefix else str(k)
                self._extract_numeric_values(v, out, key)
        elif isinstance(src, (list, tuple)):
            for i, v in enumerate(src):
                key = f"{prefix}[{i}]"
                self._extract_numeric_values(v, out, key)
        elif isinstance(src, (int, float)) and not (isinstance(src, float) and np.isnan(src)):
            out[prefix].append(float(src))

    def _calculate_kpi_statistics(self, kpi_list: List[Dict[str, Any]], confidence_level: float = 0.95) -> Dict[str, Any]:
        if not kpi_list:
            return {}
        flat: Dict[str, List[float]] = defaultdict(list)
        for kpis in kpi_list:
            if kpis:
                self._extract_numeric_values(kpis, flat)
        # Special handling: coverage stats are a list of dicts per shift -> compute per-shift stats
        coverage_key = "coverage_stats"
        if coverage_key in flat:
            flat.pop(coverage_key, None)
        return {metric: self._calculate_statistics(vals, confidence_level) for metric, vals in flat.items() if vals}

    # ----------------------- outputs / graphs -----------------------
    def _maybe_generate_case_graphs(self, test_key: str, results: Dict[str, Any], export_dir: str, company):
        if not EnhancedAnalytics:
            return
        try:
            # build a full analytics instance on the *current* DB snapshot
            all_entries = ScheduleEntry.objects.filter(company=company)
            employees = list(Employee.objects.filter(company=company))
            shifts = list(Shift.objects.filter(company=company))
            ea = EnhancedAnalytics(company, all_entries, employees, shifts)

            # Prefer the "all comparison" helper if present, else fall back
            if hasattr(ea, "generate_all_individual_comparison_graphs"):
                ea.generate_all_individual_comparison_graphs(results, export_dir, test_key)
            elif hasattr(ea, "generate_algorithm_comparison_graphs"):
                ea.generate_algorithm_comparison_graphs(results, export_dir, test_key)
            # Always try to include the monthly contract graph for context
            if hasattr(ea, "generate_monthly_hours_by_contract_graph"):
                ea.generate_monthly_hours_by_contract_graph(export_dir, test_key)
        except Exception as e:
            self.stdout.write(f"[warn] Analytics graph generation skipped: {e}")

    def _maybe_generate_overall_graphs(self, all_results: Dict[str, Any], export_dir: str):
        if not EnhancedAnalytics:
            return
        try:
            if hasattr(EnhancedAnalytics, "generate_comparison_graphs_across_test_cases"):
                EnhancedAnalytics.generate_comparison_graphs_across_test_cases(all_results, export_dir)
        except Exception as e:
            self.stdout.write(f"[warn] Overall comparison graph skipped: {e}")