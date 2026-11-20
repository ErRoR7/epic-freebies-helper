# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import sys
from zoneinfo import ZoneInfo
from loguru import logger

def timezone_filter(record):
    record["time"] = record["time"].astimezone(ZoneInfo("Asia/Shanghai"))
    return record

def init_log(**sink_channel):
    # Simple logger setup; no patching logic lives here anymore
    log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    logger.remove()
    logger.add(sink=sys.stdout, level=log_level, filter=timezone_filter)
    
    # Attach the remaining log outputs
    if sink_channel.get("error"):
        logger.add(sink=sink_channel.get("error"), level="ERROR", rotation="5 MB", filter=timezone_filter)
    if sink_channel.get("runtime"):
        logger.add(sink=sink_channel.get("runtime"), level="TRACE", rotation="5 MB", filter=timezone_filter)
        
    return logger
