
# idea: count the words and save it in a dict. take the words which value are the highest to lowest in k range
from collections import Counter
def top_words(text, k): # top_words("a b a c b a", 2) == ["a", "b"]
    counts = Counter(text.split())
    pairs = counts.most_common(k)
    return [word for word, count in pairs]



# idea:
def missing_number(numbers):
    have = set(numbers)
    for n in range(len(numbers) + 1):
        if n not in have:
            return n

# idea: the sum of 0..n minus the real sum = the missing number
def missing_number(numbers):
    n = len(numbers)
    expected = n * (n + 1) // 2
    return expected - sum(numbers)
# n = len([3, 0, 1])          = 3        → the numbers should be 0, 1, 2, 3
# expected = 3 * 4 // 2       = 6        → 0 + 1 + 2 + 3
# sum([3, 0, 1])              = 4        → what we really have
# 6 - 4                       = 2  ✅    → the one that's missing



# idea: walk the text counting the current letter; when the letter changes, write
#       the old one with its count and start counting the new one; write the last group at the end
def compress(text):
    if not text:
        return ""
    result = ""
    current = text[0]
    count = 1
    for char in text[1:]:
        if char == current:
            count += 1
        else:
            result += f"{current}{count}"
            current = char
            count = 1
    result += f"{current}{count}"
    return result