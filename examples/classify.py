"""Minimal example — classify a repo, print the result."""
import sys
from app_classifier import classify


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    result = classify(repo)
    print(f"Category:   {result.app_category} ({result.app_category_confidence:.0%})")
    print(f"Summary:    {result.one_line_summary}")
    print(f"Features:   {', '.join(result.detected_features) or '(none)'}")
    print()
    print("Description:")
    print(f"  {result.functional_description}")
    print()
    print(f"Routes:    {len(result.routes)}")
    print(f"Models:    {len(result.data_models)}")
    print(f"Databases: {', '.join(result.databases) or '(none)'}")


if __name__ == "__main__":
    main()
