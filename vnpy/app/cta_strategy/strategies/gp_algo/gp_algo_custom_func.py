import time
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def neg(x):
    return -x


def delay(x, t):
    return x[:-t]


def delta(x, t):
    return x[t:] - delay(x, t)


def ts_min(x, t):
    return np.min(sliding_window_view(x, t), axis=1)


def ts_max(x, t):
    return np.max(sliding_window_view(x, t), axis=1)


def ts_argmin(x, t):
    return np.argmin(sliding_window_view(x, t), axis=1)


def ts_argmax(x, t):
    return np.argmax(sliding_window_view(x, t), axis=1)


def ts_rank(x, t):
    last_value = x[-1]
    sliding_array = sliding_window_view(x, t)
    left = np.count_nonzero(sliding_array < last_value, axis=1)
    right = np.count_nonzero(sliding_array <= last_value, axis=1)
    pct = (right + left + (right > left).astype(int)) * 50.0 / sliding_array.shape[1]
    return pct


def ts_sum(x, t):
    return np.sum(sliding_window_view(x, t), axis=1)


def ts_stddev(x, t):
    return np.std(sliding_window_view(x, t), axis=1)


def ts_mean_return(x, t):
    sliding_array = sliding_window_view(x, t)
    rate = sliding_array[1:] / sliding_array[:-1] - 1
    return np.mean(rate, axis=1)
