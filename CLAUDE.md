# xyz-dl 项目说明

## 项目概述
小宇宙播客音频下载器 - 从小宇宙播客平台下载音频文件的 Python 单文件程序

## 项目结构
```
xyz-dl/
├── xyz-dl.py          # 主程序文件
├── pyproject.toml     # uv 项目配置和依赖管理
├── README.md          # 项目说明文档
├── CLAUDE.md          # 项目开发说明
└── .gitignore         # Git 忽略文件
```

## 技术栈
- **Python 3.6+**: 主要开发语言
- **requests**: HTTP 请求处理
- **beautifulsoup4**: HTML 页面解析
- **uv**: 现代 Python 包管理工具

## 核心功能
1. **URL 验证**: 验证小宇宙播客 episode 页面 URL
2. **页面解析**: 提取音频 URL 和标题信息
3. **文件命名**: 智能解析和清理文件名
4. **流式下载**: 支持大文件下载和进度显示
5. **错误处理**: 完善的异常处理机制

## 开发环境设置

### 使用 uv (推荐)
```bash
# 初始化项目
uv init

# 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# 运行程序
python xyz-dl.py <url>
```

### 开发工具
- **代码格式化**: black
- **导入排序**: isort
- **代码检查**: flake8
- **测试框架**: pytest

## 命令参考

### 基本使用
```bash
# 下载音频
python xyz-dl.py https://www.xiaoyuzhoufm.com/episode/12345678

# 指定下载目录
python xyz-dl.py -d ~/Downloads <url>

# 详细输出
python xyz-dl.py -v <url>
```

### 开发命令
```bash
# 安装开发依赖
uv sync --extra dev

# 代码格式化
uv run black xyz-dl.py

# 导入排序
uv run isort xyz-dl.py

# 代码检查
uv run flake8 xyz-dl.py

# 运行测试
uv run pytest
```

## 代码规范

### 类设计
- `XiaoyuzhouDownloader`: 主下载器类
  - `validate_url()`: URL 格式验证
  - `extract_audio_info()`: 音频信息提取
  - `sanitize_filename()`: 文件名清理
  - `download_audio()`: 音频文件下载
  - `download()`: 主下载流程

### 错误处理
- **网络错误**: requests.RequestException
- **解析错误**: 找不到音频/标题元素
- **文件操作**: IOError 处理
- **参数验证**: ValueError 处理

### 文件命名规则
1. 解析页面标题格式："节目名 - 主播名 | 小宇宙"
2. 重组为："主播名 - 节目名"
3. 清理非法字符：`[<>:"/\\|?*]`
4. 限制长度：最大 200 字符

## 注意事项
1. **单文件设计**: 保持程序的单文件特性，便于分发使用
2. **依赖最小化**: 仅使用必要的第三方库
3. **用户体验**: 提供清晰的进度反馈和错误提示
4. **文件安全**: 避免文件名冲突和非法字符
5. **网络处理**: 合理的超时设置和重试机制

## 扩展建议
- 批量下载支持
- 配置文件支持
- 下载历史记录
- 音频格式转换
- GUI 界面