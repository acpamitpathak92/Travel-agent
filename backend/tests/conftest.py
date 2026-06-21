"""Force adapters onto their offline path during the deterministic suite so
tests are fast and reproducible regardless of network. Live-parser tests below
do not need network because they call the pure parser functions directly."""
import app.config


def pytest_configure(config):
    app.config.settings.allow_network = False
