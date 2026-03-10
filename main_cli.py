"""
PRManager - 本地代码审查系统
CLI模式入口
"""
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
from src.adapters.cli_adapter import start_cli


if __name__ == "__main__":
    start_cli()