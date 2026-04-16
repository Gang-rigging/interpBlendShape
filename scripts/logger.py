import logging
import sys

class InterpFormatter(logging.Formatter):
    """Clean format for WARNING+, verbose with timestamp for DEBUG/INFO."""

    CLEAN   = logging.Formatter('# %(name)s : %(message)s')
    VERBOSE = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s: %(message)s')

    def format(self, record):
        if record.levelno >= logging.WARNING:
            return self.CLEAN.format(record)
        return self.VERBOSE.format(record)


def getLogger(name="InterpBlendShape", level=logging.WARNING):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(InterpFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger