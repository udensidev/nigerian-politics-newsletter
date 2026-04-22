from typing import List, Dict, Any
from rapidfuzz import fuzz

SOURCE_RANKING = [
    "Premium Times",
    "The Cable",
    "Punch",
    "Vanguard",
    "Daily Trust",
    "The Guardian Nigeria",
    "ThisDay"
]

def get_source_rank(source: str) -> int:
    """
    Get the rank of a source. Lower index means higher rank.
    If not in list, assign a high number (lowest rank).
    """
    try:
        return SOURCE_RANKING.index(source)
    except ValueError:
        return len(SOURCE_RANKING)

def deduplicate(articles: List[Dict[str, Any]], threshold: float = 85.0) -> List[Dict[str, Any]]:
    """
    Deduplicate a list of articles based on fuzzy matching of their titles.
    
    Args:
        articles: List of article dictionaries containing at least 'title' and 'source'
        threshold: The rapidfuzz score above which articles are considered duplicates
        
    Returns:
        A deduplicated list of articles.
    """
    if not articles:
        return []

    # Sort articles by source rank first, so that the first item we see 
    # for any cluster of duplicates is the one from the highest ranked source.
    articles_sorted = sorted(articles, key=lambda a: get_source_rank(a.get("source", "")))
    
    deduplicated: List[Dict[str, Any]] = []
    
    for article in articles_sorted:
        is_duplicate = False
        title = article.get("title", "")
        
        for existing in deduplicated:
            existing_title = existing.get("title", "")
            score = fuzz.token_sort_ratio(title, existing_title)
            
            if score >= threshold:
                is_duplicate = True
                break
                
        if not is_duplicate:
            deduplicated.append(article)
            
    return deduplicated
