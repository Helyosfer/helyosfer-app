"""Loan instalment calculation and repayment schedule."""

import unittest
from decimal import Decimal

from services.loan_service import calculate_loan


class LoanCalculationTest(unittest.TestCase):
    def test_the_instalment_matches_the_annuity_formula(self):
        result = calculate_loan(100000, 3.49, 12, include_taxes=False)
        rate = Decimal("0.0349")
        growth = (1 + rate) ** 12
        expected = (Decimal(100000) * rate * growth / (growth - 1)).quantize(Decimal("0.01"))
        self.assertEqual(Decimal(str(result["monthly_payment"])), expected)

    def test_taxes_raise_the_instalment(self):
        plain = calculate_loan(100000, 3.49, 12, include_taxes=False)
        taxed = calculate_loan(100000, 3.49, 12, include_taxes=True)
        self.assertGreater(taxed["monthly_payment"], plain["monthly_payment"])

    def test_the_total_is_the_rounded_instalment_times_the_count(self):
        result = calculate_loan(123456.78, 2.19, 37)
        self.assertEqual(
            Decimal(str(result["total_repayment"])),
            Decimal(str(result["monthly_payment"])) * 37,
        )
        self.assertAlmostEqual(
            result["total_cost"], result["total_repayment"] - 123456.78, places=2
        )

    def test_the_schedule_pays_the_loan_off_exactly(self):
        result = calculate_loan(100000, 3.49, 24)
        schedule = result["schedule"]
        self.assertEqual(len(schedule), 24)
        self.assertEqual(schedule[-1]["balance"], 0.0)
        self.assertAlmostEqual(sum(r["principal"] for r in schedule), 100000, delta=0.5)
        for earlier, later in zip(schedule, schedule[1:]):
            self.assertLess(later["balance"], earlier["balance"])
            self.assertGreater(later["principal"], earlier["principal"])

    def test_each_row_splits_the_instalment_into_principal_and_charges(self):
        for row in calculate_loan(50000, 4.0, 6)["schedule"]:
            self.assertAlmostEqual(
                row["principal"] + row["interest"], row["payment"], delta=0.02
            )

    def test_invalid_inputs_are_refused(self):
        for arguments in (
            (0, 3, 12), (-5, 3, 12), (1000, 0, 12), (1000, 3, 0),
            (1000, 3, 361), ("abc", 3, 12), (float("nan"), 3, 12),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    calculate_loan(*arguments)


if __name__ == "__main__":
    unittest.main()
