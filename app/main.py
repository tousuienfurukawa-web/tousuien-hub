# --- safe import for gpt5_summary ---
import logging

generate_slack_summary = None
try:
    # try relative import (preferred when app is a package)
    from .gpt5_summary import generate_slack_summary
    logging.info("Imported gpt5_summary via relative import")
except Exception:
    try:
        # fallback: absolute import (in case package layout differs)
        from gpt5_summary import generate_slack_summary
        logging.info("Imported gpt5_summary via absolute import")
    except Exception:
        # final fallback: leave generate_slack_summary as None and log exception
        logging.exception("gpt5_summary could not be imported; functionality will be disabled.")
        generate_slack_summary = None
# --- end safe import ---
