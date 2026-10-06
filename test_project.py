import unittest
from datetime import date
from project import project
from test_invoice import header, row, H2_2026, RATES

class ProjectTests(unittest.TestCase):
    def test_periods_until_schedule_ends(self):
        tab = [header(H2_2026, 'Oct 26')] + [row(H2_2026, d, t1='Day' if d == 5 else '') for d in range(1, 32)]
        rows = project([tab], date(2026, 10, 17), RATES)
        self.assertEqual([r[0] for r in rows], [date(2026, 10, 17), date(2026, 10, 31)])  # November not built yet
        self.assertEqual(rows[0][1:4], [1, 14, 103])  # Oct 4-17: one Tele 1 plus fourteen Tele 2 nights
        self.assertEqual(rows[1][1:4], [0, 14, 98])

if __name__ == '__main__': unittest.main()
