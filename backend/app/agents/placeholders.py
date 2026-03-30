from app.agents.base import BaseAgent
from app.graph.state import LiveAgentState, StatePatch


class QAPlaceholderAgent(BaseAgent):
    name = "qa"

    def __init__(self, retrieval_pipeline=None):
        self.pipeline = retrieval_pipeline

    async def run(self, state: LiveAgentState) -> StatePatch:
        from app.core.config import settings
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        query = state['user_input']
        context = ''
        retrieved_docs = []
        references = []

        if self.pipeline is not None:
            try:
                context, rerank_results = await self.pipeline.retrieve(
                    query,
                    source_hint=state.get('knowledge_scope'),
                )
                retrieved_docs = [
                    {'doc_id': r.doc_id, 'content': r.content,
                     'score': r.final_score, 'metadata': r.metadata}
                    for r in rerank_results
                ]
                references = [r.doc_id for r in rerank_results]
            except Exception as e:
                import logging
                logging.getLogger(__name__).error('RAG retrieve error: %s', e)
                context = ''

        if not context:
            return {
                'agent_output': '抱歉，知识库中未找到相关信息，请联系人工客服。',
                'references': [],
                'retrieved_docs': [],
                'agent_name': self.name,
            }

        try:
            api_key  = settings.LLM_API_KEY or settings.OPENAI_API_KEY or ''
            base_url = settings.LLM_BASE_URL or settings.OPENAI_BASE_URL or ''
            model    = settings.LLM_MODEL or settings.ROUTER_MODEL or 'qwen-plus'
            llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url,
                             temperature=0.3, max_tokens=512)
            resp = await llm.ainvoke([
                SystemMessage(content='你是直播电商AI助手，根据知识库内容回答用户问题，简洁准确，不编造信息。'),
                HumanMessage(content=f'{context}\n\n用户问题：{query}\n请回答：'),
            ])
            answer = resp.content.strip()
        except Exception as e:
            answer = f'[检索结果摘要]\n{context[:500]}'

        return {
            'agent_output': answer,
            'references': references,
            'retrieved_docs': retrieved_docs,
            'agent_name': self.name,
        }


class ScriptPlaceholderAgent(BaseAgent):
    name = "script"

    def __init__(self, retrieval_pipeline=None):
        self.pipeline = retrieval_pipeline

    async def run(self, state: LiveAgentState) -> StatePatch:
        from app.core.config import settings
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        query = state['user_input']
        context = ''
        retrieved_docs = []
        rerank_results = []

        if self.pipeline is not None:
            try:
                context, rerank_results = await self.pipeline.retrieve(
                    query,
                    source_hint=state.get('knowledge_scope'),
                )
                retrieved_docs = [
                    {'doc_id': r.doc_id, 'content': r.content, 'score': r.final_score}
                    for r in rerank_results
                ]
            except Exception:
                context = ''

        ctx_text = context if context else '暂无相关商品资料'

        try:
            api_key  = settings.LLM_API_KEY or settings.OPENAI_API_KEY or ''
            base_url = settings.LLM_BASE_URL or settings.OPENAI_BASE_URL or ''
            model    = settings.LLM_MODEL or settings.ROUTER_MODEL or 'qwen-plus'
            llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url,
                             temperature=0.5, max_tokens=512)
            resp = await llm.ainvoke([
                SystemMessage(content='你是直播主播AI助手，根据商品资料生成简洁有力的直播话术，突出卖点和促单语，语气亲切有感染力。'),
                HumanMessage(content=f'商品资料:\n{ctx_text}\n\n需求：{query}\n话术：'),
            ])
            answer = resp.content.strip()
        except Exception:
            answer = '建议突出商品卖点、价格锚点和互动口令。'

        return {
            'agent_output': answer,
            'references': [r.doc_id for r in rerank_results],
            'retrieved_docs': retrieved_docs,
            'agent_name': self.name,
        }


class AnalystPlaceholderAgent(BaseAgent):
    name = "analyst"

    async def run(self, state: LiveAgentState) -> StatePatch:
        return {
            'agent_output': '复盘能力将在后续版本接入报表和高频问题统计。',
            'references': [],
            'retrieved_docs': [],
            'agent_name': self.name,
        }
