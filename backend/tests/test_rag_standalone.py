import sys, os, asyncio, json, re, glob

BACKEND_DIR = r"D:\Desktop\LiveAgentStudio\backend"

def load_env(path):
    env = {}
    if not os.path.exists(path): return env
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

for _p in [
    os.path.join(BACKEND_DIR, '..', 'deploy', '.env'),
    os.path.join(BACKEND_DIR, '.env'),
    os.path.join(BACKEND_DIR, '..', '.env'),
]:
    _p = os.path.normpath(_p)
    if os.path.exists(_p):
        env = load_env(_p)
        print('[ENV] ' + _p)
        break
else:
    env = {}

API_KEY  = env.get('LLM_API_KEY') or env.get('OPENAI_API_KEY') or ''
BASE_URL = env.get('LLM_BASE_URL') or 'https://api.openai.com/v1'
MODEL    = env.get('LLM_MODEL') or env.get('ROUTER_MODEL') or 'qwen-plus'
print('[Config] model=' + MODEL + ' api_key=' + ('set' if API_KEY else 'MISSING'))


class KBRetriever:
    def __init__(self, kb_dir):
        self.chunks = []
        files = glob.glob(os.path.join(kb_dir, '*.jsonl'))
        if not files: print('[WARN] No JSONL'); return
        latest = max(files, key=os.path.getmtime)
        print('[KB] ' + os.path.basename(latest))
        with open(latest, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try: self.chunks.append(json.loads(line))
                    except: pass
        print('[KB] ' + str(len(self.chunks)) + ' chunks')

    def retrieve(self, query, top_k=5):
        kws = set()
        for k in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', query):
            kws.add(k.lower())
            if len(k) >= 4:
                for i in range(len(k)-1):
                    kws.add(k[i:i+2])
        kws = [w for w in kws if len(w) >= 2]
        scored = []
        for idx, c in enumerate(self.chunks):
            content = c.get('content', '').lower()
            s = sum(content.count(w) for w in kws)
            if s > 0:
                scored.append((s, idx, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, _, c in scored[:top_k]]


class LLMClient:
    async def chat(self, system, user):
        if not API_KEY:
            return '[No API key]'
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage
            client = ChatOpenAI(
                model=MODEL,
                api_key=API_KEY,
                base_url=BASE_URL,
                temperature=0.3,
                max_tokens=512,
            )
            resp = await client.ainvoke([
                SystemMessage(content=system),
                HumanMessage(content=user),
            ])
            return resp.content.strip()
        except Exception as e:
            return '[LLM error: ' + str(e) + ']'


async def route(llm, query):
    sys_p = ('你是直播运营AI Router，只做意图分类。'
             '返回纯JSON格式: {"intent":"qa|script|analyst|unknown","confidence":0.9,"reason":""}'
             '不要输出markdown，不要有多余文字。')
    usr_p = json.dumps({'input': query, 'defs': {
        'qa': '商品/规则/售后问答',
        'script': '主播话术/促单/卖点',
        'analyst': '复盘/统计/报告',
        'unknown': '无关直播'
    }}, ensure_ascii=False)
    raw = await llm.chat(sys_p, usr_p)
    try:
        m = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        return json.loads(m.group()) if m else {'intent': 'qa', 'confidence': 0.5, 'reason': 'parse_fail'}
    except:
        return {'intent': 'qa', 'confidence': 0.5, 'reason': 'parse_fail'}


async def qa(llm, retriever, query):
    docs = retriever.retrieve(query)
    if not docs:
        return {'answer': '抱歉，知识库中未找到相关信息。', 'top_src': '', 'n_docs': 0}
    ctx = '\n\n'.join('[' + str(i) + '] ' + d['content'][:400] for i, d in enumerate(docs, 1))
    sys_p = '你是直播电商AI助手，根据知识库内容回答用户问题，简洁准确，不编造信息。'
    usr_p = '知识库:\n' + ctx + '\n\n问题：' + query + '\n请回答：'
    answer = await llm.chat(sys_p, usr_p)
    src = docs[0].get('source_file') or docs[0].get('metadata', {}).get('source_file', '?')
    return {'answer': answer, 'top_src': src, 'n_docs': len(docs)}


async def script_qa(llm, retriever, query):
    docs = retriever.retrieve(query)
    ctx = '\n\n'.join('[' + str(i) + '] ' + d['content'][:400] for i, d in enumerate(docs, 1)) if docs else '暂无资料'
    sys_p = '你是直播主播AI助手，根据商品资料生成简洁有力的直播话术，突出卖点和促单语，语气亲切有感染力。'
    usr_p = '商品资料:\n' + ctx + '\n\n需求：' + query + '\n话术：'
    answer = await llm.chat(sys_p, usr_p)
    return {'answer': answer, 'n_docs': len(docs), 'top_src': ''}


async def main():
    print('\n' + '='*70)
    print('RAG Full Pipeline Test: 用户输入 -> Router -> 检索 -> LLM -> 输出')
    print('='*70)

    retriever = KBRetriever(os.path.join(BACKEND_DIR, 'kb_output'))
    llm = LLMClient()

    queries = [
        '这款蒸汽拖洗机适合什么地板?',
        'FAQ里有关于退货的规定吗?',
        '直播活动有哪些优惠规则?',
        '帮我说一下这款产品的卖点促单话术',
        '今天直播数据复盘一下',
    ]

    for i, query in enumerate(queries, 1):
        print('\n' + '-'*70)
        print('[Q' + str(i) + '] ' + query)
        intent_res = await route(llm, query)
        intent = intent_res.get('intent', 'qa')
        conf   = intent_res.get('confidence', 0)
        reason = intent_res.get('reason', '')
        print('Router -> intent=' + intent + ' conf=' + str(round(conf, 2)) + ' reason=' + str(reason))
        if intent == 'script':
            res = await script_qa(llm, retriever, query)
        elif intent == 'analyst':
            res = {'answer': '[Analyst 待接入]', 'n_docs': 0, 'top_src': ''}
        else:
            res = await qa(llm, retriever, query)
        print('Docs:   ' + str(res.get('n_docs', 0)) + ' retrieved  src=' + str(res.get('top_src', '-')))
        print('Answer: ' + res['answer'][:300])

    print('\n' + '='*70)
    print('[DONE] RAG pipeline test complete')
    print('='*70)


if __name__ == '__main__':
    asyncio.run(main())
