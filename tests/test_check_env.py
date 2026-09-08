"""Environment check test."""

def test_check_environment_packages():
    has_numpy = False
    try:
        import numpy as np
        has_numpy = True
    except ImportError:
        pass

    has_scipy = False
    try:
        import scipy
        has_scipy = True
    except ImportError:
        pass

    has_torch = False
    try:
        import torch
        has_torch = True
    except ImportError:
        pass

    print(f"\nENV: numpy={has_numpy}, scipy={has_scipy}, torch={has_torch}")
    assert True
