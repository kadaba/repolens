"""Example: classify a repo + polish the description with OpenAI.

Run with:
    OPENAI_API_KEY=sk-... python examples/with_llm_openai.py /path/to/repo

Requires:
    pip install openai
"""
import asyncio
import os
import sys

from app_classifier import classify_async


async def openai_provider(prompt, max_tokens=400, temperature=0.2):
    """Lazy import so this example doesn't require openai at install time."""
    import openai
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content


async def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    result = await classify_async(repo, llm_provider=openai_provider)
    print(f"Category: {result.app_category} ({result.app_category_confidence:.0%})")
    print()
    print("LLM-polished description:")
    print(f"  {result.functional_description}")


if __name__ == "__main__":
    asyncio.run(main())
