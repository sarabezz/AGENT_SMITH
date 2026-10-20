
# idea: split the text into words (list), reverse the list, join it back with spaces
def reverse_words(text):
    reverse = []
    for word in text.split()[::-1]: # start from the last word
        reverse.append(word) # add it to the list and move backwards
    return " ".join(reverse) # join them with spaces

def reverse_words(text):
    return " ".join(text.split()[::-1])


# idea: create a dict, get the length of each word, group each word by its length in the dict
def group_by_length(words):
    result = {}
    for word in words:
        size = len(word)
        if size not in result:
            result[size] = []
        result[size].append(word)
    return result


# idea: s
def merge_sorted(a, b):
    result = []
    i = 0
    j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    result.extend(a[i:])
    result.extend(b[j:])
    return result

def merge_sorted(a, b):
    return sorted(a + b)   

import heapq
def merge_sorted(a, b):
    return list(heapq.merge(a, b))  # the standard library already has the "two piles" algorithm
print(merge_sorted([1, 4, 7], [2, 3, 9]))