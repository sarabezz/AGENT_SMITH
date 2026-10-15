
def find_max(num_list):
    if not num_list:
        return None  
    result = num_list[0]
    for num in num_list[1:]:
        if num > result:
            result = num
    return result


def count_words(text):
    counts = {}
    for word in text.lower().split():
        if word not in counts:
            counts[word] = 1
        else:
            counts[word] += 1
    return counts

def count_words(text):
    counts = {}
    for word in text.lower().split():
        counts[word] = counts.get(word, 0) + 1 #the value of word, or 0 if it isn’t there yet
    return counts

from collections import Counter
print(Counter("the cat and the dog".split()))
#or in a function:
def count_words(text):
    return dict(Counter(text.split())) #
"""dict(...) turns the Counter into a normal dictionary, so the result looks exactly like the expected one. (A Counter is already a special kind of dictionary, so it works without dict(...) too; the print just looks slightly different.)

Which one to use where:

your if/else version → to show you understand the logic;
.get → shorter, still shows the logic;
Counter → what you’d use in real code.

In an interview, the best order is to write one of the first two, and then mention Counter."""


def has_duplicates(items):
    seen = set()
    for item in items:
        if item in seen:
            return True
        seen.add(item)
    return False

print(has_duplicates([1, 2, 3, 2]))   # True
print(has_duplicates(["a", "b"])) #False

import time

def dup_list(items):
    seen = []
    for item in items:
        if item in seen:
            return True
        seen.append(item)
    return False

def dup_set(items):
    seen = set()
    for item in items:
        if item in seen:
            return True
        seen.add(item)
    return False

numbers = list(range(10000))      # no duplicates: the worst case, every element is checked

start = time.perf_counter()
dup_list(numbers)
print(f"list: {time.perf_counter() - start:.3f} s")

start = time.perf_counter()
dup_set(numbers)
print(f"set:  {time.perf_counter() - start:.3f} s")
