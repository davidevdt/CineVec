import logging

format = "[%(asctime)s: %(levelname)s: %(module)s: %(message)s]"


logging.basicConfig(
    level=logging.INFO,
    format=format,
)

logger = logging.getLogger(__name__)
