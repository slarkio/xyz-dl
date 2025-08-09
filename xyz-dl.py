#!/usr/bin/env python3
"""
xyz-dl - 小宇宙播客音频下载器

从小宇宙播客平台下载音频文件的Python单文件程序
支持从episode URL提取音频源并下载到本地

使用方法:
    python xyz-dl.py <episode_url>
    
示例:
    python xyz-dl.py https://www.xiaoyuzhoufm.com/episode/12345678
"""

import sys
import re
import os
import argparse
from urllib.parse import urlparse, unquote
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("缺少依赖库，请安装：")
    print("pip install requests beautifulsoup4")
    sys.exit(1)


class XiaoyuzhouDownloader:
    """小宇宙播客下载器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def validate_url(self, url):
        """验证URL格式"""
        if not url.startswith('https://www.xiaoyuzhoufm.com/episode/'):
            raise ValueError("URL必须是小宇宙播客episode页面")
        return True
    
    def extract_audio_info(self, url):
        """从页面提取音频信息"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"获取页面失败: {e}")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取音频URL
        audio_tag = soup.find('audio')
        if not audio_tag or not audio_tag.get('src'):
            raise Exception("页面中未找到音频文件")
        
        audio_url = audio_tag.get('src')
        
        # 提取标题信息
        title_tag = soup.find('title')
        if not title_tag:
            raise Exception("页面中未找到标题信息")
        
        title_text = title_tag.get_text()
        
        # 解析标题格式: "节目名 - 主播名 | 小宇宙"
        # 移除 "| 小宇宙" 部分
        if '|' in title_text:
            title_text = title_text.split('|')[0].strip()
        
        # 分割节目名和主播名
        if ' - ' in title_text:
            parts = title_text.split(' - ')
            if len(parts) >= 2:
                episode_name = parts[0].strip()
                host_name = parts[1].strip()
                # 按照扩展的命名格式: "主播名 - 节目名"
                filename = f"{host_name} - {episode_name}"
            else:
                filename = title_text
        else:
            filename = title_text
        
        # 清理文件名中的非法字符
        filename = self.sanitize_filename(filename)
        
        return {
            'audio_url': audio_url,
            'filename': filename,
            'title': title_text
        }
    
    def sanitize_filename(self, filename):
        """清理文件名中的非法字符"""
        # 移除或替换Windows/macOS不支持的字符
        illegal_chars = r'[<>:"/\\|?*]'
        filename = re.sub(illegal_chars, '', filename)
        
        # 移除多余空格
        filename = ' '.join(filename.split())
        
        # 限制文件名长度
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename.strip()
    
    def download_audio(self, audio_url, filename, download_dir='.'):
        """下载音频文件"""
        # 确保下载目录存在
        download_path = Path(download_dir)
        download_path.mkdir(exist_ok=True)
        
        # 构建完整文件路径
        file_path = download_path / f"{filename}.mp3"
        
        # 检查文件是否已存在
        if file_path.exists():
            overwrite = input(f"文件 '{file_path}' 已存在，是否覆盖？(y/N): ")
            if overwrite.lower() not in ['y', 'yes']:
                print("下载已取消")
                return None
        
        try:
            print(f"开始下载: {filename}.mp3")
            
            # 获取文件大小
            head_response = self.session.head(audio_url, timeout=30)
            file_size = int(head_response.headers.get('content-length', 0))
            
            # 流式下载
            response = self.session.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()
            
            downloaded = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 显示下载进度
                        if file_size > 0:
                            progress = (downloaded / file_size) * 100
                            print(f"\r下载进度: {progress:.1f}% ({downloaded}/{file_size} bytes)", end='', flush=True)
            
            print(f"\n下载完成: {file_path}")
            return str(file_path)
            
        except requests.RequestException as e:
            raise Exception(f"下载失败: {e}")
        except IOError as e:
            raise Exception(f"文件写入失败: {e}")
    
    def download(self, url, download_dir='.'):
        """主下载方法"""
        self.validate_url(url)
        
        print(f"正在解析页面: {url}")
        audio_info = self.extract_audio_info(url)
        
        print(f"节目信息: {audio_info['title']}")
        print(f"文件名: {audio_info['filename']}.mp3")
        
        file_path = self.download_audio(
            audio_info['audio_url'], 
            audio_info['filename'], 
            download_dir
        )
        
        return file_path


def main():
    parser = argparse.ArgumentParser(
        description='从小宇宙播客平台下载音频文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python xyz-dl.py https://www.xiaoyuzhoufm.com/episode/12345678
  python xyz-dl.py -d ~/Downloads https://www.xiaoyuzhoufm.com/episode/12345678
        """
    )
    
    parser.add_argument('url', help='小宇宙播客episode页面URL')
    parser.add_argument('-d', '--dir', default='.', 
                       help='下载目录 (默认: 当前目录)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='显示详细输出')
    
    args = parser.parse_args()
    
    try:
        downloader = XiaoyuzhouDownloader()
        file_path = downloader.download(args.url, args.dir)
        
        if file_path:
            print(f"\n✅ 下载成功!")
            print(f"文件位置: {file_path}")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()