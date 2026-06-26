"""研报 PDF 下载。"""
import re
from pathlib import Path

from py.a_stock_data._common import em_get, UA


PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


def download_pdf(record: dict, target_dir: str = "./reports") -> str | None:
    """下载单份研报PDF，返回保存路径或None"""
    info_code = record.get("infoCode", "")
    if not info_code:
        return None
    date = (record.get("publishDate") or "")[:10]
    org = record.get("orgSName") or "未知"
    title = re.sub(r'[\\/:*?"<>|]', "_", record.get("title", ""))[:80]
    fname = f"{date}_{org}_{title}.pdf"
    target = Path(target_dir) / fname
    if target.exists():
        return str(target)
    url = PDF_TPL.format(info_code=info_code)
    r = em_get(url, headers={"Referer": "https://data.eastmoney.com/"}, timeout=60)
    if r.status_code == 200 and len(r.content) >= 1024:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(r.content)
        return str(target)
    return None