"""Minimal Gaussian-process surrogate + Expected Improvement.

A dependency-free, deterministic GP regressor with an isotropic RBF kernel and
fixed hyperparameters, fit by a hand-rolled Cholesky solve. Targets are
standardized internally. This is the surrogate model behind the Bayesian
configuration tuner (Layer B1); it is intentionally simple and teachable
rather than state-of-the-art — no hyperparameter optimization, no external
linear-algebra dependency.

Determinism: there is no RNG anywhere. Given the same observations the
posterior and the acquisition values are bit-stable, so the tuner's choices
are fully reproducible.
"""

from __future__ import annotations

import math

_DEFAULT_LENGTHSCALE = 0.3
_DEFAULT_NOISE = 1e-6
_JITTER = 1e-9
_SQRT_2 = math.sqrt(2.0)
_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _rbf(a: tuple[float, ...], b: tuple[float, ...], lengthscale: float) -> float:
    sqdist = sum((x - y) ** 2 for x, y in zip(a, b, strict=True))
    return math.exp(-0.5 * sqdist / (lengthscale * lengthscale))


def _cholesky(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                lower[i][j] = math.sqrt(max(matrix[i][i] - s, _JITTER))
            else:
                lower[i][j] = (matrix[i][j] - s) / lower[j][j]
    return lower


def _forward_sub(lower: list[list[float]], b: list[float]) -> list[float]:
    n = len(lower)
    y = [0.0] * n
    for i in range(n):
        s = sum(lower[i][k] * y[k] for k in range(i))
        y[i] = (b[i] - s) / lower[i][i]
    return y


def _back_sub_transpose(lower: list[list[float]], y: list[float]) -> list[float]:
    n = len(lower)
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = sum(lower[k][i] * x[k] for k in range(i + 1, n))
        x[i] = (y[i] - s) / lower[i][i]
    return x


class GaussianProcess:
    """Zero-mean (after standardization) GP regressor with an RBF kernel."""

    def __init__(
        self,
        *,
        lengthscale: float = _DEFAULT_LENGTHSCALE,
        noise: float = _DEFAULT_NOISE,
    ) -> None:
        self._lengthscale = lengthscale
        self._noise = noise
        self._x: list[tuple[float, ...]] = []
        self._y_mean = 0.0
        self._y_std = 1.0
        self._lower: list[list[float]] = []
        self._alpha: list[float] = []

    def fit(self, x: list[tuple[float, ...]], y: list[float]) -> GaussianProcess:
        if len(x) != len(y):
            raise ValueError("x and y length mismatch")
        if not x:
            raise ValueError("GaussianProcess.fit requires at least one observation")
        self._x = list(x)
        self._y_mean = sum(y) / len(y)
        variance = sum((v - self._y_mean) ** 2 for v in y) / len(y)
        self._y_std = math.sqrt(variance) if variance > 1e-18 else 1.0
        y_std = [(v - self._y_mean) / self._y_std for v in y]

        n = len(x)
        kernel = [
            [_rbf(x[i], x[j], self._lengthscale) for j in range(n)] for i in range(n)
        ]
        for i in range(n):
            kernel[i][i] += self._noise
        self._lower = _cholesky(kernel)
        self._alpha = _back_sub_transpose(
            self._lower, _forward_sub(self._lower, y_std)
        )
        return self

    def predict(self, x_star: tuple[float, ...]) -> tuple[float, float]:
        """Return posterior ``(mean, variance)`` at ``x_star`` (original scale)."""

        if not self._x:
            raise RuntimeError("predict called before fit")
        k_star = [_rbf(x_star, xi, self._lengthscale) for xi in self._x]
        mean_std = sum(k_star[i] * self._alpha[i] for i in range(len(k_star)))
        v = _forward_sub(self._lower, k_star)
        var_std = 1.0 - sum(vi * vi for vi in v)
        var_std = max(var_std, 0.0)
        mean = mean_std * self._y_std + self._y_mean
        var = var_std * (self._y_std * self._y_std)
        return mean, var


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / _SQRT_2))


def _norm_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / _SQRT_2PI


def expected_improvement(
    mean: float,
    variance: float,
    best: float,
    *,
    xi: float = 0.0,
) -> float:
    """Expected improvement for **minimization** of a noisy objective.

    ``best`` is the incumbent (lowest observed) cost. Returns 0 when the
    posterior is effectively deterministic at ``x_star``.
    """

    sigma = math.sqrt(max(variance, 0.0))
    if sigma <= 1e-12:
        return 0.0
    improvement = best - mean - xi
    z = improvement / sigma
    ei = improvement * _norm_cdf(z) + sigma * _norm_pdf(z)
    return max(ei, 0.0)
