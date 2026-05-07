"""
Web Tool Skill

功能：
- 抓取网页内容
- 提取网页链接
- 解析 HTML 结构
"""

from pathlib import Path
from typing import List
from langchain_core.tools import tool, BaseTool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from core.base_skill import BaseSkill, SkillMetadata


class WebToolSkill(BaseSkill):
    """网页抓取 Skill"""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="web_tool",
            description="网页抓取能力，包括获取网页内容、提取链接、解析HTML结构等",
            version="1.0.0",
            tags=["web", "http", "scraping", "html"],
            dependencies=["requests", "beautifulsoup4"],
            author="MuyuCheney"
        )

    def get_loader_tool(self) -> BaseTool:
        """返回 Loader Tool"""
        skill_instance = self

        @tool
        def skill_web_tool(runtime) -> Command:
            """
            Load web scraping capabilities.

            Call this tool when you need to:
            - Fetch web page content from a URL
            - Extract links from web pages
            - Parse HTML structure
            """
            instructions = skill_instance.get_instructions()

            return Command(
                update={
                    "messages": [ToolMessage(
                        content=instructions,
                        tool_call_id=runtime.tool_call_id
                    )],
                    "skills_loaded": ["web_tool"]
                }
            )

        return skill_web_tool

    def get_tools(self) -> List[BaseTool]:
        """返回实际工具"""
        return [
            self._create_fetch_url_tool(),
            self._create_extract_links_tool(),
            self._create_parse_html_tool()
        ]

    def _create_fetch_url_tool(self) -> BaseTool:
        """创建网页抓取工具"""
        @tool
        def fetch_url(url: str, timeout: int = 30) -> str:
            """
            Fetch content from a URL.

            Args:
                url: The URL to fetch
                timeout: Request timeout in seconds (default: 30)

            Returns:
                The content of the web page
            """
            try:
                import requests
                from requests.exceptions import RequestException

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }

                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()

                # 尝试检测编码
                if response.encoding is None or response.encoding == 'ISO-8859-1':
                    response.encoding = response.apparent_encoding

                content = response.text

                # 返回摘要信息
                content_preview = content[:5000] if len(content) > 5000 else content
                return f"Successfully fetched URL: {url}\nStatus: {response.status_code}\nContent length: {len(content)} characters\n\nContent preview:\n{content_preview}"

            except ImportError:
                return "Error: requests not installed. Install with: pip install requests"
            except RequestException as e:
                return f"Error fetching URL: {str(e)}"
            except Exception as e:
                return f"Error: {str(e)}"

        return fetch_url

    def _create_extract_links_tool(self) -> BaseTool:
        """创建链接提取工具"""
        @tool
        def extract_links(url: str, base_url: str = "") -> str:
            """
            Extract all links from a web page.

            Args:
                url: The URL to extract links from
                base_url: Base URL for resolving relative links (optional)

            Returns:
                List of extracted links with their text
            """
            try:
                import requests
                from bs4 import BeautifulSoup
                from urllib.parse import urljoin, urlparse
                import json

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }

                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()

                if response.encoding is None or response.encoding == 'ISO-8859-1':
                    response.encoding = response.apparent_encoding

                soup = BeautifulSoup(response.text, 'html.parser')

                # 确定 base_url
                if not base_url:
                    base_url = url

                links = []
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    text = link.get_text(strip=True)

                    # 转换为绝对 URL
                    absolute_url = urljoin(base_url, href)

                    # 过滤无效链接
                    parsed = urlparse(absolute_url)
                    if parsed.scheme in ('http', 'https'):
                        links.append({
                            'url': absolute_url,
                            'text': text[:100] if text else '(no text)'
                        })

                # 去重
                seen = set()
                unique_links = []
                for link in links:
                    if link['url'] not in seen:
                        seen.add(link['url'])
                        unique_links.append(link)

                result = {
                    'source_url': url,
                    'total_links': len(unique_links),
                    'links': unique_links[:100]  # 限制返回数量
                }

                return json.dumps(result, indent=2, ensure_ascii=False)

            except ImportError:
                return "Error: requests or beautifulsoup4 not installed. Install with: pip install requests beautifulsoup4"
            except Exception as e:
                return f"Error extracting links: {str(e)}"

        return extract_links

    def _create_parse_html_tool(self) -> BaseTool:
        """创建 HTML 解析工具"""
        @tool
        def parse_html(html_content: str, selector: str = "") -> str:
            """
            Parse HTML content and extract elements.

            Args:
                html_content: HTML content to parse
                selector: CSS selector to filter elements (optional)

            Returns:
                Extracted text content or elements
            """
            try:
                from bs4 import BeautifulSoup
                import json

                soup = BeautifulSoup(html_content, 'html.parser')

                if selector:
                    # 使用 CSS 选择器
                    elements = soup.select(selector)
                    results = []
                    for elem in elements:
                        text = elem.get_text(strip=True)
                        if text:
                            results.append({
                                'tag': elem.name,
                                'text': text[:500] if len(text) > 500 else text,
                                'attrs': dict(elem.attrs) if elem.attrs else {}
                            })

                    return json.dumps({
                        'selector': selector,
                        'matches': len(results),
                        'elements': results[:50]  # 限制返回数量
                    }, indent=2, ensure_ascii=False)

                else:
                    # 提取纯文本
                    # 移除脚本和样式
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()

                    text = soup.get_text(separator='\n', strip=True)

                    # 清理多余空行
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    clean_text = '\n'.join(lines)

                    # 获取标题
                    title = soup.title.string if soup.title else '(no title)'

                    # 获取 meta 描述
                    meta_desc = ''
                    meta_tag = soup.find('meta', attrs={'name': 'description'})
                    if meta_tag:
                        meta_desc = meta_tag.get('content', '')

                    result = {
                        'title': title,
                        'meta_description': meta_desc,
                        'text_length': len(clean_text),
                        'text_preview': clean_text[:3000] if len(clean_text) > 3000 else clean_text
                    }

                    return json.dumps(result, indent=2, ensure_ascii=False)

            except ImportError:
                return "Error: beautifulsoup4 not installed. Install with: pip install beautifulsoup4"
            except Exception as e:
                return f"Error parsing HTML: {str(e)}"

        return parse_html


def create_skill(skill_dir: Path) -> BaseSkill:
    """
    工厂函数：创建 Skill 实例

    这是 Registry 自动加载时调用的入口函数
    """
    return WebToolSkill(skill_dir)