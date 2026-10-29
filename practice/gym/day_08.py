
# idea: you can tell the sorted how to sort by key
def sort_by_length(words):
    return sorted(words, key=len)


# idea: .index(n) prints the index of n
def index_of_max(numbers):
    if not numbers:
        return None
    return numbers.index(max(numbers))


# idea: first, clean. compare their sorted letters
def is_anagram(a, b):
    a = a.lower().replace(" ", "")
    b = b.lower().replace(" ", "")
    return sorted(a) == sorted(b) # O(n log n)

from collections import Counter
def is_anagram(a, b):
    a = a.lower().replace(" ", "")
    b = b.lower().replace(" ", "")
    return Counter(a) == Counter(b) # O(n)

# with punctuation: a = "".join(c for c in a.lower() if c.isalpha())


print(is_anagram("listen", "silent"))