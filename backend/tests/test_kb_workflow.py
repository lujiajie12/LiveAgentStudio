# -*- coding: utf-8 -*-
import sys, os
rag_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'rag')
sys.path.insert(0, rag_path)
from data_readers import DataReaderFactory
from offline_pipeline import OfflineKnowledgeBasePipeline

def main():
    print('='*80)
    print('Knowledge Base Building Workflow')
    print('='*80)
    data_dir = r'D:\Desktop\LiveAgentStudio\docs\data'
    output_dir = r'D:\Desktop\LiveAgentStudio\backend\kb_output'
    print('[Step 1] Initialize pipeline...')
    pipeline = OfflineKnowledgeBasePipeline(output_dir=output_dir)
    print('[OK] Pipeline initialized')
    print('[Step 2] Process documents...')
    chunks = pipeline.process_directory(data_dir)
    print(f'[OK] Generated {len(chunks)} chunks')
    if chunks:
        json_file = pipeline.save_chunks_to_json(chunks)
        jsonl_file = pipeline.save_chunks_to_jsonl(chunks)
        print(f'[OK] JSON: {json_file}')
        print(f'[OK] JSONL: {jsonl_file}')
        pipeline.print_statistics()
        print('[Step 3] Sample chunks:')
        for i, chunk in enumerate(chunks[:3]):
            print(f'Chunk {i+1}: file={chunk.source_file}, len={len(chunk.content)}')
            print(f'  Content: {chunk.content[:100]}...')
    print('[OK] Done!')

if __name__ == '__main__':
    main()
