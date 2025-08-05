import math
import os
from collections import defaultdict
from datetime import timedelta, date
from typing import List, Set, Tuple

from pulp import (
    LpProblem,
    LpVariable,
    lpSum,
    LpMinimize,
    LpBinary,
    PULP_CBC_CMD,
    LpStatus,
)

# --- KPI Calculator ----------------------------------------------------------
from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import is_non_working_day
from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry


class ILPScheduler(SchedulingAlgorithm):
    # ------------------------------------------------------------------
    # Construction / meta
    # ------------------------------------------------------------------
    def __init__(
            self,
            *,
            sundays_off: bool = False,
            min_util_factor: float = 0.9,
            monthly_ot_cap: float = 0.05,
            yearly_ot_cap: float = 0.00,
    ):
        self.sundays_off = sundays_off
        self.MIN_UTIL_FACTOR = min_util_factor
        self.MONTHLY_OT_CAP = monthly_ot_cap
        self.YEARLY_OT_CAP = yearly_ot_cap
        self.holidays: Set[Tuple[int, int, int]] = set()
        self.company = None  # injected in ``solve``

    @property
    def name(self) -> str:
        return "Integer Linear Programming"

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def solve(self, problem: SchedulingProblem) -> Tuple[str, List[ScheduleEntry]]:
        self.company = problem.company
        self.problem = problem
        kpi_calc = KPICalculator(self.company)

        # 1) Plan‑Zeitraster (nur echte Arbeitstage)
        dates: List[date] = []
        current = problem.start_date
        while current <= problem.end_date:
            if not is_non_working_day(current, self.company):
                dates.append(current)
            current += timedelta(days=1)

        # 2) Monat‑Buckets für spätere Constraints
        months = defaultdict(list)
        for d in dates:
            months[(d.year, d.month)].append(d)

        # ------------------------------------------------------------------
        # Entscheidungsvariablen
        # ------------------------------------------------------------------
        feasible = [
            (emp.id, d, sh.id)
            for emp in problem.employees
            for d in dates
            if not kpi_calc.is_date_blocked(emp, d)
            for sh in problem.shifts
        ]

        x = {
            (eid, d, sid): LpVariable(f"x_{eid}_{d}_{sid}", cat=LpBinary)
            for (eid, d, sid) in feasible
        }

        # OT/UT Slacks je Mitarbeiter‑Monat
        ot, ut, mu_def = {}, {}, {}
        for emp in problem.employees:
            for ym in months:
                exp = kpi_calc.calculate_expected_month_hours(emp, *ym, self.company)
                max_ot = 8 * math.floor(exp * self.MONTHLY_OT_CAP / 8)
                ot[(emp.id, ym)] = LpVariable(f"ot_{emp.id}_{ym}", 0, max_ot)
                ut[(emp.id, ym)] = LpVariable(f"ut_{emp.id}_{ym}", 0)
                mu_def[(emp.id, ym)] = LpVariable(f"mu_{emp.id}_{ym}", 0)

        # Gesamtsumme je Mitarbeiter (für Jahres‑Cap)
        tot_hours = {emp.id: LpVariable(f"tot_{emp.id}", 0) for emp in problem.employees}

        # ------------------------------------------------------------------
        # Zusätzliche Variablen für Fairness (Verhältnis möglich vs. geplant)
        # ------------------------------------------------------------------
        # Ermittel die maximal möglichen Arbeitsstunden je Mitarbeiter im Planungshorizont.
        shift_by_id = {sh.id: sh for sh in problem.shifts}
        possible_hours = defaultdict(int)  # konstante Werte, kein LpVariable nötig
        for eid, d, sid in feasible:
            possible_hours[eid] += shift_by_id[sid].duration

        # min‑ und max‑Utilisation (als kontinuierliche Variablen 0‑1) über alle MA
        alpha_min = LpVariable("alpha_min", 0, 1)
        alpha_max = LpVariable("alpha_max", 0, 1)

        # ------------------------------------------------------------------
        # Zielfunktion
        # ------------------------------------------------------------------
        W_OVER = 10_000_000
        W_UNDER = 1_000_000
        W_OPTDEV = 100_000
        W_OT = 50_000
        W_UT = 25_000
        W_MU_FAIR = 50_000
        W_FAIR_RATIO = 75_000  # NEU: Gewicht für Fairness (möglich vs. geplant)
        W_PREF = -5
        W_UTIL = -50

        model = LpProblem("EmployeeScheduling", LpMinimize)
        obj = 0

        # Coverage‑Penalties
        for d in dates:
            for sh in problem.shifts:
                under = LpVariable(f"u_{d}_{sh.id}", 0)
                over = LpVariable(f"o_{d}_{sh.id}", 0)
                covered = lpSum(
                    x[(e.id, d, sh.id)]
                    for e in problem.employees
                    if (e.id, d, sh.id) in x
                )
                model += covered + under >= sh.min_staff
                model += covered - over <= sh.max_staff
                obj += W_UNDER * under + W_OVER * over

                optimal_staff = (sh.min_staff + sh.max_staff) / 2
                dev = LpVariable(f"dev_{d}_{sh.id}", 0)
                model += covered - optimal_staff <= dev
                model += optimal_staff - covered <= dev
                obj += W_OPTDEV * dev

        # Mitarbeiter‑Term + Präferenzen
        for emp in problem.employees:
            yearly_cap = kpi_calc.calculate_expected_yearly_hours(
                emp, self.problem.start_date.year
            )
            obj += W_UTIL * (1 - tot_hours[emp.id] / yearly_cap)

            prefs = set(getattr(emp, "preferred_shifts", []))
            if prefs:
                obj += W_PREF * lpSum(
                    x[(emp.id, d, sh.id)]
                    for d in dates
                    for sh in problem.shifts
                    if sh.name in prefs and (emp.id, d, sh.id) in x
                )

            for ym in months:
                obj += (
                        W_OT * ot[(emp.id, ym)]
                        + W_UT * ut[(emp.id, ym)]
                        + W_MU_FAIR * mu_def[(emp.id, ym)]
                )

        # Fairness‑Ziel: Unterschied zwischen höchster und niedrigster Auslastung minimieren
        obj += W_FAIR_RATIO * (alpha_max - alpha_min)

        model += obj

        # ------------------------------------------------------------------
        # Constraints
        # ------------------------------------------------------------------
        # 1) max 1 Schicht pro Tag
        for emp in problem.employees:
            for d in dates:
                model += (
                        lpSum(
                            x[(emp.id, d, sh.id)]
                            for sh in problem.shifts
                            if (emp.id, d, sh.id) in x
                        )
                        <= 1
                )

        # 2) 11‑h Ruhezeit
        for emp in problem.employees:
            for i in range(len(dates) - 1):
                d1, d2 = dates[i], dates[i + 1]
                for s1 in problem.shifts:
                    for s2 in problem.shifts:
                        if (emp.id, d1, s1.id) in x and (emp.id, d2, s2.id) in x:
                            if kpi_calc.violates_rest_period(s1, s2, d1):
                                model += x[(emp.id, d1, s1.id)] + x[(emp.id, d2, s2.id)] <= 1

        # 3) Monats‑Gleichung / OT‑Cap / Unterdeckung
        for emp in problem.employees:
            for ym, mdates in months.items():
                exp = kpi_calc.calculate_expected_month_hours(emp, *ym, self.company)
                worked = lpSum(
                    x[(emp.id, d, sh.id)] * sh.duration
                    for d in mdates
                    for sh in problem.shifts
                    if (emp.id, d, sh.id) in x
                )
                model += worked == exp - ut[(emp.id, ym)] + ot[(emp.id, ym)]
                model += worked + mu_def[(emp.id, ym)] >= exp * self.MIN_UTIL_FACTOR
                model += worked <= exp * (1 + self.MONTHLY_OT_CAP)  # hartes Obere‑Cap

        # 4) Jahres‑Cap
        for emp in problem.employees:
            model += tot_hours[emp.id] == lpSum(
                x[(emp.id, d, sh.id)] * sh.duration
                for d in dates
                for sh in problem.shifts
                if (emp.id, d, sh.id) in x
            )
            yearly_cap = kpi_calc.calculate_expected_yearly_hours(
                emp, self.problem.start_date.year
            )
            model += tot_hours[emp.id] <= yearly_cap  # no yearly OT
            model += tot_hours[emp.id] >= yearly_cap * 0.85  # Minimum Auslastung 85 %

        # 5) Fairness‑Constraint (möglich vs. geplant)
        for emp in problem.employees:
            ph = possible_hours[emp.id]
            if ph > 0:  # Safety: überspringe MA ohne verfügbare Stunden
                model += tot_hours[emp.id] >= alpha_min * ph
                model += tot_hours[emp.id] <= alpha_max * ph

        # ------------------------------------------------------------------
        # Lösen & Ergebnis extrahieren
        # ------------------------------------------------------------------
        num_threads = max(1, os.cpu_count() - 2)
        if problem.company.name == 'Großes Unternehmen':
            # accept a small optimality gap of 1% in order to prevent hour long runtimes
            print("Use relative Gap of 1% for Großes Unternehmen")
            status = model.solve(PULP_CBC_CMD(msg=False, timeLimit=3600, threads=num_threads, presolve=True, gapRel=0.005))
        else:

            print(f"Use no relative Gap for {problem.company}")
            status = model.solve(PULP_CBC_CMD(msg=False, timeLimit=3600, threads=num_threads))
        if LpStatus[status] != 'Optimal':
            print(f"[ILP DEBUG] Status: {LpStatus[status]}")


        schedule = [
            ScheduleEntry(eid, d, sid)
            for (eid, d, sid), var in x.items()
            if var.varValue and var.varValue > 0.5
        ]
        return schedule
