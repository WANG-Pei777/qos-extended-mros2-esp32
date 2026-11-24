#!/usr/bin/env python3
"""Focused tests for confirmatory three-system statistics."""

import unittest

import numpy as np

from analyze_three_system_formal import exact_sign_flip, holm_adjust


class ConfirmatoryStatisticsTests(unittest.TestCase):
    def test_exact_sign_flip_extreme_direction(self):
        self.assertEqual(exact_sign_flip([1.0] * 10), 2 / 1024)

    def test_holm_is_monotone_in_sorted_order(self):
        raw = [0.01, 0.03, 0.02, 0.5, 0.001, 0.9]
        adjusted = holm_adjust(raw)
        ordered = sorted(zip(raw, adjusted))
        self.assertTrue(all(left[1] <= right[1] for left, right in zip(ordered, ordered[1:])))
        self.assertTrue(all(adjusted[index] >= raw[index] for index in range(len(raw))))

    def test_empty_sign_flip_is_nan(self):
        self.assertTrue(np.isnan(exact_sign_flip([])))


if __name__ == "__main__":
    unittest.main()
