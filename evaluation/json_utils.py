"""JSON serialization utilities for evaluation scripts.

Handles numpy types and provides safe division operations.
"""

import json
from typing import Any

import numpy as np


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""

    def default(self, obj):
        # Handle numpy bool types (np.bool8 is deprecated, use np.bool_ only)
        if isinstance(obj, np.bool_):
            return bool(obj)
        # Handle numpy integer types
        if isinstance(
            obj,
            (
                np.integer,
                np.int_,
                np.intc,
                np.intp,
                np.int8,
                np.int16,
                np.int32,
                np.int64,
                np.uint8,
                np.uint16,
                np.uint32,
                np.uint64,
            ),
        ):
            return int(obj)
        # Handle numpy float types
        if isinstance(obj, (np.floating, np.float_, np.float16, np.float32, np.float64)):
            return float(obj)
        # Handle numpy arrays
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        # Handle numpy complex types
        if isinstance(obj, (np.complexfloating, np.complex_, np.complex64, np.complex128)):
            return {"real": obj.real, "imag": obj.imag}
        return super().default(obj)


def safe_dump(obj: Any, file, **kwargs) -> None:
    """Safely dump JSON with numpy type handling."""
    kwargs.setdefault("cls", NumpyEncoder)
    kwargs.setdefault("indent", 2)
    json.dump(obj, file, **kwargs)


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide with default for zero denominator."""
    if denominator == 0:
        return default
    return numerator / denominator


def safe_percent_change(new_value: float, old_value: float) -> float:
    """Calculate percent change with safe division."""
    if old_value == 0:
        return 0.0  # or float('inf') if new_value != 0
    return ((new_value - old_value) / old_value) * 100
