"""Deposit interest, compound growth, time to a goal, and the loan's detailed mode."""

import os
import tempfile
import unittest

from services.calculator_service import (
    DAILY, MONTHLY, compound_growth, deposit_interest, time_to_goal,
)
from services.loan_service import calculate_loan


class DepositInterestTest(unittest.TestCase):
    def test_interest_is_simple_and_taxed_at_five_percent(self):
        result = deposit_interest(100000, 45, 32)
        self.assertEqual(result["gross_interest"], 3945.21)
        self.assertEqual(result["tax"], 197.26)
        self.assertEqual(result["net_interest"], 3747.95)
        self.assertEqual(result["maturity_value"], 103747.95)

    def test_invalid_inputs_are_refused(self):
        for arguments in ((0, 45, 32), (1000, 0, 32), (1000, 45, 0), ("x", 45, 32)):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    deposit_interest(*arguments)


class CompoundGrowthTest(unittest.TestCase):
    def test_growth_without_contributions_is_plain_compounding(self):
        result = compound_growth(1000, 10, 2)
        self.assertEqual(result["series"], [1000.0, 1100.0, 1210.0])
        self.assertEqual(result["invested"], 1000.0)
        self.assertEqual(result["gain"], 210.0)

    def test_contributions_add_to_what_was_put_in_and_to_the_result(self):
        plain = compound_growth(50000, 30, 5)
        saving = compound_growth(50000, 30, 5, 2000)
        self.assertEqual(saving["invested"], 50000 + 2000 * 60)
        self.assertGreater(saving["final_value"], plain["final_value"] + 2000 * 60)
        self.assertEqual(len(saving["series"]), 6)

    def test_invalid_inputs_are_refused(self):
        for arguments in ((0, 10, 2), (1000, 0, 2), (1000, 10, 0), (1000, 10, 101),
                          (1000, 10, 2, -5)):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    compound_growth(*arguments)


class TimeToGoalTest(unittest.TestCase):
    def test_the_last_partial_deposit_still_counts_as_one(self):
        self.assertEqual(time_to_goal(1000, 300, MONTHLY)["deposits"], 4)
        self.assertEqual(time_to_goal(1000, 250, MONTHLY)["deposits"], 4)

    def test_daily_and_monthly_periods_give_days(self):
        self.assertEqual(time_to_goal(1000, 40, DAILY)["days"], 25)
        self.assertEqual(time_to_goal(60000, 5000, MONTHLY)["days"], 360)

    def test_money_already_saved_shortens_the_wait(self):
        self.assertEqual(time_to_goal(1000, 100, MONTHLY, already_saved=600)["deposits"], 4)
        self.assertEqual(time_to_goal(1000, 100, MONTHLY, already_saved=5000)["deposits"], 0)

    def test_invalid_inputs_are_refused(self):
        for arguments in ((0, 10), (100, 0), (100, 10, "weekly")):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    time_to_goal(*arguments)


class DetailedLoanTest(unittest.TestCase):
    def test_bank_fees_are_deducted_up_front_and_leave_the_instalment_alone(self):
        plain = calculate_loan(100000, 3.49, 24)
        detailed = calculate_loan(100000, 3.49, 24, bank_fees=True)
        self.assertEqual(detailed["monthly_payment"], plain["monthly_payment"])
        self.assertEqual(detailed["total_repayment"], plain["total_repayment"])
        self.assertEqual(
            {item["name"]: item["amount"] for item in detailed["upfront"]},
            {"allocation_fee": 575.0, "insurance": 800.0},
        )
        self.assertEqual(detailed["net_cash"], 98625.0)
        self.assertAlmostEqual(detailed["total_cost"], plain["total_cost"] + 1375.0, places=2)

    def test_a_spread_charge_appears_only_in_its_own_months(self):
        result = calculate_loan(
            100000, 3.49, 24,
            charges=[{"name": "Sigorta", "amount": 2400, "kind": "spread", "months": 12}],
        )
        self.assertEqual(result["schedule"][0]["extra"], 200.0)
        self.assertEqual(result["schedule"][11]["extra"], 200.0)
        self.assertEqual(result["schedule"][12]["extra"], 0.0)
        self.assertEqual(
            result["schedule"][0]["total"], round(result["monthly_payment"] + 200.0, 2)
        )
        self.assertEqual(result["spread_total"], 2400.0)
        self.assertEqual(result["net_cash"], 100000.0)

    def test_an_upfront_charge_reduces_the_cash_received(self):
        result = calculate_loan(
            100000, 3.49, 12,
            charges=[{"name": "Ekspertiz", "amount": 1500, "kind": "upfront"}],
        )
        self.assertEqual(result["net_cash"], 98500.0)
        self.assertTrue(all(row["extra"] == 0.0 for row in result["schedule"]))

    def test_each_kind_of_loan_has_its_longest_term(self):
        calculate_loan(100000, 3, 36, loan_kind="consumer")
        calculate_loan(100000, 3, 48, loan_kind="vehicle")
        calculate_loan(100000, 3, 120, loan_kind="housing")
        for kind, months in (("consumer", 37), ("vehicle", 49), ("housing", 121)):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    calculate_loan(100000, 3, months, loan_kind=kind)
        with self.assertRaises(ValueError):
            calculate_loan(100000, 3, 12, loan_kind="boat")

    def test_invalid_charges_are_refused(self):
        for charge in (
            {"name": "", "amount": 10, "kind": "upfront"},
            {"name": "x", "amount": 0, "kind": "upfront"},
            {"name": "x", "amount": 10, "kind": "weekly"},
            {"name": "x", "amount": 10, "kind": "spread", "months": 0},
        ):
            with self.subTest(charge=charge):
                with self.assertRaises(ValueError):
                    calculate_loan(1000, 3, 12, charges=[charge])


class LoanReportTest(unittest.TestCase):
    def test_the_schedule_is_written_as_a_pdf(self):
        from services.loan_report import write_loan_schedule_pdf

        result = calculate_loan(
            100000, 3.49, 24, bank_fees=True,
            charges=[{"name": "Ekspertiz ücreti", "amount": 1500, "kind": "upfront"}],
        )
        with tempfile.TemporaryDirectory() as folder:
            path = write_loan_schedule_pdf(
                os.path.join(folder, "plan.pdf"), result, principal=100000
            )
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(5), b"%PDF-")
            self.assertGreater(os.path.getsize(path), 1500)


if __name__ == "__main__":
    unittest.main()
