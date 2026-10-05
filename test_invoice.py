import unittest
from datetime import date
from invoice import shifts, shifts_from_tabs, last_period, month_marker, header_layout

# Column layouts seen in the live schedule (0-based): Tele 1, Tele 2, month marker.
H1_2026 = (17, 18, 24)   # Jan-June 2026: R, S, Y
H2_2026 = (18, 19, 25)   # July-Dec 2026: S, T, Z
H1_2027 = (19, 20, 26)   # Jan-June 2027: T, U, AA

def header(layout, marker):
    t1, t2, m = layout
    r = [''] * (m + 3)
    r[t1 - 1] = 'Tele admit'; r[t1] = 'Tele 1 (7p-12a)'; r[t2] = 'Tele 2 (12a-7a)'; r[m] = marker
    return r

def row(layout, d, t1='', t2='Day '):
    a, b, m = layout
    r = [''] * (m + 1)
    r[0] = d; r[a] = t1; r[b] = t2; r[m] = d
    return r

RATES = {'tele1': '75', 'tele2': '75'}

class InvoiceTests(unittest.TestCase):
    def test_corrected_invoice(self):
        tab = [header(H2_2026, 'Sep 26')] + [row(H2_2026, d) for d in range(20, 31)] + [header(H2_2026, 'Oct 26')]
        r = shifts(tab[:9] + tab[-1:], date(2026, 9, 20), date(2026, 10, 3), RATES)
        self.assertEqual(sum(x['hours'] for x in r), 56)
        self.assertEqual(sum(int(x['amount']) for x in r), 4200)
        self.assertEqual({x['shift'] for x in r}, {'tele2'})

    def test_month_boundary(self):
        tab = [header(H2_2026, 'Sep 26'), row(H2_2026, 30), header(H2_2026, 'Oct 26'), row(H2_2026, 1)]
        r = shifts(tab, date(2026, 9, 20), date(2026, 10, 3), RATES)
        self.assertEqual([x['date'] for x in r], ['2026-09-30', '2026-10-01'])

    def test_unknown_rate(self):
        tab = [header(H2_2026, 'Nov 26'), row(H2_2026, 23, 'Day', ''), header(H2_2026, 'Dec 26')]
        with self.assertRaises(ValueError): shifts(tab, date(2026, 11, 22), date(2026, 12, 5), {'tele2': '75'})

    def test_period(self): self.assertEqual(last_period(date(2026, 10, 18)), date(2026, 10, 17))

    def test_columns_found_by_header_in_each_half_year(self):
        # Same assignments, three different column layouts: each must yield Tele 1 = 5h and Tele 2 = 7h.
        for layout, y in [(H1_2026, 2026), (H2_2026, 2026), (H1_2027, 2027)]:
            tab = [header(layout, f'Mar {y % 100}'), row(layout, 1, 'Day ', 'Day '), row(layout, 2, '', 'Day ')]
            r = shifts(tab, date(y, 3, 1), date(y, 3, 14), RATES)
            self.assertEqual([(x['date'][5:], x['shift'], x['hours']) for x in r],
                             [('03-01', 'tele1', 5), ('03-01', 'tele2', 7), ('03-02', 'tele2', 7)], layout)

    def test_layout_change_between_tabs_spanning_new_year(self):
        # Period Dec 27 2026 - Jan 9 2027 crosses from the July-Dec tab to the Jan-June tab.
        dec = [header(H2_2026, 'Dec 26'), row(H2_2026, 27), row(H2_2026, 31, 'Day ', '')]
        jan = [header(H1_2027, 'Jan 27'), row(H1_2027, 1), row(H1_2027, 9, 'Day ', 'Day ')]
        r = shifts_from_tabs([dec, jan], date(2026, 12, 27), date(2027, 1, 9), RATES)
        self.assertEqual([(x['date'], x['shift']) for x in r],
                         [('2026-12-27', 'tele2'), ('2026-12-31', 'tele1'), ('2027-01-01', 'tele2'),
                          ('2027-01-09', 'tele1'), ('2027-01-09', 'tele2')])
        self.assertEqual(sum(x['hours'] for x in r), 31)

    def test_unformatted_api_values(self):
        # Sheets API UNFORMATTED_VALUE returns dates as serial numbers and day numbers as numbers.
        oct1 = (date(2026, 10, 1) - date(1899, 12, 30)).days
        tab = [header(H2_2026, oct1), row(H2_2026, 5.0), row(H2_2026, 'Mon 12')]
        r = shifts(tab, date(2026, 10, 4), date(2026, 10, 17), RATES)
        self.assertEqual([x['date'] for x in r], ['2026-10-05', '2026-10-12'])

    def test_marker_formats(self):
        self.assertEqual(month_marker('Aug 26'), (2026, 8))
        self.assertEqual(month_marker('Feb 2027'), (2027, 2))
        self.assertEqual(month_marker(date(2026, 3, 26)), (2026, 3))
        self.assertIsNone(month_marker('Tele 2 (12a-7a)'))

    def test_missing_month_block_is_an_error_not_zero_shifts(self):
        tab = [header(H2_2026, 'Sep 26'), row(H2_2026, 20)]
        with self.assertRaises(ValueError): shifts(tab, date(2026, 9, 20), date(2026, 10, 3), RATES)

    def test_mixed_assignment_stops(self):
        tab = [header(H2_2026, 'Oct 26'), row(H2_2026, 5, '', 'Day/Wong')]
        with self.assertRaises(ValueError): shifts(tab, date(2026, 10, 4), date(2026, 10, 17), RATES)

    def test_header_needs_both_tele_columns(self):
        r = [''] * 30; r[18] = 'Tele 1 (7p-12a)'
        with self.assertRaises(ValueError): header_layout(r)

if __name__ == '__main__': unittest.main()
