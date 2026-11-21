import numpy as np
import pandas as pd
import pytest

from scripts.clustered_performance import clustered, decide, net_return


def test_repeating_a_signal_day_does_not_create_independent_evidence():
    # 100 identical trades per signal day. Treating all 400 as independent
    # would reject zero; the four independent clusters do not.
    daily = np.array([-.01, -.01, .02, .02])
    result = clustered(pd.Series(np.repeat(daily, 100)), np.repeat(range(4), 100))
    assert result["t"] == pytest.approx(daily.mean() / (daily.std(ddof=1) / 2))
    assert result["ci95"][0] < 0 < result["ci95"][1]
    assert decide(result["t"], result["mean"], result["mean"], 2, .01, None) == "不通過"


def test_uneven_clusters_target_trade_mean():
    x = pd.Series([0., 0., 0., .04])
    result = clustered(x, [1, 1, 1, 2])
    assert result["mean"] == pytest.approx(.01)
    assert result["se"] == pytest.approx(.015)


def test_insufficient_data_and_strict_gates():
    assert clustered(pd.Series([.01, .02]), [1, 1])["t"] is None
    assert decide(2, .01, .01, 2, .01, True) == "不通過"
    assert decide(3, .01, .01, 1.5, .01, True) == "不通過"
    assert decide(3, -.01, .01, 2, .01, True) == "不通過"
    assert decide(3, .01, .01, 2, .01, None) == "樣本不足"
    assert decide(3, .01, .01, 2, .01, True) == "通過"
    assert net_return(0., .003, .001) < net_return(0., .001, .001) < 0
