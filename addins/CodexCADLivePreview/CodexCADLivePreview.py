import os
import sys
import traceback


ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
STARTUP_LOG = os.path.join(ADDIN_DIR, 'startup_error.log')
if ADDIN_DIR not in sys.path:
    sys.path.insert(0, ADDIN_DIR)


try:
    from . import Codex_CAD_Workbench as workbench
except Exception:
    try:
        import Codex_CAD_Workbench as workbench
    except Exception:
        with open(STARTUP_LOG, 'w', encoding='utf-8') as log_file:
            log_file.write(traceback.format_exc())
        raise


def run(context):
    try:
        workbench.run(context)
    except Exception:
        with open(STARTUP_LOG, 'w', encoding='utf-8') as log_file:
            log_file.write(traceback.format_exc())
        raise


def stop(context):
    try:
        workbench.stop(context)
    except Exception:
        with open(STARTUP_LOG, 'w', encoding='utf-8') as log_file:
            log_file.write(traceback.format_exc())
        raise
