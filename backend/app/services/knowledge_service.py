"""
文档管理服务

提供文档上传、解析、向量化和存储的完整业务流程。
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
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentQueryResult,
)
from app.rag.document_parser import DocumentParserFactory
from app.rag.embedding import BGEEmbeddingModel, MilvusVectorStore


class DocumentManagementService:
    """
    文档管理服务
    
    负责文档的完整生命周期管理：
    1. 文档上传
    2. 格式解析
    3. 文本分块
    4. 向量化
    5. 存储到 Milvus
    6. 向量检索
    """
    
    def __init__(
        self,
        upload_dir: str = "/tmp/documents",
        embedding_model: Optional[BGEEmbeddingModel] = None,
        vector_store: Optional[MilvusVectorStore] = None,
    ):
        """
        初始化文档管理服务
        
        Args:
            upload_dir: 文档上传目录
            embedding_model: 向量化模型实例
            vector_store: 向量数据库实例
        """
        self.upload_dir = upload_dir
        self.parser_factory = DocumentParserFactory()
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        
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
        4. 返回上传响应
        
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
            message="文档已上传，等待处理",
        )
    
    async def process_document(self, document_id: str) -> DocumentProcessingStatus:
        """
        处理文档（解析、分块、向量化、存储）
        
        流程：
        1. 解析文档获取分块
        2. 向量化分块
        3. 存储到 Milvus
        4. 更新处理状态
        
        Args:
            document_id: 文档 ID
            
        Returns:
            DocumentProcessingStatus: 处理状态
            
        Raises:
            ValueError: 文档不存在
            RuntimeError: 处理失败
        """
        if document_id not in self.document_status:
            raise ValueError(f"文档不存在: {document_id}")
        
        doc_info = self.document_status[document_id]
        
        try:
            # 1. 解析文档
            self._update_status(document_id, DocumentStatus.PARSING, 10)
            
            file_path = doc_info["file_path"]
            file_ext = Path(file_path).suffix.lstrip('.').lower()
            parser = self.parser_factory.get_parser(file_ext)
            
            chunks = await parser.parse(file_path, document_id)
            
            if not chunks:
                raise RuntimeError("文档解析结果为空")
            
            # 2. 分块（已在解析器中完成）
            self._update_status(document_id, DocumentStatus.CHUNKING, 30)
            
            # 3. 向量化
            self._update_status(document_id, DocumentStatus.EMBEDDING, 50)
            
            if not self.embedding_model:
                raise RuntimeError("向量化模型未初始化")
            
            # 提取分块内容
            chunk_contents = [chunk.content for chunk in chunks]
            
            # 批量向量化
            embeddings = await self.embedding_model.embed_texts(chunk_contents)
            
            # 4. 存储到 Milvus
            if self.vector_store:
                await self.vector_store.insert_chunks(chunks, embeddings)
            
            # 更新状态为已完成
            self._update_status(document_id, DocumentStatus.COMPLETED, 100)
            
            return DocumentProcessingStatus(
                document_id=document_id,
                file_name=doc_info["file_name"],
                status=DocumentStatus.COMPLETED,
                progress=100,
                total_chunks=len(chunks),
                processed_chunks=len(chunks),
                created_at=doc_info["created_at"],
                updated_at=datetime.now(),
            )
        
        except Exception as e:
            self._update_status(
                document_id,
                DocumentStatus.FAILED,
                0,
                error_message=str(e),
            )
            raise RuntimeError(f"文档处理失败: {str(e)}")
    
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
    
    async def query_documents(
        self,
        request: DocumentQueryRequest,
    ) -> DocumentQueryResponse:
        """
        查询相关文档
        
        流程：
        1. 向量化查询文本
        2. 在 Milvus 中搜索
        3. 返回结果
        
        Args:
            request: 查询请求
            
        Returns:
            DocumentQueryResponse: 查询响应
            
        Raises:
            RuntimeError: 查询失败
        """
        if not self.embedding_model or not self.vector_store:
            raise RuntimeError("向量化模型或向量数据库未初始化")
        
        try:
            # 向量化查询文本
            query_embedding = await self.embedding_model.embed_text(request.query)
            
            # 搜索相似向量
            search_results = await self.vector_store.search(
                query_embedding=query_embedding,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
            )
            
            # 构建响应
            results = [
                DocumentQueryResult(
                    chunk_id=result["chunk_id"],
                    document_id=result["document_id"],
                    file_name=self.document_status.get(
                        result["document_id"], {}
                    ).get("file_name", "unknown"),
                    content=result["content"],
                    similarity_score=result["similarity_score"],
                    metadata=result["metadata"],
                )
                for result in search_results
            ]
            
            return DocumentQueryResponse(
                query=request.query,
                results=results,
                total_count=len(results),
            )
        
        except Exception as e:
            raise RuntimeError(f"查询失败: {str(e)}")
    
    async def delete_document(self, document_id: str):
        """
        删除文档
        
        流程：
        1. 从 Milvus 删除向量
        2. 删除本地文件
        3. 清除状态记录
        
        Args:
            document_id: 文档 ID
            
        Raises:
            ValueError: 文档不存在
        """
        if document_id not in self.document_status:
            raise ValueError(f"文档不存在: {document_id}")
        
        doc_info = self.document_status[document_id]
        
        try:
            # 从 Milvus 删除
            if self.vector_store:
                await self.vector_store.delete_by_document_id(document_id)
            
            # 删除本地文件
            file_path = doc_info["file_path"]
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # 清除状态记录
            del self.document_status[document_id]
        
        except Exception as e:
            raise RuntimeError(f"删除文档失败: {str(e)}")
    
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


# Backward compatibility for existing imports in the container.
KnowledgeService = DocumentManagementService
