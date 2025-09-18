"""配置管理模块

支持从环境变量、配置文件等多种来源加载配置
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigurationError
from .models import Config


class Settings(BaseSettings):
    """应用设置类，继承自 Pydantic BaseSettings"""

    # 网络配置
    xyz_dl_timeout: int = 30
    xyz_dl_max_retries: int = 3
    xyz_dl_chunk_size: int = 8192

    # 用户代理
    xyz_dl_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # 文件名设置
    xyz_dl_max_filename_length: int = 200

    # 并发设置
    xyz_dl_max_concurrent_downloads: int = 3

    def to_config(self) -> Config:
        """转换为 Config 模型"""
        return Config(
            timeout=self.xyz_dl_timeout,
            max_retries=self.xyz_dl_max_retries,
            chunk_size=self.xyz_dl_chunk_size,
            user_agent=self.xyz_dl_user_agent,
            max_filename_length=self.xyz_dl_max_filename_length,
            max_concurrent_downloads=self.xyz_dl_max_concurrent_downloads,
        )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self._config: Optional[Config] = None

    def get_config(self) -> Config:
        """获取配置，优先环境变量，然后使用默认值"""
        if self._config is not None:
            return self._config

        # 从环境变量加载设置
        settings = Settings()
        config_dict = settings.model_dump()

        # 移除 xyz_dl_ 前缀
        clean_config = {}
        for key, value in config_dict.items():
            if key.startswith("xyz_dl_"):
                clean_key = key[7:]  # 移除 'xyz_dl_' 前缀
                clean_config[clean_key] = value
            else:
                clean_config[key] = value

        try:
            self._config = Config(**clean_config)
            return self._config
        except Exception as e:
            raise ConfigurationError(f"Failed to validate configuration: {e}")


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config() -> Config:
    """获取全局配置"""
    return config_manager.get_config()


# 环境变量检查
def check_environment() -> Dict[str, Any]:
    """检查环境变量配置"""
    env_vars = {}

    for key in os.environ:
        if key.startswith("XYZ_DL_"):
            env_vars[key] = os.environ[key]

    return env_vars


if __name__ == "__main__":
    # 测试配置管理
    print("Current config:", get_config())
    print("Environment variables:", check_environment())
