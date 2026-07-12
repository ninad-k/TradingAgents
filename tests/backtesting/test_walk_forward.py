from tradingagents.backtesting.walk_forward import expanding_walk_forward


def test_expanding_walk_forward_is_chronological_and_disjoint():
    folds = expanding_walk_forward(list(range(10)), train_size=4, test_size=2)
    assert [(f.train, f.test) for f in folds] == [
        ((0, 1, 2, 3), (4, 5)),
        ((0, 1, 2, 3, 4, 5), (6, 7)),
        ((0, 1, 2, 3, 4, 5, 6, 7), (8, 9)),
    ]
