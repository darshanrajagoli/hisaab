"""Tests for statistical computations — Wilson CI, bootstrap CI, binomial test."""

from hisaab.pipeline.stats import binomial_test, bootstrap_ci, wilson_ci


class TestWilsonCI:
    def test_perfect_hit_rate(self):
        low, high = wilson_ci(10, 10)
        assert low > 0.6
        assert high == 1.0 or high > 0.95

    def test_zero_hit_rate(self):
        low, high = wilson_ci(0, 10)
        assert low == 0.0 or low < 0.05
        assert high < 0.4

    def test_fifty_percent(self):
        low, high = wilson_ci(50, 100)
        assert low < 0.5
        assert high > 0.5

    def test_small_sample(self):
        low, high = wilson_ci(1, 2)
        # Wide interval expected
        assert high - low > 0.3

    def test_zero_n(self):
        low, high = wilson_ci(0, 0)
        assert low == 0.0
        assert high == 1.0


class TestBootstrapCI:
    def test_positive_values(self):
        values = [0.05, 0.10, 0.03, 0.08, 0.02, 0.15, 0.07, 0.04, 0.09, 0.06]
        low, high = bootstrap_ci(values)
        assert low > 0.0
        assert high > low

    def test_mixed_values(self):
        values = [-0.1, 0.2, -0.05, 0.15, 0.0, -0.08, 0.1, 0.05, -0.02, 0.03]
        low, high = bootstrap_ci(values)
        assert low < high

    def test_deterministic(self):
        """Same seed should give same results."""
        values = [0.1, 0.2, 0.3]
        ci1 = bootstrap_ci(values, seed=42)
        ci2 = bootstrap_ci(values, seed=42)
        assert ci1 == ci2

    def test_empty(self):
        low, high = bootstrap_ci([])
        assert low == 0.0
        assert high == 0.0


class TestBinomialTest:
    def test_clearly_better_than_coin(self):
        p = binomial_test(90, 100, 0.5)
        assert p < 0.01

    def test_clearly_worse_than_coin(self):
        p = binomial_test(10, 100, 0.5)
        assert p < 0.01

    def test_indistinguishable(self):
        p = binomial_test(52, 100, 0.5)
        assert p > 0.05

    def test_zero_n(self):
        p = binomial_test(0, 0, 0.5)
        assert p == 1.0
