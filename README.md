# xyz-dl - 小宇宙播客音频下载器

从小宇宙播客平台下载音频文件和Show Notes的现代化Python程序。

## 功能特性

- 🎵 从小宇宙播客 episode URL 提取音频源并下载
- 📝 自动解析播客标题和主播信息，支持Show Notes下载
- 🔧 智能文件命名（格式：主播名 - 节目名）
- 📁 支持自定义下载目录
- 📊 美化的实时下载进度显示
- ✅ 文件重复检查和覆盖确认
- 🚫 文件名非法字符自动清理
- 🎯 多种下载模式：audio/md/both
- ⚡ 异步下载支持，提升性能
- 🛠️ 现代化CLI界面，配置文件支持

## 环境要求

- Python 3.8+
- 依赖库：aiohttp, aiofiles, beautifulsoup4, pydantic, rich

## 安装方式

### 使用 uv (推荐)

```bash
# 克隆项目
git clone <repository-url>
cd xyz-dl

# 使用 uv 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows
```

### 使用 pip

```bash
# 开发模式安装
uv pip install -e .

# 或直接安装
pip install .
```

## 使用方法

### 安装后使用（推荐）

```bash
# 基本用法
xyz-dl <episode_url>

# 指定下载目录
xyz-dl -d ~/Downloads <episode_url>

# 选择下载模式
xyz-dl --mode audio <episode_url>     # 仅下载音频
xyz-dl --mode md <episode_url>        # 仅下载Show Notes
xyz-dl --mode both <episode_url>      # 同时下载（默认）

# 详细输出模式
xyz-dl -v <episode_url>
```

### 开发模式使用

```bash
# 通过模块调用
python -m src.xyz_dl <episode_url>
python -m src.xyz_dl -d ~/Downloads <episode_url>
```

### 完整示例

```bash
xyz-dl https://www.xiaoyuzhoufm.com/episode/12345678
xyz-dl -d ~/Downloads --mode both https://www.xiaoyuzhoufm.com/episode/12345678
```

## 参数说明

- `url`: 小宇宙播客 episode 页面 URL（必需）
- `-d, --dir`: 下载目录（默认：当前目录）
- `--mode`: 下载模式（audio/md/both，默认：both）
- `-v, --verbose`: 显示详细输出
- `--config`: 创建默认配置文件
- `--config-path`: 指定配置文件路径
- `--version`: 显示版本信息
- `-h, --help`: 显示帮助信息

## URL 格式要求

支持的 URL 格式：
```
https://www.xiaoyuzhoufm.com/episode/[episode_id]
```

## 文件命名规则

程序会自动解析页面标题，并按以下规则命名：

1. **标准格式**：主播名 - 节目名.mp3
2. **非法字符清理**：自动移除 `<>:"/\|?*` 等字符
3. **长度限制**：文件名超过 200 字符会被截断
4. **空格处理**：多余空格会被合并

## 错误处理

程序包含完善的错误处理机制：

- **网络错误**：超时、连接失败等网络问题
- **页面解析错误**：找不到音频文件或标题信息
- **文件操作错误**：磁盘空间不足、权限问题等
- **URL 格式错误**：非小宇宙 episode 页面 URL

## 技术实现

- **异步HTTP**：使用 aiohttp 库处理异步网络请求
- **页面解析**：使用 BeautifulSoup 解析 HTML 页面
- **数据验证**：使用 Pydantic 进行数据模型验证
- **美化界面**：使用 Rich 库提供美观的CLI体验
- **流式下载**：支持大文件下载和美化进度显示
- **配置管理**：支持配置文件和环境变量配置
- **用户代理**：模拟浏览器请求避免被封禁

## 注意事项

1. 请确保有稳定的网络连接
2. 下载的内容仅供个人学习使用
3. 请遵守小宇宙平台的使用条款
4. 建议适度使用，避免频繁请求

## 许可证

本项目仅供学习和个人使用。