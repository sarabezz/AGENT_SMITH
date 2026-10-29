
# idea: 
from collections import Counter
def top_words(text, k): # top_words("a b a c b a", 2) == ["a", "b"]
    counts = {}
    for word in text:
        counts = Counter(word).most_common(k)
    return counts

print(top_words("a b a c b a", 2) == ["a", "b"])