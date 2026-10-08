import unittest
from datetime import date
from decimal import Decimal
from castle_income import parse_payment, ims_cells, plausible_lag

def serial(d): return (d - date(1899, 12, 30)).days

BODY = ("Gusto\nInpatient Medicine Services, LLC\nYou've been paid, James Day!\n## Check amount ##\n## Paid on ##\n"
        "$1,750.00\n\n09/25/2026\n\nFlat payment\n\n## $1,750.00 ##\n")
SUBJECT = "🎉 Hey James Day, you've been paid (09/25/2026)"
HEADER = ['Month', 'Pay period', 'GRMC pay-period end', 'GRMC income', 'Confirmed?', 'IMS pay-period end', 'IMS income', 'Confirmed?', 'Total income']

def sheet():
    return [['2026 1099 Income Goal Tracker'], [], HEADER,
            ['AUGUST', 17, serial(date(2026, 8, 22)), 3500, 'Y', serial(date(2026, 8, 31)), 3500, 'Y'],
            ['SEPTEMBER', 18, serial(date(2026, 9, 5)), 3500, 'Y', serial(date(2026, 9, 15))],
            ['', 19, serial(date(2026, 9, 19)), 3675, 'N', serial(date(2026, 9, 30))]]

class ParseTests(unittest.TestCase):
    def test_parses_gusto_email(self):
        self.assertEqual(parse_payment(SUBJECT, BODY), (date(2026, 9, 25), Decimal('1750.00')))

    def test_rejects_other_employer(self):
        with self.assertRaises(ValueError): parse_payment(SUBJECT, BODY.replace('Inpatient Medicine Services', 'Other Co'))

    def test_rejects_conflicting_amounts(self):
        with self.assertRaises(ValueError): parse_payment(SUBJECT, BODY.replace('## $1,750.00 ##', '').replace('$1,750.00', '$1,750.00 $900.00'))

class RowTests(unittest.TestCase):
    def test_latest_period_before_pay_date(self):
        row, inc, conf, end, income, _ = ims_cells(sheet(), date(2026, 9, 25))
        self.assertEqual((row, inc, conf, end, income), (5, 6, 7, date(2026, 9, 15), ''))

    def test_pay_on_period_end_uses_prior_period(self):
        self.assertEqual(ims_cells(sheet(), date(2026, 9, 15))[3], date(2026, 8, 31))

    def test_existing_amount_reported(self):
        self.assertEqual(ims_cells(sheet(), date(2026, 9, 10))[4], 3500)

    def test_no_earlier_period(self):
        self.assertIsNone(ims_cells(sheet(), date(2026, 8, 1)))

class LagTests(unittest.TestCase):
    def test_usual_paydays_accepted(self):
        self.assertTrue(plausible_lag(date(2026, 9, 25), date(2026, 9, 15)))
        self.assertTrue(plausible_lag(date(2026, 10, 9), date(2026, 9, 30)))

    def test_payday_that_slips_past_next_period_end_is_held(self):
        # Paid 10/16 for the period ending 9/30: the nearest earlier end is 10/15, one day before.
        self.assertEqual(ims_cells(sheet() + [['', 20, serial(date(2026, 10, 3)), '', '', serial(date(2026, 10, 15))]],
                                   date(2026, 10, 16))[3], date(2026, 10, 15))
        self.assertFalse(plausible_lag(date(2026, 10, 16), date(2026, 10, 15)))

    def test_very_late_payment_is_held(self):
        self.assertFalse(plausible_lag(date(2026, 11, 25), date(2026, 10, 31)))

if __name__ == '__main__': unittest.main()
