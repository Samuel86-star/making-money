from pathlib import Path
import a_stock.config as cfg


def test_paths_exist():
    assert cfg.ROOT.exists()
    assert isinstance(cfg.DATA_DIR, Path)
    assert isinstance(cfg.SCREEN_DIR, Path)
    assert isinstance(cfg.BRIEFS_DIR, Path)
    assert isinstance(cfg.EM_CACHE_DIR, Path)


def test_em_interval_default():
    assert cfg.EM_MIN_INTERVAL == 1.0
    assert isinstance(cfg.TZ, str)


def test_scoring_has_both_strategies():
    assert "short" in cfg.SCORING
    assert "mid" in cfg.SCORING
    assert sum(cfg.SCORING["short"].values()) == 100
    assert sum(cfg.SCORING["mid"].values()) == 100