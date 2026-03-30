"""
RAG 知识库管理模块

功能：
- 文档上传和管理
- 文档格式解析（CSV、Excel、PDF 等）
- 文本分块处理
- 向量化嵌入（使用 BGE-v1.5）
- Milvus 向量数据库操作
"""

from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """文档类型枚举"""
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"
    TXT = "txt"
    MARKDOWN = "markdown"


class DocumentStatus(str, Enum):
    """文档处理状态"""
    PENDING = "pending"  # 待处理
    PARSING = "parsing"  # 解析中
    CHUNKING = "chunking"  # 分块中
    EMBEDDING = "embedding"  # 向量化中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class DocumentUploadRequest(BaseModel):
    """文档上传请求"""
    file_name: str = Field(..., description="文件名")
    doc_type: DocumentType = Field(..., description="文档类型")
    category: str = Field(..., description="文档分类，如 product_info, faq, promotion_rule")
    description: Optional[str] = Field(None, description="文档描述")
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_name": "products.csv",
                "doc_type": "csv",
                "category": "product_info",
                "description": "商品详情数据"
            }
        }


class DocumentChunk(BaseModel):
    """文档分块"""
    chunk_id: str = Field(..., description="分块 ID")
    document_id: str = Field(..., description="所属文档 ID")
    chunk_index: int = Field(..., description="分块序号")
    content: str = Field(..., description="分块内容")
    token_count: int = Field(..., description="Token 数量")
    metadata: dict = Field(default_factory=dict, description="元数据")


class DocumentParseResult(BaseModel):
    """文档解析结果"""
    document_id: str = Field(..., description="文档 ID")
    file_name: str = Field(..., description="文件名")
    doc_type: DocumentType = Field(..., description="文档类型")
    total_chunks: int = Field(..., description="总分块数")
    total_tokens: int = Field(..., description="总 Token 数")
    chunks: List[DocumentChunk] = Field(..., description="分块列表")
    metadata: dict = Field(default_factory=dict, description="文档元数据")


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""
    document_id: str = Field(..., description="文档 ID")
    file_name: str = Field(..., description="文件名")
    status: DocumentStatus = Field(..., description="处理状态")
    created_at: datetime = Field(..., description="创建时间")
    message: str = Field(..., description="状态消息")
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "doc_20260316_001",
                "file_name": "products.csv",
                "status": "pending",
                "created_at": "2026-03-16T10:30:00",
                "message": "文档已上传，等待处理"
            }
        }


class DocumentProcessingStatus(BaseModel):
    """文档处理状态查询"""
    document_id: str = Field(..., description="文档 ID")
    file_name: str = Field(..., description="文件名")
    status: DocumentStatus = Field(..., description="当前状态")
    progress: int = Field(..., description="处理进度（0-100）")
    total_chunks: Optional[int] = Field(None, description="总分块数")
    processed_chunks: Optional[int] = Field(None, description="已处理分块数")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class DocumentQueryRequest(BaseModel):
    """文档查询请求"""
    query: str = Field(..., description="查询文本")
    top_k: int = Field(default=5, description="返回结果数")
    score_threshold: float = Field(default=0.5, description="相似度阈值")
    category: Optional[str] = Field(None, description="文档分类过滤")


class DocumentQueryResult(BaseModel):
    """文档查询结果"""
    chunk_id: str = Field(..., description="分块 ID")
    document_id: str = Field(..., description="文档 ID")
    file_name: str = Field(..., description="文件名")
    content: str = Field(..., description="分块内容")
    similarity_score: float = Field(..., description="相似度分数")
    metadata: dict = Field(default_factory=dict, description="元数据")


class DocumentQueryResponse(BaseModel):
    """文档查询响应"""
    query: str = Field(..., description="查询文本")
    results: List[DocumentQueryResult] = Field(..., description="查询结果")
    total_count: int = Field(..., description="结果总数")
