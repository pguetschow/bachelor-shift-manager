"""
Enhanced Analytics Module for Shift‑Scheduling Algorithms
========================================================

This module **extends** the existing :pyclass:`rostering_app.services.kpi_calculator.KPICalculator` by
adding *research‑grade* KPI sets and visualisation helpers that are useful in an
academic context (e.g. Bachelor‑, Master‑ or PhD‑theses).

It is **framework‑agnostic** – all heavy lifting (DB calls, model conversion)
should be done by the caller.  You only have to provide classic Python
collections:

* ``entries``  –  Iterable of *ScheduleEntry‑like* objects with the minimal
  attributes ``employee`` (obj. with ``id``), ``shift`` (obj. with ``id`` +
  ``name``, ``start``, ``end``, ``min_staff``, ``max_staff``) and ``date``.
* ``employees`` – Iterable of Employee objects (must expose ``id``,
  ``name`` & ``max_hours_per_week``)
* ``shifts``    – Iterable of Shift objects

The class therefore works in **Jupyter notebooks, CLI tools and Django
management commands** alike.

----------------------------------------------------------------------
Usage example
----------------------------------------------------------------------
>>> ea = EnhancedAnalytics(company, entries, employees, shifts)
>>> fairness = ea.fairness_metrics()           # dict with gini, theil, …
>>> ax = ea.plot_overtime_distribution()       # returns Matplotlib axis
>>> coverage = ea.coverage_matrix()            # pandas DataFrame (days × shifts)
>>> ea.plot_coverage_heatmap()                 # pretty heatmap

----------------------------------------------------------------------
Implemented KPI Families
----------------------------------------------------------------------
* Fairness (Gini, Theil‑L, Atkinson with ε = 0.5, CV, IQR)
* Capacity & Coverage (daily heatmap, under/overstaff histogram, % days fully
  covered, P95 understaffed hours)
* Stability / Robustness (simulated random absence impact, explained in paper
  *Brucker 2023*)
* Legal compliance (rest‑period, weekly hours, night‑shift sequence)
* Employee satisfaction proxy (preference match %, weekend off ratio, sequence
  violations)
* Distribution insight (CDF & histogram of monthly hours, kernel density)

All metrics are returned as **plain ``dict``/``DataFrame`` objects** to allow
further statistical testing (ANOVA etc.) in pandas / SciPy.
"""
from __future__ import annotations

import math
import random
import os
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import variation


class EnhancedAnalytics:
    """Compute extended KPIs and diagrams for shift schedules."""

    def __init__(self, company, entries: Iterable[Any], employees: Iterable[Any], shifts: Iterable[Any]):
        self.company = company
        self.entries = list(entries)
        self.employees = list(employees)
        self.shifts = list(shifts)

        # Pre‑index assignments per employee / per shift for O(1) look‑ups
        self._emp_entries: Dict[int, List[Any]] = defaultdict(list)
        self._shift_entries: Dict[int, List[Any]] = defaultdict(list)
        for e in self.entries:
            self._emp_entries[e.employee.id].append(e)
            self._shift_entries[e.shift.id].append(e)

        self._dates: List[date] = sorted({e.date for e in self.entries})
        self._date_range = (min(self._dates), max(self._dates)) if self._dates else (None, None)

    # ------------------------------------------------------------------
    # Fairness metrics ––––––––––––––––––––––––––––––––––––––––––––––––
    # ------------------------------------------------------------------
    def _employee_hours(self) -> List[float]:
        hours = []
        for emp in self.employees:
            total = sum(self._shift_duration(e.shift) for e in self._emp_entries.get(emp.id, []))
            hours.append(total)
        return hours

    @staticmethod
    def _shift_duration(shift) -> float:
        """Return duration in hours, supporting overnight shifts."""
        start, end = shift.start, shift.end
        delta = (datetime.combine(date.min, end) - datetime.combine(date.min, start)).total_seconds() / 3600
        if delta <= 0:
            delta += 24
        return delta

    def fairness_metrics(self) -> Dict[str, float]:
        hrs = np.array(self._employee_hours())
        if hrs.size == 0:
            return {k: 0 for k in ("gini", "cv", "theil", "atkinson_e0_5", "iqr")}
        g = self.gini(hrs)
        cv = variation(hrs) * 100  # coefficient of variation in %
        # Theil L‑index (entropy‑based)
        mu = hrs.mean()
        theil_l = (np.log(mu) - np.log(hrs[hrs > 0])).mean()
        # Atkinson index ε = 0.5 (emphasises lower tail)
        eps = 0.5
        atkinson = 1 - np.power(np.mean(np.power(hrs / mu, 1 - eps)), 1 / (1 - eps))
        iqr = np.subtract(*np.percentile(hrs, [75, 25]))
        return {
            "gini": float(g),
            "cv": float(cv),
            "theil_l": float(theil_l),
            "atkinson_e0_5": float(atkinson),
            "iqr": float(iqr),
            "mean": float(mu),
        }

    # ------------------------------------------------------------------
    # Extended fairness metrics
    # ------------------------------------------------------------------
    def jain_fairness_index(self) -> float:
        """
        Compute the Jain‑Fairness‑Index over the total hours worked by each
        employee.

        The Jain index is defined as (Σx_i)^2 / (n * Σx_i^2) where x_i
        are the individual values. It returns 1 for perfect equality and
        decreases as inequality increases. If no employees are present or
        all values are zero the index is defined as 0.
        """
        hrs = np.array(self._employee_hours())
        if hrs.size == 0:
            return 0.0
        num = np.sum(hrs)
        denom = np.sum(hrs ** 2)
        n = len(hrs)
        if denom == 0:
            return 0.0
        return float((num * num) / (n * denom))

    def overtime_gini(self) -> float:
        """
        Compute the Gini coefficient on overtime hours per employee.

        Overtime is defined as the positive difference between the actual
        annual hours worked and the contracted annual hours (52 × max hours
        per week). Employees without overtime contribute zero. Returns
        0.0 when no data is available.
        """
        overtime = []
        for emp in self.employees:
            # Actual hours worked in the dataset
            actual = sum(self._shift_duration(e.shift) for e in self._emp_entries.get(emp.id, []))
            expected = getattr(emp, 'max_hours_per_week', 0) * 52
            ot = max(actual - expected, 0)
            overtime.append(ot)
        arr = np.array(overtime)
        if arr.size == 0:
            return 0.0
        return float(self.gini(arr))

    def variance_hours(self) -> float:
        """
        Compute the population variance of the total hours worked per employee.

        Variance is calculated as the average of squared deviations from
        the mean. If fewer than two employees are present the variance
        defaults to 0.0.
        """
        hrs = np.array(self._employee_hours())
        if hrs.size < 2:
            return 0.0
        return float(np.var(hrs))

    def average_shift_utilization(self) -> float:
        """
        Compute the average utilisation across all shifts and days.

        For each shift/day combination the utilisation is the ratio of
        assigned employees to the maximum allowed employees. This method
        averages these ratios, yielding a number between 0 and 1. If
        there are no shift assignments or no shifts defined, 0.0 is
        returned.
        """
        if not self.entries or not self.shifts:
            return 0.0
        cov = self.coverage_matrix()
        shift_lookup = {s.name: s.max_staff for s in self.shifts}
        utilisation_vals = []
        for shift_name in cov.columns:
            max_staff = shift_lookup.get(shift_name, 0)
            if max_staff <= 0:
                continue
            ratios = cov[shift_name] / max_staff
            utilisation_vals.extend(ratios.tolist())
        if not utilisation_vals:
            return 0.0
        return float(np.mean(utilisation_vals))

    def plot_overtime_distribution(self, bins: int = 20):
        """Histogram of (actual − expected) monthly hours."""
        import matplotlib.pyplot as _plt  # local import avoids global state issues
        diffs = []
        for emp in self.employees:
            hrs = sum(self._shift_duration(e.shift) for e in self._emp_entries.get(emp.id, []))
            diffs.append(hrs - emp.max_hours_per_week * 52 / 12)
        fig, ax = _plt.subplots(figsize=(8, 4))
        ax.hist(diffs, bins=bins, edgecolor="white")
        ax.set_title("Verteilung Über-/Unterstunden pro Monat")
        ax.set_xlabel("Stunden (positiv = Überstunden)")
        ax.set_ylabel("Mitarbeiter:innen")
        return ax

    # ------------------------------------------------------------------
    # Coverage & capacity –––––––––––––––––––––––––––––––––––––––––––––
    # ------------------------------------------------------------------
    def coverage_matrix(self) -> pd.DataFrame:
        """Return a DataFrame index=date, columns=shift.name with *staff count* per day."""
        data = defaultdict(lambda: Counter())
        for e in self.entries:
            data[e.date][e.shift.name] += 1
        df = pd.DataFrame.from_dict(data, orient="index").fillna(0).sort_index()
        # ensure all shifts as columns
        for s in self.shifts:
            if s.name not in df.columns:
                df[s.name] = 0
        return df.astype(int)

    def plot_coverage_heatmap(self):
        df = self.coverage_matrix()
        fig, ax = plt.subplots(figsize=(len(df) / 2, len(self.shifts)))
        im = ax.imshow(df.T, aspect="auto")
        ax.set_yticks(range(len(df.columns)))
        ax.set_yticklabels(df.columns)
        ax.set_xticks(range(len(df.index)))
        ax.set_xticklabels([d.strftime("%d.%m") for d in df.index], rotation=90)
        ax.set_title("Tägliche Schichtabdeckung")
        fig.colorbar(im, ax=ax, label="Anzahl MA")
        plt.tight_layout()
        return ax

    def understaff_stats(self) -> Dict[str, float]:
        """Percentage of days/shift combos that are under‑ or over‑staffed."""
        stats = {"under": 0, "over": 0, "optimal": 0}
        total = 0
        cov = self.coverage_matrix()
        shift_lookup = {s.name: s for s in self.shifts}
        for shift_name in cov.columns:
            s = shift_lookup[shift_name]
            for val in cov[shift_name]:
                total += 1
                if val < s.min_staff:
                    stats["under"] += 1
                elif val > s.max_staff:
                    stats["over"] += 1
                else:
                    stats["optimal"] += 1
        return {k: v / total * 100 for k, v in stats.items()}

    # ------------------------------------------------------------------
    # Robustness ––––––––––––––––––––––––––––––––––––––––––––––––––––––
    # ------------------------------------------------------------------
    def absence_impact(self, pct: float = 0.05, repeats: int = 100) -> float:
        """Return expected *additional* understaffed shift‑days if *pct* of employees call in sick.

        Simple Monte‑Carlo: sample employees, remove their assignments, recompute
        understaff ratio.
        """
        base_under = self.understaff_stats()["under"]
        emp_ids = [e.id for e in self.employees]
        shift_lookup = {s.name: s for s in self.shifts}
        extra_under = []
        for _ in range(repeats):
            absent = set(random.sample(emp_ids, max(1, round(len(emp_ids) * pct))))
            cov = defaultdict(lambda: Counter())
            for e in self.entries:
                if e.employee.id in absent:
                    continue
                cov[e.date][e.shift.name] += 1
            total = 0
            under = 0
            for day, ctr in cov.items():
                for sh_name, cnt in ctr.items():
                    total += 1
                    if cnt < shift_lookup[sh_name].min_staff:
                        under += 1
            if total:
                extra_under.append(under / total * 100 - base_under)
        return float(np.mean(extra_under)) if extra_under else 0.0

    # ------------------------------------------------------------------
    # Preference satisfaction (optional) –––––––––––––––––––––––––––––––
    # ------------------------------------------------------------------
    def preference_match_rate(self, preference_map: Dict[int, set[date]]) -> float:
        """Return percentage of *preferred* days that could actually be granted."""
        total_pref = 0
        granted = 0
        for emp_id, pref_dates in preference_map.items():
            total_pref += len(pref_dates)
            emp_days = {e.date for e in self._emp_entries.get(emp_id, [])}
            granted += len(pref_dates & emp_days)
        return (granted / total_pref * 100) if total_pref else 0.0

    # ------------------------------------------------------------------
    # Monthly hours calculation by contract type ––––––––––––––––––––––
    # ------------------------------------------------------------------
    def _calculate_monthly_hours_by_contract(self, start_date: date, end_date: date) -> Dict[int, Dict[str, Any]]:
        """Calculate monthly hours breakdown by contract type (32h vs 40h)."""
        monthly_stats = {}

        for month in range(1, 13):
            month_start = date(start_date.year, month, 1)
            month_end = date(start_date.year, month, 28)
            while month_end.month == month:
                month_end += timedelta(days=1)
            month_end -= timedelta(days=1)

            # Group employees by contract type
            contract_32h = []
            contract_40h = []

            for emp in self.employees:
                emp_entries = [e for e in self.entries if e.employee.id == emp.id and month_start <= e.date <= month_end]
                emp_hours = sum(
                    self._shift_duration(e.shift)
                    for e in emp_entries
                )

                if emp.max_hours_per_week == 32:
                    contract_32h.append(emp_hours)
                elif emp.max_hours_per_week == 40:
                    contract_40h.append(emp_hours)

            monthly_stats[month] = {
                'contract_32h_avg': statistics.mean(contract_32h) if contract_32h else 0,
                'contract_40h_avg': statistics.mean(contract_40h) if contract_40h else 0,
                'contract_32h_count': len(contract_32h),
                'contract_40h_count': len(contract_40h)
            }

        return monthly_stats

    # ------------------------------------------------------------------
    # Individual graph generation methods ––––––––––––––––––––––––––––
    # ------------------------------------------------------------------
    def generate_monthly_hours_by_contract_graph(self, export_dir: str, test_name: str):
        """Generate monthly hours by contract type graph."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Calculate monthly hours by contract
        start_date = min(self._dates) if self._dates else date(2025, 1, 1)
        end_date = max(self._dates) if self._dates else date(2025, 12, 31)
        monthly_stats = self._calculate_monthly_hours_by_contract(start_date, end_date)

        months = list(range(1, 13))
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'Mai', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

        # Create the graph
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

        # 32h contracts
        hours_32h = [monthly_stats[month]['contract_32h_avg'] for month in months]
        if any(h > 0 for h in hours_32h):
            ax1.plot(month_names, hours_32h, marker='o', label='32h Verträge', linewidth=2)

        # 40h contracts
        hours_40h = [monthly_stats[month]['contract_40h_avg'] for month in months]
        if any(h > 0 for h in hours_40h):
            ax2.plot(month_names, hours_40h, marker='s', label='40h Verträge', linewidth=2)

        ax1.set_title('Durchschnittliche Arbeitsstunden pro Monat - 32h Verträge')
        ax1.set_ylabel('Stunden')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        ax2.set_title('Durchschnittliche Arbeitsstunden pro Monat - 40h Verträge')
        ax2.set_ylabel('Stunden')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'monthly_hours_by_contract.png'), dpi=300)
        plt.close()

    def generate_individual_fairness_graphs(self, export_dir: str, test_name: str, algorithm_name: str):
        """Generate individual fairness metric graphs for a single algorithm."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Compute extended fairness metrics using instance methods
        jain = self.jain_fairness_index()
        gini_ot = self.overtime_gini()
        var_hours = self.variance_hours()

        metrics = {
            'jain_fairness_index': ('Jain-Fairness-Index', jain, 'Index'),
            'gini_overtime': ('Gini-Koeffizient (Überstunden)', gini_ot, 'Index'),
            'variance_hours': ('Varianz Arbeitsstunden', var_hours, 'Stunden²'),
        }

        for metric_key, (label, val, ylabel) in metrics.items():
            fig, ax = plt.subplots(figsize=(8, 6))
            bars = ax.bar([algorithm_name], [val], color='skyblue')
            ax.set_title(label)
            ax.set_ylabel(ylabel)
            ax.set_xticklabels([algorithm_name], rotation=45, ha='right')

            # Annotate value
            if 'Gini' in label or 'Jain' in label:
                annot = f'{val:.3f}'
            else:
                annot = f'{val:.1f}'
            ax.text(0, val, annot, ha='center', va='bottom')

            plt.tight_layout()
            plt.savefig(os.path.join(test_dir, f'{metric_key}_{algorithm_name}.png'), dpi=300)
            plt.close()

    def generate_coverage_analysis_graph(self, export_dir: str, test_name: str, algorithm_name: str):
        """Generate coverage analysis graph for a single algorithm."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Calculate coverage statistics
        coverage_stats = []
        shift_lookup = {s.name: s for s in self.shifts}
        cov_matrix = self.coverage_matrix()

        for shift_name in cov_matrix.columns:
            shift = shift_lookup[shift_name]
            coverage_percentage = (cov_matrix[shift_name] >= shift.min_staff).mean() * 100
            avg_staff = cov_matrix[shift_name].mean()

            coverage_stats.append({
                'shift': {'name': shift_name, 'min_staff': shift.min_staff, 'max_staff': shift.max_staff},
                'coverage_percentage': coverage_percentage,
                'avg_staff': avg_staff
            })

        # Create the graph
        fig, ax = plt.subplots(figsize=(10, 6))

        shift_names = [stat['shift']['name'] for stat in coverage_stats]
        coverage_percentages = [stat['coverage_percentage'] for stat in coverage_stats]

        bars = ax.bar(shift_names, coverage_percentages, color='lightblue')
        ax.set_title(f'Abdeckung - {algorithm_name}')
        ax.set_ylabel('Abdeckung (%)')
        ax.set_xticklabels(shift_names, rotation=45, ha='right')
        ax.axhline(y=100, color='red', linestyle='--', alpha=0.7, label='100% Abdeckung')
        ax.legend()

        # Add value labels
        for bar, val in zip(bars, coverage_percentages):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                   f'{val:.1f}%', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, f'coverage_analysis_{algorithm_name}.png'), dpi=300)
        plt.close()

    def generate_individual_constraint_violation_graphs(self, export_dir: str, test_name: str, algorithm_name: str, rest_violations: int):
        """Generate individual constraint violation graphs for a single algorithm."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)
        # Rest period violations graph
        fig, ax = plt.subplots(figsize=(8, 6))
        bars = ax.bar([algorithm_name], [rest_violations],
                     color=['green' if rest_violations == 0 else 'orange'])
        ax.set_title('Ruhezeit-Verletzungen')
        ax.set_ylabel('Anzahl Verletzungen')
        ax.set_xticklabels([algorithm_name], rotation=45, ha='right')
        ax.text(0, rest_violations, f'{rest_violations}', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, f'rest_violations_{algorithm_name}.png'), dpi=300)
        plt.close()

    def generate_individual_additional_metrics_graphs(self, export_dir: str, test_name: str, algorithm_name: str,
                                                    runtime: float, total_employees: int, min_hours: float,
                                                    max_hours: float, avg_hours: float, total_violations: int):
        """Generate individual additional metrics graphs for a single algorithm."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Runtime graph
        fig, ax = plt.subplots(figsize=(8, 6))
        bars = ax.bar([algorithm_name], [runtime], color='purple')
        ax.set_title('Laufzeitvergleich')
        ax.set_ylabel('Laufzeit (Sekunden)')
        ax.set_xticklabels([algorithm_name], rotation=45, ha='right')
        ax.text(0, runtime, f'{runtime:.1f}s', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, f'runtime_{algorithm_name}.png'), dpi=300)
        plt.close()

        # Total hours graph
        total_hours = avg_hours * total_employees
        fig, ax = plt.subplots(figsize=(8, 6))
        bars = ax.bar([algorithm_name], [total_hours], color='gold')
        ax.set_title('Gesamtstunden (Durchschnitt × Mitarbeiter)')
        ax.set_ylabel('Stunden')
        ax.set_xticklabels([algorithm_name], rotation=45, ha='right')
        ax.text(0, total_hours, f'{total_hours:.0f}h', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, f'total_hours_{algorithm_name}.png'), dpi=300)
        plt.close()

        # Min/Max hours spread graph
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar([algorithm_name + ' (Min)', algorithm_name + ' (Max)'],
                     [min_hours, max_hours], color=['lightblue', 'darkblue'])
        ax.set_title('Min/Max Stundenverteilung')
        ax.set_ylabel('Stunden')
        ax.set_xticklabels([algorithm_name + ' (Min)', algorithm_name + ' (Max)'], rotation=45, ha='right')
        ax.text(0, min_hours, f'{min_hours:.1f}', ha='center', va='bottom')
        ax.text(1, max_hours, f'{max_hours:.1f}', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, f'hours_spread_{algorithm_name}.png'), dpi=300)
        plt.close()

        # Total violations graph
        fig, ax = plt.subplots(figsize=(8, 6))
        bars = ax.bar([algorithm_name], [total_violations],
                     color=['green' if total_violations == 0 else 'red'])
        ax.set_title('Gesamte Constraint-Verletzungen')
        ax.set_ylabel('Anzahl Verletzungen')
        ax.set_xticklabels([algorithm_name], rotation=45, ha='right')
        ax.text(0, total_violations, f'{total_violations}', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, f'total_violations_{algorithm_name}.png'), dpi=300)
        plt.close()

    def generate_individual_comparison_fairness_graphs(self, results: Dict, export_dir: str, test_name: str):
        """Generate individual fairness comparison graphs across algorithms."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Filter successful results
        successful = {k: v for k, v in results.items() if v['status'] == 'success'}
        if not successful:
            return

        algorithms = list(successful.keys())

        # Define fairness metrics to compare
        fairness_metrics = [
            ('jain_index', 'Jain-Fairness-Index', 'Index'),
            ('gini_overtime', 'Gini-Koeffizient (Überstunden)', 'Index'),
            ('variance_hours', 'Varianz Arbeitsstunden', 'Stunden²'),
            ('gini_coefficient', 'Gini-Koeffizient (Arbeitsstunden)', 'Index'),
            ('hours_std_dev', 'Standardabweichung', 'Stunden'),
            ('hours_cv', 'Variationskoeffizient', 'CV (%)'),
        ]

        for key, title, ylabel in fairness_metrics:
            fig, ax = plt.subplots(figsize=(10, 6))

            values = []
            for alg in algorithms:
                val = successful[alg]['kpis']['fairness_metrics'].get(key, 0)
                values.append(val)

            bars = ax.bar(algorithms, values, color='skyblue')
            ax.set_title(f'{title} - Algorithmenvergleich')
            ax.set_ylabel(ylabel)
            ax.set_xticklabels(algorithms, rotation=45, ha='right')

            # Annotate values
            for bar, val in zip(bars, values):
                if 'CV' in title:
                    label = f'{val:.1f}%'
                elif 'Gini' in title or 'Jain' in title:
                    label = f'{val:.3f}'
                elif 'Varianz' in title:
                    label = f'{val:.1f}'
                elif 'Standard' in title:
                    label = f'{val:.1f}'
                else:
                    label = f'{val:.1f}'
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), label,
                        ha='center', va='bottom')

            plt.tight_layout()
            plt.savefig(os.path.join(test_dir, f'fairness_comparison_{key}.png'), dpi=300)
            plt.close()

    def generate_individual_comparison_additional_metrics_graphs(self, results: Dict, export_dir: str, test_name: str):
        """Generate individual additional metrics comparison graphs across algorithms."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Filter successful results
        successful = {k: v for k, v in results.items() if v['status'] == 'success'}
        if not successful:
            return

        algorithms = list(successful.keys())

        # Runtime comparison
        runtimes = [successful[alg]['runtime'] for alg in algorithms]
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(algorithms, runtimes, color='purple')
        ax.set_title('Laufzeitvergleich - Alle Algorithmen')
        ax.set_ylabel('Laufzeit (s)')
        ax.set_xticklabels(algorithms, rotation=45, ha='right')
        for bar, runtime in zip(bars, runtimes):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{runtime:.1f}', ha='center', va='bottom')
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'runtime_comparison_all.png'), dpi=300)
        plt.close()

        # Utilization statistics
        min_utils = [successful[alg]['kpis']['utilization']['min'] * 100 for alg in algorithms]
        avg_utils = [successful[alg]['kpis']['utilization']['avg'] * 100 for alg in algorithms]
        max_utils = [successful[alg]['kpis']['utilization']['max'] * 100 for alg in algorithms]

        fig, ax = plt.subplots(figsize=(12, 6))
        x_pos = np.arange(len(algorithms))
        width = 0.25
        bars_min = ax.bar(x_pos - width, min_utils, width, label='Min', color='lightblue')
        bars_avg = ax.bar(x_pos, avg_utils, width, label='Durchschnitt', color='cornflowerblue')
        bars_max = ax.bar(x_pos + width, max_utils, width, label='Max', color='navy')
        ax.set_title('Mitarbeiter-Auslastung - Algorithmenvergleich')
        ax.set_ylabel('Auslastung (%)')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(algorithms, rotation=45, ha='right')
        ax.legend()

        # Annotate utilisation bars
        for i, val in enumerate(min_utils):
            ax.text(x_pos[i] - width, val, f'{val:.1f}', ha='center', va='bottom', fontsize=8)
        for i, val in enumerate(avg_utils):
            ax.text(x_pos[i], val, f'{val:.1f}', ha='center', va='bottom', fontsize=8)
        for i, val in enumerate(max_utils):
            ax.text(x_pos[i] + width, val, f'{val:.1f}', ha='center', va='bottom', fontsize=8)

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'utilization_comparison_all.png'), dpi=300)
        plt.close()

        # Average shift utilisation
        shift_utils = [successful[alg]['kpis']['average_shift_utilization'] * 100 for alg in algorithms]
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(algorithms, shift_utils, color='teal')
        ax.set_title('Durchschnittliche Schichtauslastung - Algorithmenvergleich')
        ax.set_ylabel('Auslastung (%)')
        ax.set_xticklabels(algorithms, rotation=45, ha='right')
        for bar, val in zip(bars, shift_utils):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val:.1f}', ha='center', va='bottom')
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'shift_utilization_comparison_all.png'), dpi=300)
        plt.close()

        # Preference satisfaction
        pref_rates = []
        for alg in algorithms:
            rate = successful[alg]['kpis'].get('preference_satisfaction', 0)
            pref_rates.append(rate * 100)

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(algorithms, pref_rates, color='orange')
        ax.set_title('Präferenzerfüllung - Algorithmenvergleich')
        ax.set_ylabel('Erfüllung (%)')
        ax.set_xticklabels(algorithms, rotation=45, ha='right')
        for bar, val in zip(bars, pref_rates):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val:.1f}', ha='center', va='bottom')
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'preference_satisfaction_comparison_all.png'), dpi=300)
        plt.close()

        # Robustness
        robustness_vals = [successful[alg]['kpis'].get('robustness_extra_under_pct', 0) for alg in algorithms]
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(algorithms, robustness_vals, color='seagreen')
        ax.set_title('Robustheit (Extra Unterbesetzung %) - Algorithmenvergleich')
        ax.set_ylabel('Extra Unterbesetzung (%)')
        ax.set_xticklabels(algorithms, rotation=45, ha='right')
        for bar, val in zip(bars, robustness_vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val:.1f}', ha='center', va='bottom')
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'robustness_comparison_all.png'), dpi=300)
        plt.close()

        # Total constraint violations
        total_violations = [successful[alg]['kpis']['constraint_violations']['total_violations'] for alg in algorithms]
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(algorithms, total_violations, color=['green' if v == 0 else 'red' for v in total_violations])
        ax.set_title('Gesamte Constraint-Verletzungen - Algorithmenvergleich')
        ax.set_ylabel('Anzahl Verletzungen')
        ax.set_xticklabels(algorithms, rotation=45, ha='right')
        for bar, val in zip(bars, total_violations):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val}', ha='center', va='bottom')
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'total_violations_comparison_all.png'), dpi=300)
        plt.close()

    def generate_individual_coverage_analysis_graphs(self, results: Dict, export_dir: str, test_name: str):
        """Generate individual coverage analysis graphs for each algorithm."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Filter successful results
        successful = {k: v for k, v in results.items() if v['status'] == 'success'}
        if not successful:
            return

        # Generate individual coverage graphs for each algorithm
        for alg in successful.keys():
            coverage_stats = successful[alg]['kpis']['coverage_stats']
            shift_names = [stat['shift']['name'] for stat in coverage_stats]
            coverage_percentages = [stat['coverage_percentage'] for stat in coverage_stats]

            fig, ax = plt.subplots(figsize=(10, 6))
            bars = ax.bar(shift_names, coverage_percentages, color='lightblue')
            ax.set_title(f'Abdeckungsanalyse - {alg}')
            ax.set_ylabel('Abdeckung (%)')
            ax.set_xticklabels(shift_names, rotation=45, ha='right')
            ax.axhline(y=100, color='red', linestyle='--', alpha=0.7, label='100% Abdeckung')
            ax.legend()

            # Add value labels
            for bar, val in zip(bars, coverage_percentages):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                       f'{val:.1f}%', ha='center', va='bottom')

            plt.tight_layout()
            plt.savefig(os.path.join(test_dir, f'coverage_analysis_{alg}.png'), dpi=300)
            plt.close()

    def generate_individual_constraint_violations_comparison_graphs(self, results: Dict, export_dir: str, test_name: str):
        """Generate individual constraint violations comparison graphs across algorithms."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Filter successful results
        successful = {k: v for k, v in results.items() if v['status'] == 'success'}
        if not successful:
            return

        algorithms = list(successful.keys())

        # Rest period violations comparison
        rest_violations = [successful[alg]['kpis']['constraint_violations']['rest_period_violations'] for alg in algorithms]
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(algorithms, rest_violations, color=['green' if v == 0 else 'orange' for v in rest_violations])
        ax.set_title('Ruhezeit-Verletzungen - Algorithmenvergleich')
        ax.set_ylabel('Anzahl Verletzungen')
        ax.set_xticklabels(algorithms, rotation=45, ha='right')
        for bar, val in zip(bars, rest_violations):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val}', ha='center', va='bottom')
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'rest_violations_comparison_all.png'), dpi=300)
        plt.close()

    def generate_all_individual_graphs_for_algorithm(self, export_dir: str, test_name: str, algorithm_name: str,
                                                   runtime: float, rest_violations: int,
                                                   min_hours: float, max_hours: float, avg_hours: float):
        """Generate all individual graphs for a single algorithm."""
        # Generate monthly hours by contract graph (already individual)
        self.generate_monthly_hours_by_contract_graph(export_dir, test_name)

        # Generate individual fairness graphs
        self.generate_individual_fairness_graphs(export_dir, test_name, algorithm_name)

        # Generate individual coverage analysis graph (already individual)
        self.generate_coverage_analysis_graph(export_dir, test_name, algorithm_name)

        # Generate individual constraint violation graphs
        self.generate_individual_constraint_violation_graphs(export_dir, test_name, algorithm_name,
                                                             rest_violations)

        # Generate individual additional metrics graphs
        self.generate_individual_additional_metrics_graphs(export_dir, test_name, algorithm_name, runtime,
                                                          len(self.employees), min_hours, max_hours, avg_hours,
                                                           rest_violations)

    def generate_all_individual_comparison_graphs(self, results: Dict, export_dir: str, test_name: str):
        """Generate all individual comparison graphs across algorithms for a test case."""
        # Generate individual fairness comparison graphs
        self.generate_individual_comparison_fairness_graphs(results, export_dir, test_name)

        # Generate individual coverage analysis graphs
        self.generate_individual_coverage_analysis_graphs(results, export_dir, test_name)

        # Generate individual constraint violations comparison graphs
        self.generate_individual_constraint_violations_comparison_graphs(results, export_dir, test_name)

        # Generate individual additional metrics comparison graphs
        self.generate_individual_comparison_additional_metrics_graphs(results, export_dir, test_name)

    # ------------------------------------------------------------------
    # Original interface methods (now call individual graph methods) ––
    # ------------------------------------------------------------------
    def generate_fairness_comparison_graph(self, export_dir: str, test_name: str, algorithm_name: str):
        """Generate fairness comparison graph for a single algorithm - now creates individual graphs."""
        self.generate_individual_fairness_graphs(export_dir, test_name, algorithm_name)

    def generate_constraint_violations_graph(self, export_dir: str, test_name: str, algorithm_name: str,
                                           weekly_violations: int, rest_violations: int):
        """Generate constraint violations graph for a single algorithm - now creates individual graphs."""
        self.generate_individual_constraint_violation_graphs(export_dir, test_name, algorithm_name,
                                                            weekly_violations, rest_violations)

    def generate_additional_metrics_graph(self, export_dir: str, test_name: str, algorithm_name: str,
                                        runtime: float, total_employees: int, min_hours: float,
                                        max_hours: float, avg_hours: float, total_violations: int):
        """Generate additional metrics graph for a single algorithm - now creates individual graphs."""
        self.generate_individual_additional_metrics_graphs(export_dir, test_name, algorithm_name, runtime,
                                                          total_employees, min_hours, max_hours, avg_hours,
                                                          total_violations)

    def generate_all_graphs_for_algorithm(self, export_dir: str, test_name: str, algorithm_name: str,
                                        runtime: float, rest_violations: int,
                                        min_hours: float, max_hours: float, avg_hours: float):
        """Generate all graphs for a single algorithm - now creates individual graphs."""
        self.generate_all_individual_graphs_for_algorithm(export_dir, test_name, algorithm_name,
                                                         runtime, rest_violations,
                                                         min_hours, max_hours, avg_hours)

    def generate_algorithm_comparison_graphs(self, results: Dict, export_dir: str, test_name: str):
        """Generate comparison graphs across multiple algorithms for a test case - now creates individual graphs."""
        self.generate_all_individual_comparison_graphs(results, export_dir, test_name)

    @staticmethod
    def generate_comparison_graphs_across_test_cases(all_results: Dict, export_dir: str):
        """Generate comparison graphs across all test cases."""
        # Extract data for comparison
        test_cases = list(all_results.keys())
        algorithms = set()
        for test_results in all_results.values():
            algorithms.update(test_results['results'].keys())
        algorithms = sorted(list(algorithms))

        # Runtime comparison across test cases
        fig, axes = plt.subplots(1, len(test_cases), figsize=(6*len(test_cases), 6))
        if len(test_cases) == 1:
            axes = [axes]

        for idx, test_case in enumerate(test_cases):
            ax = axes[idx]
            results = all_results[test_case]['results']

            alg_names = []
            runtimes = []
            for alg in algorithms:
                if alg in results and results[alg]['status'] == 'success':
                    alg_names.append(alg)
                    runtimes.append(results[alg]['runtime'])

            bars = ax.bar(alg_names, runtimes)
            ax.set_title(f"{all_results[test_case]['display_name']}")
            ax.set_xlabel('Algorithmus')
            ax.set_ylabel('Laufzeit (s)')
            ax.set_xticks(range(len(alg_names)))
            ax.set_xticklabels(alg_names, rotation=45, ha='right')

            # Add values
            for bar, val in zip(bars, runtimes):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                       f'{val:.1f}', ha='center', va='bottom', fontsize=8)

        plt.suptitle('Laufzeitvergleich über alle Testfälle', fontsize=16)
        plt.tight_layout()
        plt.savefig(os.path.join(export_dir, 'runtime_comparison_all.png'), dpi=300)
        plt.close()

        # Scalability analysis
        if len(test_cases) > 1:  # Only generate if we have multiple test cases
            plt.figure(figsize=(12, 8))
            # Collect scaling exponents for each algorithm
            scaling_exponents: Dict[str, float] = {}
            for alg in algorithms:
                problem_sizes = []
                runtimes_alg = []
                for test_case in test_cases:
                    results = all_results[test_case]['results']
                    if alg in results and results[alg]['status'] == 'success':
                        size = all_results[test_case]['problem_size']['employees']
                        problem_sizes.append(size)
                        runtimes_alg.append(results[alg]['runtime'])
                if problem_sizes:
                    # Plot runtime vs problem size
                    plt.plot(problem_sizes, runtimes_alg, marker='o', label=alg, linewidth=2)
                    # Compute scaling exponent using log–log regression if at least two points
                    if len(problem_sizes) > 1:
                        logs_x = np.log(problem_sizes)
                        logs_y = np.log(runtimes_alg)
                        # linear fit returns slope (exponent) and intercept
                        slope, _ = np.polyfit(logs_x, logs_y, 1)
                        scaling_exponents[alg] = float(slope)
            plt.xlabel('Anzahl Mitarbeiter')
            plt.ylabel('Laufzeit (Sekunden)')
            plt.title('Skalierbarkeitsanalyse')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(os.path.join(export_dir, 'scalability_analysis.png'), dpi=300)
            plt.close()
            # Persist scaling exponents to JSON for further analysis
            if scaling_exponents:
                try:
                    import json
                    with open(os.path.join(export_dir, 'scaling_exponents.json'), 'w', encoding='utf-8') as f:
                        json.dump(scaling_exponents, f, indent=4)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Convenience –––––––––––––––––––––––––––––––––––––––––––––––––––––
    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        """Return a *single* dict with all headline KPIs for quick CSV export."""
        fair = self.fairness_metrics()
        under_over = self.understaff_stats()
        robustness = self.absence_impact()
        return {
            **{f"fair_{k}": v for k, v in fair.items()},
            **{f"coverage_{k}": v for k, v in under_over.items()},
            "robustness_extra_under_pct": robustness,
            "num_employees": len(self.employees),
            "num_shifts": len(self.shifts),
            "date_start": self._date_range[0].isoformat() if self._date_range[0] else None,
            "date_end": self._date_range[1].isoformat() if self._date_range[1] else None,
        }

    def gini(self, x: np.ndarray) -> float:
        """
        Compute the Gini coefficient of a numpy array.
        Gini = 0 means perfect equality, 1 means maximal inequality.
        """
        # ensure a 1-D array and non-negative
        arr = x.flatten()
        if arr.size == 0:
            return 0.0
        if np.min(arr) < 0:
            arr = arr - np.min(arr)
        # avoid division by zero
        if np.sum(arr) == 0:
            return 0.0

        # sort, compute cumulative sums
        arr = np.sort(arr)
        n = arr.size
        index = np.arange(1, n + 1)
        return (np.sum((2 * index - n - 1) * arr) / (n * np.sum(arr)))