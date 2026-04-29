"""
LangChain 标准 RAG 文档处理流程

Markdown: QMDMarkdownChunker（标题分节 + 滑动窗口）
其他格式: LangChain DocumentLoader + RecursiveCharacterTextSplitter
"""
import json
import os
import re
import hashlib
import logging
from pathlib import Path
from typing import List, Tuple
from langchain_core.documents import Document

from app.rag.query_constraints import extract_catalog_attributes

logger = logging.getLogger(__name__)

HEAVY_METADATA_KEYS = {
    'text_as_html',
    'image_base64',
    'orig_elements',
    'coordinates',
}
MAX_METADATA_VALUE_BYTES = 4 * 1024
MAX_METADATA_TOTAL_BYTES = 8 * 1024
PRODUCT_TITLE_PATTERN = re.compile(
    r"^\s*#+\s*(?P<name>[^()\n（]+?)\s*[（(](?P<sku>[^()（）\n]+)[)）]",
    re.MULTILINE,
)


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode('utf-8', errors='ignore')


def sanitize_metadata(metadata: dict) -> dict:
    """
    Drop loader-specific large payloads so split documents stay insertable in
    Milvus and metadata remains useful for retrieval/debugging.
    """
    if not metadata:
        return {}

    cleaned = {}
    total_bytes = 2

    for key, value in metadata.items():
        if value is None or key in HEAVY_METADATA_KEYS:
            continue

        if isinstance(value, (str, int, float, bool)):
            normalized = value
        else:
            normalized = json.dumps(value, ensure_ascii=False, default=str)

        key_str = str(key)
        key_bytes = len(key_str.encode('utf-8'))

        if isinstance(normalized, str):
            normalized = _truncate_utf8(normalized, MAX_METADATA_VALUE_BYTES)
            value_bytes = len(normalized.encode('utf-8'))
        else:
            value_bytes = len(str(normalized).encode('utf-8'))

        if total_bytes + key_bytes + value_bytes > MAX_METADATA_TOTAL_BYTES:
            continue

        cleaned[key_str] = normalized
        total_bytes += key_bytes + value_bytes

    return cleaned


# ---------------------------------------------------------------------------
# TextCleaner
# ---------------------------------------------------------------------------

class TextCleaner:
    @staticmethod
    def clean(text: str) -> str:
        if not text:
            return ''
        text = re.sub(r'\s+', ' ', text)
        text = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @staticmethod
    def clean_markdown(text: str) -> str:
        if not text:
            return ''
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)          # 去 HTML 标签
        text = re.sub(r'\n{4,}', '\n\n\n', text)   # 最多3个连续换行
        text = '\n'.join(line.rstrip() for line in text.split('\n'))
        return text.strip()


# ---------------------------------------------------------------------------
# QMDMarkdownChunker - Query-aligned Markdown Decomposition
# ---------------------------------------------------------------------------

class QMDMarkdownChunker:
    """
    QMD (Query-aligned Markdown Decomposition) 分块算法

    核心思想：结构感知的加权断点选择
    - 扫描全文，识别所有候选断点并赋基础分数
    - 当文本接近目标长度时，在截止点前 window 字符内搜索候选断点
    - 用公式选出最优切点：finalScore = baseScore × (1 - (distance/window)² × 0.7)
    - 越靠近目标长度惩罚越小，结构价值高（如H1）即使稍远也能胜出

    断点优先级（baseScore）：
      H1=100, H2=90, H3=80, H4=70, H5=60, H6=50
      代码块边界=80, 分隔线=60, 空行=20, 列表项=5, 普通换行=1
    """

    # 断点模式及基础分数
    BREAKPOINT_PATTERNS = [
        (re.compile(r'^# .+$',    re.MULTILINE), 100),  # H1
        (re.compile(r'^## .+$',   re.MULTILINE),  90),  # H2
        (re.compile(r'^### .+$',  re.MULTILINE),  80),  # H3
        (re.compile(r'^#### .+$', re.MULTILINE),  70),  # H4
        (re.compile(r'^##### .+$',re.MULTILINE),  60),  # H5
        (re.compile(r'^#{6} .+$', re.MULTILINE),  50),  # H6
        (re.compile(r'^```',      re.MULTILINE),  80),  # 代码块边界
        (re.compile(r'^[-*]{3,}$',re.MULTILINE),  60),  # 分隔线
        (re.compile(r'\n\n',               re.MULTILINE),  20),  # 空行
        (re.compile(r'^[-*+] .+$',re.MULTILINE),   5),  # 无序列表项
        (re.compile(r'^\d+\. .+$',re.MULTILINE),   5),  # 有序列表项
        (re.compile(r'\n',                 re.MULTILINE),   1),  # 普通换行
    ]
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

    def __init__(self, chunk_size: int = 900, window: int = 200, min_chunk_size: int = 100):
        self.chunk_size = chunk_size
        self.window = window
        self.min_chunk_size = min_chunk_size

    def split_documents(self, documents: List[Document]) -> List[Document]:
        result = []
        for doc in documents:
            result.extend(self._split_one(doc))
        return result

    def _split_one(self, doc: Document) -> List[Document]:
        text = doc.page_content
        base_meta = sanitize_metadata(dict(doc.metadata))
        chunks = []
        chunk_index = 0

        # 先按当前文档里最高层级标题切成 section，避免整份商品资料总说明和具体商品正文落在同一个 chunk。
        for section_title, section_text in self._split_semantic_sections(text):
            section_chunks = self._split_section(section_text, base_meta, chunk_index, section_title)
            chunks.extend(section_chunks)
            chunk_index += len(section_chunks)

        return chunks

    def _split_section(
        self,
        text: str,
        base_meta: dict,
        start_index: int,
        section_title: str,
    ) -> List[Document]:
        breakpoints = self._scan_breakpoints(text)
        chunks: List[Document] = []
        pos = 0
        chunk_index = start_index

        while pos < len(text):
            target = pos + self.chunk_size

            if target >= len(text):
                chunk_text = text[pos:]
                if len(chunk_text.strip()) >= self.min_chunk_size:
                    subsection_title = self._extract_title(chunk_text)
                    chunks.append(
                        self._make_doc(
                            chunk_text,
                            base_meta,
                            chunk_index,
                            'end',
                            section_title=section_title,
                            subsection_title=subsection_title,
                        )
                    )
                    chunk_index += 1
                break

            window_start = max(pos, target - self.window)
            best_pos, best_score, best_type = target, 0.0, 'forced'

            for bp_pos, bp_score, bp_type in breakpoints:
                if bp_pos <= pos:
                    continue
                if bp_pos < window_start:
                    continue
                if bp_pos > target:
                    break
                distance = target - bp_pos
                ratio = distance / self.window if self.window > 0 else 1.0
                final_score = bp_score * (1.0 - (ratio ** 2) * 0.7)
                if final_score > best_score:
                    best_score = final_score
                    best_pos = bp_pos
                    best_type = bp_type

            chunk_text = text[pos:best_pos]
            if len(chunk_text.strip()) >= self.min_chunk_size:
                subsection_title = self._extract_title(chunk_text)
                chunks.append(
                    self._make_doc(
                        chunk_text,
                        base_meta,
                        chunk_index,
                        best_type,
                        section_title=section_title,
                        subsection_title=subsection_title,
                    )
                )
                chunk_index += 1

            pos = best_pos

        return chunks

    def _split_semantic_sections(self, text: str) -> List[Tuple[str, str]]:
        headings = list(self.HEADING_PATTERN.finditer(text))
        if not headings:
            return [('', text)]

        primary_level = min(len(match.group(1)) for match in headings)
        primary_headings = [match for match in headings if len(match.group(1)) == primary_level]
        if not primary_headings:
            return [('', text)]

        sections: List[Tuple[str, str]] = []
        preamble = text[:primary_headings[0].start()].strip()
        if preamble:
            sections.append((self._extract_title(preamble), preamble))

        for index, match in enumerate(primary_headings):
            start = match.start()
            end = primary_headings[index + 1].start() if index + 1 < len(primary_headings) else len(text)
            section_text = text[start:end].strip()
            if section_text:
                sections.append((match.group(0).strip(), section_text))

        return sections or [('', text)]

    def _scan_breakpoints(self, text: str):
        """
        扫描全文，返回所有候选断点列表：[(position, base_score, type_name), ...]
        按 position 排序
        """
        bp_map = {}  # position -> (score, type)
        for pattern, score in self.BREAKPOINT_PATTERNS:
            type_name = f'score_{score}'
            for m in pattern.finditer(text):
                p = m.start()
                if p not in bp_map or score > bp_map[p][0]:
                    bp_map[p] = (score, type_name)
        return sorted([(p, v[0], v[1]) for p, v in bp_map.items()])

    def _extract_title(self, text: str) -> str:
        """提取文本块中第一个标题行"""
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                return line
        return ''

    def _make_doc(
        self,
        text: str,
        base_meta: dict,
        idx: int,
        cut_at: str,
        section_title: str = '',
        subsection_title: str = '',
    ) -> Document:
        chunk_id = hashlib.md5(text.encode()).hexdigest()[:16]
        title_source = section_title or subsection_title or text
        title_match = PRODUCT_TITLE_PATTERN.search(title_source)
        catalog_attributes = extract_catalog_attributes(text, base_meta)
        meta = {
            **base_meta,
            'chunk_id': chunk_id,
            'chunk_index': idx,
            'cut_at': cut_at,
            'section_title': section_title,
            'subsection_title': subsection_title,
            # 把商品名 / SKU 写回 chunk metadata，后面的 BM25、向量和混合排序都可以直接复用。
            'product_name': title_match.group('name').strip() if title_match else '',
            'sku': title_match.group('sku').strip() if title_match else '',
            # 价带、类目、商品类型这些结构化信号会参与后续检索排序，不能只埋在正文里。
            'category': catalog_attributes.get('category', ''),
            'audience': catalog_attributes.get('audience', ''),
            'product_type': catalog_attributes.get('product_type', ''),
            'price_band_text': catalog_attributes.get('price_band_text', ''),
            'price_band_low': catalog_attributes.get('price_band_low', ''),
            'price_band_high': catalog_attributes.get('price_band_high', ''),
        }
        return Document(page_content=text, metadata=meta)


# ---------------------------------------------------------------------------
# DocumentLoader 工厂
# ---------------------------------------------------------------------------

def get_loader(file_path: str):
    ext = Path(file_path).suffix.lower()
    if ext == '.pdf':
        from langchain_community.document_loaders import PyPDFLoader
        return PyPDFLoader(file_path)
    elif ext in ('.xlsx', '.xls'):
        from langchain_community.document_loaders import UnstructuredExcelLoader
        return UnstructuredExcelLoader(file_path, mode='elements')
    elif ext == '.docx':
        from langchain_community.document_loaders import Docx2txtLoader
        return Docx2txtLoader(file_path)
    elif ext in ('.md', '.txt'):
        from langchain_community.document_loaders import TextLoader
        return TextLoader(file_path, encoding='utf-8')
    elif ext == '.csv':
        from langchain_community.document_loaders import CSVLoader
        return CSVLoader(file_path, encoding='utf-8')
    else:
        raise ValueError(f'Unsupported: {ext}')


# ---------------------------------------------------------------------------
# 单文件加载 + 分块
# ---------------------------------------------------------------------------

def load_and_split(
    file_path: str,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
) -> List[Document]:
    """
    加载单个文件，按类型选择分块策略：
    - .md  → QMDMarkdownChunker（标题分节 + 滑动窗口）
    - 其他 → RecursiveCharacterTextSplitter
    """
    ext = Path(file_path).suffix.lower()
    source_file = os.path.basename(file_path)

    raw_docs = get_loader(file_path).load()
    for doc in raw_docs:
        doc.metadata = sanitize_metadata({
            **dict(doc.metadata),
            'source_file': source_file,
            'format': ext.lstrip('.'),
        })

    if ext == '.md':
        for doc in raw_docs:
            doc.page_content = TextCleaner.clean_markdown(doc.page_content)
        child_docs = QMDMarkdownChunker(
            chunk_size=chunk_size, window=chunk_overlap, min_chunk_size=100
        ).split_documents(raw_docs)
    else:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        child_docs = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            separators=['\n\n', '\n', '\u3002', '\uff01', '\uff1f', '\uff1b', '.', '!', '?', ';', ' ', ''],
        ).split_documents(raw_docs)

    for i, doc in enumerate(child_docs):
        metadata = sanitize_metadata(dict(doc.metadata))
        if 'chunk_id' not in metadata:
            metadata['chunk_id'] = hashlib.md5(doc.page_content.encode()).hexdigest()[:16]
        metadata.setdefault('chunk_index', i)
        metadata.setdefault('source_file', source_file)
        doc.metadata = metadata

    logger.info('load_and_split: %s → %d chunks', source_file, len(child_docs))
    return child_docs


# ---------------------------------------------------------------------------
# 父子分块
# ---------------------------------------------------------------------------

def load_with_parent_child(
    file_path: str,
    parent_chunk_size: int = 1500,
    child_chunk_size: int = 512,
    chunk_overlap: int = 128,
) -> Tuple[List[Document], List[Document]]:
    """
    父子分块：父块(大)给 LLM 上下文，子块(小)用于向量检索
    子块 metadata 含 parent_id
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    ext = Path(file_path).suffix.lower()
    source_file = os.path.basename(file_path)

    raw_docs = get_loader(file_path).load()
    for doc in raw_docs:
        doc.metadata = sanitize_metadata({
            **dict(doc.metadata),
            'source_file': source_file,
            'format': ext.lstrip('.'),
        })

    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap,
        separators=['\n\n', '\n', '\u3002', '.', ' ', ''],
    )
    parent_docs = parent_splitter.split_documents(raw_docs)
    for p_idx, p in enumerate(parent_docs):
        metadata = sanitize_metadata(dict(p.metadata))
        metadata['chunk_id'] = hashlib.md5(p.page_content.encode()).hexdigest()[:16]
        metadata['chunk_type'] = 'parent'
        metadata['chunk_index'] = p_idx
        p.metadata = metadata

    if ext == '.md':
        child_splitter = QMDMarkdownChunker(chunk_size=child_chunk_size, window=chunk_overlap)
        split_fn = child_splitter.split_documents
    else:
        _cs = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size, chunk_overlap=chunk_overlap,
            separators=['\n\n', '\n', '\u3002', '.', ' ', ''],
        )
        split_fn = _cs.split_documents

    child_docs = []
    for parent in parent_docs:
        parent_id = parent.metadata['chunk_id']
        children = split_fn([parent])
        for c_idx, child in enumerate(children):
            child_id = hashlib.md5(child.page_content.encode()).hexdigest()[:16]
            metadata = sanitize_metadata(dict(child.metadata))
            metadata.update({
                'chunk_id': child_id, 'parent_id': parent_id,
                'chunk_type': 'child', 'chunk_index': c_idx,
            })
            child.metadata = metadata
            child_docs.append(child)

    logger.info('parent-child: %s → %d parents %d children', source_file, len(parent_docs), len(child_docs))
    return parent_docs, child_docs


# ---------------------------------------------------------------------------
# 目录批量处理
# ---------------------------------------------------------------------------

def load_directory(
    directory: str,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    use_parent_child: bool = False,
) -> Tuple[List[Document], List[Document]]:
    """批量加载目录下所有支持的文件，返回 (child_docs, parent_docs)"""
    supported = {'.pdf', '.xlsx', '.xls', '.docx', '.md', '.csv', '.txt'}
    all_child, all_parent = [], []
    stats = {'total': 0, 'ok': 0, 'fail': 0}

    for fp in sorted(Path(directory).rglob('*')):
        if fp.suffix.lower() not in supported:
            continue
        stats['total'] += 1
        try:
            if use_parent_child:
                parents, children = load_with_parent_child(
                    str(fp), parent_chunk_size=1500,
                    child_chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                )
                all_parent.extend(parents)
                all_child.extend(children)
            else:
                chunks = load_and_split(str(fp), chunk_size, chunk_overlap)
                all_child.extend(chunks)
            stats['ok'] += 1
        except Exception as e:
            logger.error('Failed %s: %s', fp.name, e)
            stats['fail'] += 1

    logger.info('load_directory: total=%d ok=%d fail=%d child_chunks=%d',
                stats['total'], stats['ok'], stats['fail'], len(all_child))
    return all_child, all_parent
