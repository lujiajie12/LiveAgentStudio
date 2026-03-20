"""
端到端知识库构建测试脚本
"""
import sys
import os
from pathlib import Path

# 添加 RAG 模块路径
rag_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'rag')
sys.path.insert(0, rag_path)

from data_readers import DataReaderFactory
from document_processor import DocumentProcessor
from offline_pipeline import OfflineKnowledgeBasePipeline
from storage_pipeline import VectorizationPipeline


def demonstrate_workflow():
    """演示完整工作流"""
    print("\n" + "="*80)
    print("知识库构建完整工作流演示")
    print("="*80)
    
    data_dir = r"D:\Desktop\LiveAgentStudio\docs\data"
    output_dir = r"D:\Desktop\LiveAgentStudio\backend\kb_output"
    
    print("\n步骤 1: 初始化管道")
    pipeline = OfflineKnowledgeBasePipeline(output_dir=output_dir)
    print("✓ 管道已初始化")
    
    print("\n步骤 2: 处理文档")
    chunks = pipeline.process_directory(data_dir)
    print(f"✓ 处理完成，生成 {len(chunks)} 个块")
    
    if chunks:
        print("\n步骤 3: 保存块")
        json_file = pipeline.save_chunks_to_json(chunks)
        jsonl_file = pipeline.save_chunks_to_jsonl(chunks)
        print(f"✓ 已保存到:")
        print(f"  - {json_file}")
        print(f"  - {jsonl_file}")
        
        print("\n步骤 4: 向量化")
        vec_pipeline = VectorizationPipeline()
        embeddings = vec_pipeline.vectorize_chunks(chunks)
        print(f"✓ 向量化完成，生成 {len(embeddings)} 个向量")
        
        print("\n步骤 5: 统计信息")
        pipeline.print_statistics()
        
        print("\n样本块信息:")
        for i, chunk in enumerate(chunks[:2]):
            print(f"\n块 {i+1}:")
            print(f"  - 文件: {chunk.source_file}")
            print(f"  - 内容: {chunk.content[:100]}...")
    
    print("\n✓ 工作流完成！")


if __name__ == '__main__':
    demonstrate_workflow()
