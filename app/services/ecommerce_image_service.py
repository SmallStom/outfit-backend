import asyncio
import ipaddress
import json
import logging
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.exceptions import BadRequestException

logger = logging.getLogger(__name__)

# 允许的平台域名白名单
_ALLOWED_HOSTS = {
    "taobao.com",
    "www.taobao.com",
    "detail.tmall.com",
    "tmall.com",
    "www.tmall.com",
    "item.jd.com",
    "jd.com",
    "www.jd.com",
    "mobile.yangkeduo.com",
    "yangkeduo.com",
    "pinduoduo.com",
    "www.pinduoduo.com",
}

# 各平台通用域名后缀，用于后缀匹配
_ALLOWED_SUFFIXES = (
    ".taobao.com",
    ".tmall.com",
    ".jd.com",
    ".yangkeduo.com",
    ".pinduoduo.com",
)

_PLATFORM_NAMES = {
    "taobao": "淘宝",
    "tmall": "天猫",
    "jd": "京东",
    "pdd": "拼多多",
}

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

_MAX_HTML_SIZE = 3 * 1024 * 1024  # 3 MB
_REQUEST_TIMEOUT = 15.0
_MAX_REDIRECTS = 3


def _is_forbidden_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _validate_hostname_public(hostname: str) -> None:
    if hostname.lower() == "localhost":
        raise BadRequestException("该链接类型不受支持")
    try:
        if _is_forbidden_ip(hostname):
            raise BadRequestException("该链接类型不受支持")
    except ValueError:
        pass

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror:
        raise BadRequestException("链接域名无法解析")
    for info in infos:
        if _is_forbidden_ip(info[4][0]):
            raise BadRequestException("该链接类型不受支持")


def _hostname_of(url: str) -> str:
    return urlparse(url).hostname or ""


def detect_platform(url: str) -> str | None:
    """根据 URL 识别电商平台，返回内部平台标识。"""
    hostname = _hostname_of(url).lower()
    if not hostname:
        return None
    if "jd.com" in hostname:
        return "jd"
    if "taobao.com" in hostname:
        return "taobao"
    if "tmall.com" in hostname:
        return "tmall"
    if "pinduoduo.com" in hostname or "yangkeduo.com" in hostname:
        return "pdd"
    return None


async def validate_ecommerce_url(url: str) -> tuple[str, str]:
    """校验链接是否合法，返回 (platform, normalized_url)。"""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise BadRequestException("仅支持 http/https 链接")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise BadRequestException("链接格式不正确")

    await _validate_hostname_public(hostname)

    if hostname not in _ALLOWED_HOSTS and not hostname.endswith(_ALLOWED_SUFFIXES):
        raise BadRequestException("仅支持淘宝、天猫、京东、拼多多商品链接")

    platform = detect_platform(url)
    if platform is None:
        raise BadRequestException("无法识别该链接所属平台")

    return platform, url


async def fetch_html(url: str) -> str:
    """拉取商品页面 HTML。"""
    current_url = url
    content = bytearray()
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=False,
            headers=_REQUEST_HEADERS,
        ) as client:
            for redirect_count in range(_MAX_REDIRECTS + 1):
                await validate_ecommerce_url(current_url)
                async with client.stream("GET", current_url) as resp:
                    if resp.status_code in {301, 302, 303, 307, 308}:
                        location = resp.headers.get("location")
                        if not location:
                            raise BadRequestException("商品页跳转地址无效")
                        if redirect_count >= _MAX_REDIRECTS:
                            raise BadRequestException("商品页跳转次数过多")
                        current_url = str(resp.url.join(location))
                        continue

                    resp.raise_for_status()
                    content.clear()
                    async for chunk in resp.aiter_bytes():
                        if len(content) + len(chunk) > _MAX_HTML_SIZE:
                            raise BadRequestException("商品页内容过大，无法解析")
                        content.extend(chunk)

                    encoding = resp.encoding or "utf-8"
                    return bytes(content).decode(encoding, errors="replace")
    except httpx.TimeoutException as exc:
        logger.warning("抓取商品页超时: %s", exc)
        raise BadRequestException("抓取商品页超时，请稍后重试或直接上传图片")
    except httpx.HTTPStatusError as exc:
        logger.warning("抓取商品页失败, status=%s: %s", exc.response.status_code, exc)
        raise BadRequestException("无法访问该商品链接，请检查链接是否有效")
    except httpx.RequestError as exc:
        logger.warning("抓取商品页请求错误: %s", exc)
        raise BadRequestException("抓取商品页失败，请直接上传图片")

    raise BadRequestException("商品页抓取失败")


def _resolve_url(url: str, base_url: str) -> str:
    """将相对地址或协议相对地址补全为绝对地址。"""
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return f"https:{url}"
    return urljoin(base_url, url)


def _normalize_image_url(url: str) -> str:
    """去除淘宝/京东等常见的缩略图尺寸后缀，便于去重。"""
    # 淘宝 _400x400.jpg._400x400.jpg 这类
    url = re.sub(r"_\d+x\d+[^?]*", "", url)
    # 京东类似 n0/s320x320 路径，只保留路径主干较困难，这里仅去查询参数
    return url.split("?")[0]


def _dedupe(images: list[dict]) -> list[dict]:
    """按 URL 去重并保持顺序。"""
    seen = set()
    result = []
    for img in images:
        norm = _normalize_image_url(img["url"])
        if not norm or norm in seen:
            continue
        seen.add(norm)
        result.append(img)
    return result


def _extract_og_images(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """提取 Open Graph 图片。"""
    images = []
    for tag in soup.find_all("meta", property=re.compile(r"^og:image", re.I)):
        content = tag.get("content", "").strip()
        if content:
            images.append({"url": _resolve_url(content, base_url), "type": "main"})
    return images


def _extract_jsonld_images(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """提取 JSON-LD 中的图片。"""
    images = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            for key in ("image", "images"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    images.append({"url": _resolve_url(value, base_url), "type": "main"})
                elif isinstance(value, list):
                    for img in value:
                        if isinstance(img, str):
                            images.append({"url": _resolve_url(img, base_url), "type": "main"})
    return images


def _extract_script_json_images(html: str, base_url: str, pattern: re.Pattern, key: str) -> list[dict]:
    """从 script 标签中的 JSON 数据提取图片列表。

    pattern 应捕获包含目标字段的 JSON 对象；若捕获到的是数组，则直接把数组当作图片列表。
    """
    images = []
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            value = data
        elif isinstance(data, dict):
            value = data.get(key)
        else:
            continue
        if isinstance(value, list):
            for img in value:
                if isinstance(img, str):
                    images.append({"url": _resolve_url(img, base_url), "type": "main"})
        elif isinstance(value, str):
            images.append({"url": _resolve_url(value, base_url), "type": "main"})
    return images


def _extract_taobao_images(html: str, base_url: str) -> list[dict]:
    """针对淘宝/天猫页面提取主图。"""
    images = []

    # 常见主图字段 auctionImages / itemPic
    for pattern, key in (
        (re.compile(r'["\']?auctionImages["\']?\s*:\s*(\[[^\]]+\])', re.S), "auctionImages"),
        (re.compile(r'["\']?itemPic["\']?\s*:\s*["\']([^"\']+)["\']', re.S), "itemPic"),
    ):
        if key == "itemPic":
            for match in pattern.finditer(html):
                url = match.group(1).strip().replace("\\/", "/")
                images.append({"url": _resolve_url(url, base_url), "type": "main"})
        else:
            images.extend(_extract_script_json_images(html, base_url, pattern, key))

    # Hub.config.data / g_config 中偶尔有图片配置
    hub_pattern = re.compile(r'Hub\.config\.set\(\s*\'[^\']+\'\s*,\s*(\{.+?\})\s*\)\s*;', re.S)
    for match in hub_pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, str) and (".jpg" in value or ".png" in value or ".webp" in value):
                    images.append({"url": _resolve_url(value.replace("\\/", "/"), base_url), "type": "main"})
                elif isinstance(value, list):
                    for img in value:
                        if isinstance(img, str) and (".jpg" in img or ".png" in img or ".webp" in img):
                            images.append({"url": _resolve_url(img.replace("\\/", "/"), base_url), "type": "main"})

    return images


def _extract_jd_images(html: str, base_url: str) -> list[dict]:
    """针对京东页面提取主图。"""
    images = []

    # initUsedProductInfo / product 等结构中的 imageList
    for pattern, key in (
        (re.compile(r'["\']?imageList["\']?\s*:\s*(\[[^\]]+\])', re.S), "imageList"),
        (re.compile(r'["\']?mainImage["\']?\s*:\s*["\']([^"\']+)["\']', re.S), "mainImage"),
    ):
        if key == "mainImage":
            for match in pattern.finditer(html):
                url = match.group(1).strip().replace("\\/", "/")
                images.append({"url": _resolve_url(url, base_url), "type": "main"})
        else:
            images.extend(_extract_script_json_images(html, base_url, pattern, key))

    # 部分京东页面直接把主图地址放在 descImages 中
    for pattern, key in (
        (re.compile(r'"descImages"\s*:\s*(\[[^\]]+\])', re.S), "descImages"),
    ):
        detail_images = _extract_script_json_images(html, base_url, pattern, key)
        for img in detail_images:
            img["type"] = "detail"
        images.extend(detail_images)

    return images


def _extract_pdd_images(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """针对拼多多页面提取图片（优先 OG 和页面主图）。"""
    images = []
    # 拼多多商品图常见 data-src 属性
    for selector in ("img[src]", "img[data-src]", "img[data-original]"):
        for img in soup.select(selector):
            for attr in ("data-src", "data-original", "src"):
                src = img.get(attr, "").strip()
                if not src:
                    continue
                # 拼多多商品图常见 gif/jpg，过滤小图标
                lower = src.lower()
                if any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
                    if "avatar" in lower or "logo" in lower or "icon" in lower:
                        continue
                    images.append({"url": _resolve_url(src, base_url), "type": "main"})
                    break
    return images


def _extract_detail_images(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """通用详情图提取：从页面正文中找比较大的商品图。"""
    images = []
    for img in soup.find_all("img"):
        for attr in ("data-src", "data-original", "src"):
            src = img.get(attr, "").strip()
            if not src:
                continue
            lower = src.lower()
            if not any(ext in lower for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
                continue
            # 过滤明显非商品图
            if any(bad in lower for bad in ("avatar", "logo", "icon", "qrcode", "wechat", "wx")):
                continue
            # 仅当 img 标签在内容区域或图片尺寸较大时才认为可能是详情图
            width = img.get("width") or img.get("data-width")
            height = img.get("height") or img.get("data-height")
            try:
                w = int(width) if width else 0
                h = int(height) if height else 0
            except ValueError:
                w = h = 0
            # 尺寸够大 或 路径里不含明显小图后缀
            is_large = w >= 200 or h >= 200 or "_400x" in lower or "_800x" in lower
            images.append({"url": _resolve_url(src, base_url), "type": "detail" if not is_large else "main"})
            break
    return images


def extract_images(platform: str, html: str, base_url: str) -> list[dict]:
    """根据平台提取候选图片列表。"""
    soup = BeautifulSoup(html, "html.parser")
    images: list[dict] = []

    # 1. 通用 OG / JSON-LD
    images.extend(_extract_og_images(soup, base_url))
    images.extend(_extract_jsonld_images(soup, base_url))

    # 2. 平台特定提取
    if platform in ("taobao", "tmall"):
        images.extend(_extract_taobao_images(html, base_url))
    elif platform == "jd":
        images.extend(_extract_jd_images(html, base_url))
    elif platform == "pdd":
        images.extend(_extract_pdd_images(soup, base_url))

    # 3. 兜底：页面所有候选图
    images.extend(_extract_detail_images(soup, base_url))

    return _dedupe(images)


async def fetch_ecommerce_images(url: str) -> dict:
    """对外主入口：校验 URL、抓取页面、返回图片候选。"""
    platform, normalized_url = await validate_ecommerce_url(url)
    html = await fetch_html(normalized_url)
    images = extract_images(platform, html, normalized_url)

    if not images:
        raise BadRequestException("未从该链接中解析到图片，建议截图上传")

    return {
        "platform": platform,
        "platformName": _PLATFORM_NAMES.get(platform, platform),
        "url": normalized_url,
        "images": images,
    }
