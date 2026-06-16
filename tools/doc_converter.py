#=======================================================================================
#.       tools/doc_converter.py — Office 文档 → PDF 转换器
#.       使用 LibreOffice headless 模式将 Microsoft Office 文档转为 PDF，
#.       方便 Gemini 多模态模型读取（Gemini 原生支持 PDF 但不支持 .docx 等）。
#.
#.       支持格式: .docx .doc .pptx .ppt .xlsx .xls
#.       依赖: brew install libreoffice（macOS）
#.               apt install libreoffice（Linux）
#.
#.       提供两个版本：
#.         convert_to_pdf()       — 转换并保存为本地 PDF 文件，返回路径
#.         convert_to_pdf_bytes() — 转换并返回 PDF bytes（不保留本地文件）
#.
#.       被 bot/handlers.py 的 handle_reply() 在处理 Office 文档回复时调用。
#=======================================================================================

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

#=============================================================
#.       _OFFICE_EXT — 支持的 Office 文档后缀集合
#.       _LABELS    — 后缀 → 人类可读格式名称
#=============================================================
_OFFICE_EXT = {".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"}
_LABELS = {
    ".docx": "Word", ".doc": "Word",
    ".pptx": "PPT", ".ppt": "PPT",
    ".xlsx": "Excel", ".xls": "Excel",
}


#=============================================================
#.       convert_to_pdf() — 转换 Office 文档并保存为本地 PDF 文件
#.       参数：
#.         file_bytes — 文件二进制内容
#.         filename   — 原始文件名（用于提取扩展名和输出文件名）
#.       返回：成功返回 PDF 文件路径 (str)，失败返回 None
#.       注意：生成的 PDF 保存在当前工作目录下
#=============================================================
def convert_to_pdf(file_bytes: bytes, filename: str) -> str | None:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _OFFICE_EXT:
        return None

    # 将文件内容写入临时文件（保留原始后缀，LibreOffice 需要后缀判断格式）
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    out_dir = os.getcwd()
    base = os.path.splitext(filename)[0]
    pdf_path = os.path.join(out_dir, f"{base}.pdf")

    try:
        # 调用 LibreOffice headless 模式转换
        _run_soffice(tmp_path, out_dir)

        # LibreOffice 输出文件名基于临时文件名，需重命名为原始文件名
        lo_output = os.path.join(
            out_dir, f"{os.path.splitext(os.path.basename(tmp_path))[0]}.pdf"
        )
        if os.path.exists(lo_output):
            if lo_output != pdf_path:
                os.replace(lo_output, pdf_path)
            size = os.path.getsize(pdf_path)
            logger.info(f"转换完成: {filename} → {pdf_path} ({size}B)")
            return pdf_path
        else:
            logger.error(f"转换后未找到 PDF: {lo_output}")
            return None

    except FileNotFoundError:
        logger.error("LibreOffice 未安装，请运行: brew install libreoffice")
        return None
    except subprocess.TimeoutExpired:
        logger.error("LibreOffice 转换超时")
        return None
    except Exception as e:
        logger.error(f"转换异常: {e}")
        return None
    finally:
        # 清理临时源文件
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


#=============================================================
#.       convert_to_pdf_bytes() — 转换 Office 文档并返回 PDF bytes
#.       与 convert_to_pdf() 功能相同，但不保留本地文件。
#.       转换完成后立即读取 PDF 内容到内存，然后清理临时文件。
#.       参数同上，返回：成功返回 bytes，失败返回 None
#.       被 bot/handlers.py handle_reply() 直接调用以便传给 Gemini。
#=============================================================
def convert_to_pdf_bytes(file_bytes: bytes, filename: str) -> bytes | None:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _OFFICE_EXT:
        return None

    # 写入临时源文件
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as src:
        src.write(file_bytes)
        src_path = src.name

    # 创建临时输出目录（避免与当前目录其他文件冲突）
    tmp_dir = tempfile.mkdtemp()

    try:
        _run_soffice(src_path, tmp_dir)

        # LibreOffice 输出文件名 = 源文件名（不含扩展名）+ .pdf
        pdf_name = f"{os.path.splitext(os.path.basename(src_path))[0]}.pdf"
        pdf_path = os.path.join(tmp_dir, pdf_name)

        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                data = f.read()
            logger.info(f"转换完成: {filename} → {len(data)}B (in-memory)")
            return data
        else:
            logger.error(f"转换后未找到 PDF: {pdf_path}")
            return None

    except FileNotFoundError:
        logger.error("LibreOffice 未安装，请运行: brew install libreoffice")
        return None
    except subprocess.TimeoutExpired:
        logger.error("LibreOffice 转换超时")
        return None
    except Exception as e:
        logger.error(f"转换异常: {e}")
        return None
    finally:
        # 清理临时源文件和输出目录
        try:
            os.unlink(src_path)
        except Exception:
            pass
        try:
            import shutil
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


#=============================================================
#.       _run_soffice() — 内部函数：执行 LibreOffice headless 命令
#.       参数：
#.         src_path — 源文件绝对路径
#.         out_dir  — 输出目录
#.       超时时间 120 秒（大文件转换可能需要较长时间）
#.       转换失败抛出 RuntimeError。
#=============================================================
def _run_soffice(src_path: str, out_dir: str) -> None:
    result = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, src_path],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice 失败: {result.stderr}")
