"""
文档上传和解析服务（简化版）

只负责：
1. 文档上传
2. 格式解析
3. 文本分块

不包含向量化和存储功能。
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from app.schemas.document import (
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentStatus,
    DocumentProcessingStatus,
    DocumentParseResult,
)
from app.rag.document_parser import DocumentParserFactory


class DocumentUploadService:
    """
    文档上传和解析服务
    
    功能：
    1. 接收文档上传
    2. 解析文档格式（CSV、Excel 等）
    3. 文本分块
    """
    
    def __init__(self, upload_dir: str = "./data/uploads"):
        """
        初始化文档上传服务
        
        Args:
            upload_dir: 文档上传目录
        """
        self.upload_dir = upload_dir
        self.parser_factory = DocumentParserFactory()
        
        # 创建上传目录
        Path(upload_dir).mkdir(parents=True, exist_ok=True)
        
        # 文档状态跟踪（实际应该用数据库）
        self.document_status = {}
    
    async def upload_document(
        self,
        file_content: bytes,
        request: DocumentUploadRequest,
    ) -> DocumentUploadResponse:
        """
        上传文档
        
        流程：
        1. 生成文档 ID
        2. 保存文件到本地
        3. 初始化处理状态
        
        Args:
            file_content: 文件内容（字节）
            request: 上传请求
            
        Returns:
            DocumentUploadResponse: 上传响应
            
        Raises:
            ValueError: 文件类型不支持
        """
        # 生成文档 ID
        document_id = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 验证文件类型
        file_ext = Path(request.file_name).suffix.lstrip('.').lower()
        if file_ext not in self.parser_factory.get_supported_types():
            raise ValueError(f"不支持的文件类型: {file_ext}")
        
        # 保存文件
        file_path = os.path.join(self.upload_dir, f"{document_id}_{request.file_name}")
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        # 初始化处理状态
        self.document_status[document_id] = {
            "file_name": request.file_name,
            "file_path": file_path,
            "doc_type": request.doc_type,
            "category": request.category,
            "description": request.description,
            "status": DocumentStatus.PENDING,
            "progress": 0,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        
        return DocumentUploadResponse(
            document_id=document_id,
            file_name=request.file_name,
            status=DocumentStatus.PENDING,
            created_at=datetime.now(),
            message="文档已上传，等待解析",
        )
    
    async def parse_document(self, document_id: str) -> DocumentParseResult:
        """
        解析文档（只做解析和分块，不做向量化）
        
        流程：
        1. 根据文件类型选择解析器
        2. 解析文档获取分块
        3. 返回解析结果
        
        Args:
            document_id: 文档 ID
            
        Returns:
            DocumentParseResult: 解析结果
            
        Raises:
            ValueError: 文档不存在
            RuntimeError: 解析失败
        """
        if document_id not in self.document_status:
            raise ValueError(f"文档不存在: {document_id}")
        
        doc_info = self.document_status[document_id]
        
        try:
            # 更新状态为解析中
            self._update_status(document_id, DocumentStatus.PARSING, 30)
            
            # 获取文件路径和类型
            file_path = doc_info["file_path"]
            file_ext = Path(file_path).suffix.lstrip('.').lower()
            
            # 获取对应的解析器
            parser = self.parser_factory.get_parser(file_ext)
            
            # 解析文档
            chunks = await parser.parse(file_path, document_id)
            
            if not chunks:
                raise RuntimeError("文档解析结果为空")
            
            # 计算总 token 数
            total_tokens = sum(chunk.token_count for chunk in chunks)
            
            # 更新状态为已完成
            self._update_status(document_id, DocumentStatus.COMPLETED, 100)
            doc_info["total_chunks"] = len(chunks)
            doc_info["processed_chunks"] = len(chunks)
            
            # 返回解析结果
            return DocumentParseResult(
                document_id=document_id,
                file_name=doc_info["file_name"],
                doc_type=doc_info["doc_type"],
                total_chunks=len(chunks),
                total_tokens=total_tokens,
                chunks=chunks,
                metadata={
                    "category": doc_info["category"],
                    "description": doc_info["description"],
                    "parsed_at": datetime.now().isoformat(),
                },
            )
        
        except Exception as e:
            self._update_status(
                document_id,
                DocumentStatus.FAILED,
                0,
                error_message=str(e),
            )
            raise RuntimeError(f"文档解析失败: {str(e)}")
    
    async def get_document_status(self, document_id: str) -> DocumentProcessingStatus:
        """
        获取文档处理状态
        
        Args:
            document_id: 文档 ID
            
        Returns:
            DocumentProcessingStatus: 处理状态
            
        Raises:
            ValueError: 文档不存在
        """
        if document_id not in self.document_status:
            raise ValueError(f"文档不存在: {document_id}")
        
        doc_info = self.document_status[document_id]
        
        return DocumentProcessingStatus(
            document_id=document_id,
            file_name=doc_info["file_name"],
            status=doc_info["status"],
            progress=doc_info["progress"],
            total_chunks=doc_info.get("total_chunks"),
            processed_chunks=doc_info.get("processed_chunks"),
            error_message=doc_info.get("error_message"),
            created_at=doc_info["created_at"],
            updated_at=doc_info["updated_at"],
        )
    
    def _update_status(
        self,
        document_id: str,
        status: DocumentStatus,
        progress: int,
        error_message: Optional[str] = None,
    ):
        """
        更新文档处理状态
        
        Args:
            document_id: 文档 ID
            status: 新状态
            progress: 进度（0-100）
            error_message: 错误信息
        """
        if document_id in self.document_status:
            self.document_status[document_id]["status"] = status
            self.document_status[document_id]["progress"] = progress
            self.document_status[document_id]["updated_at"] = datetime.now()
            if error_message:
                self.document_status[document_id]["error_message"] = error_message
