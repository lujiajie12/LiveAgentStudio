"""
文档上传和解析 API 接口

提供文档上传、解析、状态查询等 REST API 端点。
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from typing import Optional

from app.schemas.document import (
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentProcessingStatus,
    DocumentParseResult,
)
from app.services.document_upload_service import DocumentUploadService

# 创建路由
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# 全局服务实例（实际应该通过依赖注入）
upload_service: Optional[DocumentUploadService] = None


def set_upload_service(service: DocumentUploadService):
    """设置文档上传服务实例"""
    global upload_service
    upload_service = service


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    summary="上传文档",
    description="上传知识库文档（支持 CSV、Excel、TXT、Markdown）",
)
async def upload_document(
    file: UploadFile = File(...),
    category: str = "general",
    description: Optional[str] = None,
):
    """
    上传文档接口
    
    流程：
    1. 接收文件上传
    2. 验证文件类型
    3. 保存文件到本地
    4. 返回文档 ID
    
    Args:
        file: 上传的文件
        category: 文档分类（如 product_info, faq 等）
        description: 文档描述
        
    Returns:
        DocumentUploadResponse: 上传响应，包含文档 ID
        
    Raises:
        HTTPException: 上传失败
        
    Example:
        ```
        POST /api/v1/documents/upload
        Content-Type: multipart/form-data
        
        file: <binary>
        category: product_info
        description: 商品详情数据
        ```
    """
    if not upload_service:
        raise HTTPException(status_code=500, detail="文档服务未初始化")
    
    try:
        # 读取文件内容
        file_content = await file.read()
        
        # 创建上传请求
        upload_request = DocumentUploadRequest(
            file_name=file.filename,
            doc_type=file.filename.split('.')[-1].lower(),
            category=category,
            description=description,
        )
        
        # 上传文档
        response = await upload_service.upload_document(file_content, upload_request)
        
        return response
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.post(
    "/parse/{document_id}",
    response_model=DocumentParseResult,
    summary="解析文档",
    description="解析已上传的文档，进行格式转换和文本分块",
)
async def parse_document(document_id: str):
    """
    解析文档接口
    
    流程：
    1. 根据文件类型选择解析器
    2. 解析文档内容
    3. 进行文本分块
    4. 返回分块结果
    
    Args:
        document_id: 文档 ID（由上传接口返回）
        
    Returns:
        DocumentParseResult: 解析结果，包含所有分块
        
    Raises:
        HTTPException: 解析失败
        
    Example:
        ```
        POST /api/v1/documents/parse/doc_20260316_001
        ```
    """
    if not upload_service:
        raise HTTPException(status_code=500, detail="文档服务未初始化")
    
    try:
        result = await upload_service.parse_document(document_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@router.get(
    "/status/{document_id}",
    response_model=DocumentProcessingStatus,
    summary="查询文档处理状态",
    description="查询文档的处理进度和状态",
)
async def get_document_status(document_id: str):
    """
    查询文档处理状态接口
    
    Args:
        document_id: 文档 ID
        
    Returns:
        DocumentProcessingStatus: 处理状态
        
    Raises:
        HTTPException: 文档不存在或查询失败
        
    Example:
        ```
        GET /api/v1/documents/status/doc_20260316_001
        ```
    """
    if not upload_service:
        raise HTTPException(status_code=500, detail="文档服务未初始化")
    
    try:
        status = await upload_service.get_document_status(document_id)
        return status
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get(
    "/supported-types",
    summary="获取支持的文件类型",
    description="获取系统支持的所有文档格式",
)
async def get_supported_types():
    """
    获取支持的文件类型接口
    
    Returns:
        dict: 支持的文件类型列表
        
    Example:
        ```
        GET /api/v1/documents/supported-types
        
        Response:
        {
            "supported_types": ["csv", "excel", "xlsx", "xls", "txt", "markdown", "md"],
            "count": 7
        }
        ```
    """
    if not upload_service:
        raise HTTPException(status_code=500, detail="文档服务未初始化")
    
    try:
        supported_types = upload_service.parser_factory.get_supported_types()
        return {
            "supported_types": supported_types,
            "count": len(supported_types),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")
