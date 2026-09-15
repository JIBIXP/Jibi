"""
Module Updater — PATCHÉ v2 (inchangé, imports conditionnels conservés)
"""
__version__ = "2.0.0"

try:
    from . import checker
    CHECKER_OK = True
except ImportError:
    checker = None
    CHECKER_OK = False

try:
    from . import git_manager
    GIT_MANAGER_OK = True
except ImportError:
    git_manager = None
    GIT_MANAGER_OK = False

try:
    from . import rollback
    ROLLBACK_OK = True
except ImportError:
    rollback = None
    ROLLBACK_OK = False

try:
    from . import test_runner
    TEST_RUNNER_OK = True
except ImportError:
    test_runner = None
    TEST_RUNNER_OK = False

try:
    from . import updater as updater_module
    UPDATER_MODULE_OK = True
except ImportError:
    updater_module = None
    UPDATER_MODULE_OK = False

def get_version():
    return __version__

def verifier_modules():
    return {
        "checker": CHECKER_OK,
        "git_manager": GIT_MANAGER_OK,
        "rollback": ROLLBACK_OK,
        "test_runner": TEST_RUNNER_OK,
        "updater": UPDATER_MODULE_OK,
    }
