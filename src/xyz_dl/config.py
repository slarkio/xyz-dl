"""配置管理模块

支持从环境变量、配置文件等多种来源加载配置
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Union
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import Config
from .exceptions import ConfigurationError


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
        self._config_paths = [
            Path.home() / ".xyz-dl" / "config.json",  # 用户配置
            Path.cwd() / "xyz-dl.json",  # 项目配置
            Path.cwd() / ".xyz-dl.json",  # 隐藏项目配置
        ]

    def load_config(self, config_path: Optional[Union[str, Path]] = None) -> Config:
        """加载配置

        优先级（从高到低）：
        1. 指定的配置文件路径
        2. 环境变量
        3. 配置文件
        4. 默认值
        """
        if self._config is not None:
            return self._config

        # 1. 从环境变量加载基础设置
        settings = Settings()
        config_dict = settings.model_dump()

        # 2. 从配置文件加载（如果存在）
        file_config = self._load_from_file(config_path)
        if file_config:
            config_dict.update(file_config)

        # 3. 移除 xyz_dl_ 前缀
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

    def _load_from_file(
        self, config_path: Optional[Union[str, Path]] = None
    ) -> Optional[Dict[str, Any]]:
        """从文件加载配置"""
        paths_to_try = []

        if config_path:
            paths_to_try.append(Path(config_path))

        paths_to_try.extend(self._config_paths)

        for path in paths_to_try:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                    print(f"Loaded configuration from: {path}")
                    return config_data
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Failed to load config from {path}: {e}")
                    continue

        return None

    def save_config(
        self, config: Config, config_path: Optional[Union[str, Path]] = None
    ) -> None:
        """保存配置到文件"""
        if config_path:
            path = Path(config_path)
        else:
            # 使用第一个配置路径作为默认保存位置
            path = self._config_paths[0]

        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            config_dict = config.model_dump()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            print(f"Configuration saved to: {path}")
        except IOError as e:
            raise ConfigurationError(f"Failed to save config to {path}: {e}")

    def reload_config(self) -> Config:
        """重新加载配置"""
        self._config = None
        return self.load_config()

    def get_config(self) -> Config:
        """获取当前配置，如果未加载则自动加载"""
        if self._config is None:
            return self.load_config()
        return self._config

    def update_config(self, **kwargs) -> Config:
        """更新配置项"""
        current_config = self.get_config()
        config_dict = current_config.model_dump()
        config_dict.update(kwargs)

        try:
            self._config = Config(**config_dict)
            return self._config
        except Exception as e:
            raise ConfigurationError(f"Failed to update configuration: {e}")


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config() -> Config:
    """获取全局配置"""
    return config_manager.get_config()


def load_config(config_path: Optional[Union[str, Path]] = None) -> Config:
    """加载配置"""
    return config_manager.load_config(config_path)


def save_config(config: Config, config_path: Optional[Union[str, Path]] = None) -> None:
    """保存配置"""
    config_manager.save_config(config, config_path)


def create_default_config_file(path: Optional[Union[str, Path]] = None) -> Path:
    """创建默认配置文件"""
    if path:
        config_path = Path(path)
    else:
        config_path = config_manager._config_paths[0]

    # 创建默认配置
    default_config = Config()

    # 确保目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存配置文件
    config_dict = default_config.model_dump()
    config_dict["_comment"] = "xyz-dl configuration file"

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)

    print(f"Default configuration file created at: {config_path}")
    return config_path


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
