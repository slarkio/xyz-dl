# xyz-dl - 小宇宙播客音频下载器

从小宇宙播客平台下载音频文件的 Python 单文件程序。

## 功能特性

- 🎵 从小宇宙播客 episode URL 提取音频源并下载
- 📝 自动解析播客标题和主播信息
- 🔧 智能文件命名（格式：主播名 - 节目名）
- 📁 支持自定义下载目录
- 📊 实时下载进度显示
- ✅ 文件重复检查和覆盖确认
- 🚫 文件名非法字符自动清理

## 环境要求

- Python 3.6+
- 依赖库：requests, beautifulsoup4

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
pip install -r requirements.txt
```

## 使用方法

### 基本用法

```bash
python xyz-dl.py <episode_url>
```

### 指定下载目录

```bash
python xyz-dl.py -d ~/Downloads <episode_url>
```

### 详细输出模式

```bash
python xyz-dl.py -v <episode_url>
```

### 完整示例

```bash
python xyz-dl.py https://www.xiaoyuzhoufm.com/episode/12345678
python xyz-dl.py -d ~/Downloads https://www.xiaoyuzhoufm.com/episode/12345678
```

## 参数说明

- `url`: 小宇宙播客 episode 页面 URL（必需）
- `-d, --dir`: 下载目录（默认：当前目录）
- `-v, --verbose`: 显示详细输出
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

- **HTTP 请求**：使用 requests 库处理网络请求
- **页面解析**：使用 BeautifulSoup 解析 HTML 页面
- **流式下载**：支持大文件下载和进度显示
- **用户代理**：模拟浏览器请求避免被封禁

## 注意事项

1. 请确保有稳定的网络连接
2. 下载的内容仅供个人学习使用
3. 请遵守小宇宙平台的使用条款
4. 建议适度使用，避免频繁请求

## 许可证

本项目仅供学习和个人使用。