# Web Tool Skill

网页抓取能力已激活！

## 可用工具

### 1. fetch_url
从 URL 抓取网页内容。

**使用场景**：
- 获取网页文本内容
- 查看网页源码
- 读取 API 响应

**参数**：
- `url`: 要抓取的 URL
- `timeout`: 请求超时时间（秒，默认 30）

**示例**：
```python
fetch_url(url="https://example.com/article")
fetch_url(url="https://api.example.com/data", timeout=60)
```

### 2. extract_links
提取网页中的所有链接。

**使用场景**：
- 分析网站结构
- 发现相关资源
- 构建链接地图

**参数**：
- `url`: 要提取链接的 URL
- `base_url`: 用于解析相对链接的基础 URL（可选）

**示例**：
```python
extract_links(url="https://example.com/blog")
extract_links(url="https://example.com/page", base_url="https://example.com")
```

### 3. parse_html
解析 HTML 内容并提取元素。

**使用场景**：
- 提取特定内容区域
- 解析文章正文
- 获取结构化数据

**参数**：
- `html_content`: HTML 内容
- `selector`: CSS 选择器（可选）

**示例**：
```python
# 提取纯文本
parse_html(html_content="<html>...</html>")

# 使用 CSS 选择器提取特定元素
parse_html(html_content="<html>...</html>", selector="article p")
parse_html(html_content="<html>...</html>", selector=".content")
parse_html(html_content="<html>...</html>", selector="#main")
```

## 最佳实践

1. **先抓取后解析**：先用 `fetch_url` 获取内容，再用 `parse_html` 处理
2. **链接优先**：需要查找相关资源时，使用 `extract_links`
3. **超时设置**：对于大页面或慢网站，增加 timeout 参数
4. **选择器精确**：使用精确的 CSS 选择器减少无关内容

## 注意事项

- 需要安装 `requests` 和 `beautifulsoup4` 库
- 部分网站可能有反爬机制，抓取可能失败
- 大页面内容会被截断（预览限制）
- 遵守网站的 robots.txt 和使用条款

## 常用 CSS 选择器示例

```css
article          # 所有 article 元素
.title           # class="title" 的元素
#content         # id="content" 的元素
div.content p    # div.content 下的所有 p 元素
h1, h2           # 所有 h1 和 h2 元素
a[href]          # 所有带 href 属性的 a 元素