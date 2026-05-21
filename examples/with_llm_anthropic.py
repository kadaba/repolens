"""Example: classify a repo + polish with Anthropic Claude.

Run with:
    ANTHROPIC_API_KEY=sk-ant-... python examples/with_llm_anthropic.py /path/to/repo

Requires:
    pip install anthropic
"""
import asyncio
import os
import sys

from app_classifier import classify_async


async def anthropic_provider(prompt, max_tokens=400, temperature=0.2):
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


async def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    result = await classify_async(repo, llm_provider=anthropic_provider)
    print(f"Category: {result.app_category}")
    print(f"Description: {result.functional_description}")


if __name__ == "__main__":
    asyncio.run(main())
