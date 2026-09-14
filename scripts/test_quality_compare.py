"""
V0.26 minimax 质量对比测试 - 直接调 Anthropic Messages API
避开 litellm minimax 404 问题。

DeepSeek 走 litellm（OpenAI 兼容）
minimax 走 httpx 直接调 Anthropic Messages API（base_url=https://api.minimax.cn/anthropic）
"""
import asyncio
import sys
import time
from pathlib import Path

# 把项目根目录加入 sys.path
ROOT = Path(r'D:/OHMYSTORY/novel2all')
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values

env = dotenv_values(ROOT / '.env')
DEEPSEEK_KEY = env.get('DEEPSEEK_API_KEY')
MINIMAX_KEY = env.get('MINIMAX_API_KEY')

ORIGINAL = (
    '黄晓隆呆了一呆，心里觉得这老和尚说的未尝没有道理，只是事到临头，'
    '他却还是说不出所以然来，只得怔在那里。张羽瞪了老僧一眼，拉了黄晓隆的手，'
    '道：「晓隆，这老和尚古里古怪，我们别理他。」说完便拉他向外边走去。'
    '几个孩子都跟了过去，显然一向以林惊羽马首是瞻。'
)

SYSTEM = (
    '你是一位中文玄幻小说作家，擅长《诛仙》这种古典仙侠风格。\n'
    '要求：\n'
    '1. 保持原文人物语气（黄晓隆/张小凡的少年感、张羽的古灵精怪）\n'
    '2. 描写动作、表情、心理活动\n'
    '3. 用词古朴，避免现代网络用语\n'
    '4. 场景衔接要自然\n'
    '5. 输出大约 500 字'
)

USER = f'请扩写以下片段：\n\n{ORIGINAL}'

OUT_PATH = ROOT / 'scripts' / '_quality_result.md'


async def call_deepseek():
    """DeepSeek flash via litellm OpenAI 兼容"""
    import litellm

    t0 = time.time()
    resp = await litellm.acompletion(
        model='deepseek/deepseek-flash',
        messages=[
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': USER},
        ],
        max_tokens=1500,
        temperature=0.7,
        api_key=DEEPSEEK_KEY,
        extra_body={'thinking': {'type': 'disabled'}},
    )
    elapsed = time.time() - t0
    text = resp.choices[0].message.content
    usage = resp.usage
    return {
        'model': 'deepseek/deepseek-flash',
        'elapsed': round(elapsed, 2),
        'chars': len(text),
        'input_tokens': getattr(usage, 'prompt_tokens', 0),
        'output_tokens': getattr(usage, 'completion_tokens', 0),
        'cache_hit_tokens': getattr(usage, 'prompt_cache_hit_tokens', 0),
        'text': text,
    }


async def call_minimax():
    """minimax-M3 via httpx 直接调 Anthropic Messages API
    (避开 litellm minimax OpenAI 兼容的 404 bug)
    """
    import httpx

    payload = {
        'model': 'MiniMax-M3',
        'max_tokens': 1500,
        'temperature': 0.7,
        'system': SYSTEM,
        'messages': [{'role': 'user', 'content': USER}],
    }
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': MINIMAX_KEY,
        'anthropic-version': '2023-06-01',
        'Authorization': f'Bearer {MINIMAX_KEY}',
    }
    url = 'https://api.minimax.cn/anthropic/v1/messages'

    t0 = time.time()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload, headers=headers)
    elapsed = time.time() - t0

    if r.status_code != 200:
        return {
            'model': 'minimax/MiniMax-M3',
            'elapsed': round(elapsed, 2),
            'chars': 0,
            'error': f'HTTP {r.status_code}: {r.text[:300]}',
            'text': '',
        }

    data = r.json()
    # Anthropic Messages API 响应格式
    content_blocks = data.get('content', [])
    text = ''.join(b.get('text', '') for b in content_blocks if b.get('type') == 'text')
    usage = data.get('usage', {})

    return {
        'model': 'minimax/MiniMax-M3',
        'elapsed': round(elapsed, 2),
        'chars': len(text),
        'input_tokens': usage.get('input_tokens', 0),
        'output_tokens': usage.get('output_tokens', 0),
        'text': text,
    }


async def main():
    results = []
    print('Calling DeepSeek...', flush=True)
    try:
        results.append(await call_deepseek())
        print(f"  done: {results[-1]['chars']} chars", flush=True)
    except Exception as e:
        print(f'  FAILED: {type(e).__name__}: {e}', flush=True)
        results.append({'model': 'deepseek/deepseek-flash', 'error': str(e)})

    print('Calling minimax...', flush=True)
    try:
        results.append(await call_minimax())
        print(f"  done: {results[-1]['chars']} chars", flush=True)
    except Exception as e:
        print(f'  FAILED: {type(e).__name__}: {e}', flush=True)
        results.append({'model': 'minimax/MiniMax-M3', 'error': str(e)})

    # 写入 markdown 结果
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write('# DeepSeek vs minimax 扩写质量对比\n\n')
        f.write(f'**原文：**\n\n```\n{ORIGINAL}\n```\n\n')
        f.write(f'**System prompt：**\n\n```\n{SYSTEM}\n```\n\n---\n\n')
        for r in results:
            f.write(f"## {r['model']}\n\n")
            if 'error' in r:
                f.write(f"**FAILED:** {r['error']}\n\n")
                continue
            f.write(f"- 延迟: {r['elapsed']}s\n")
            f.write(f"- 字数: {r['chars']}\n")
            if 'input_tokens' in r:
                f.write(f"- input_tokens: {r['input_tokens']}\n")
                f.write(f"- output_tokens: {r['output_tokens']}\n")
            if 'cache_hit_tokens' in r:
                f.write(f"- cache_hit_tokens: {r['cache_hit_tokens']}\n")
            f.write('\n**扩写内容：**\n\n')
            f.write(r['text'])
            f.write('\n\n---\n\n')

    print(f'\n结果写入: {OUT_PATH}', flush=True)


asyncio.run(main())
