
# idea: split the text into words, make the firts letter of each word upper case, and join them back with spaces
def capitalize_words(text):
    words = []
    for word in text.split():
        words.append(word[0].upper() + word[1:])
    return " ".join(words)

def capitalize_words(text):
    return text.title()


# idea: compare how many times appears one word with the next one
def most_common_word(text):
    words = text.split()
    most_common = None
    for word in words:
        if words.count(word) > words.count(most_common):
            most_common = word
    return most_common

from collections import Counter
# idea: count all the words at once, then take the most common one
def most_common_word(text):
    words = text.split()
    if not words:
        return None
    return Counter(words).most_common(1)[0][0] # most_common is a method that comes with Counter
    """Counter(words)                   # Counter({'el': 2, 'gato': 1, 'y': 1, 'perro': 1})
    Counter(words).most_common(1)    # [('el', 2)]     ← a list with the top 1 (word, count)
    ...most_common(1)[0]             # ('el', 2)       ← the first pair
    ...most_common(1)[0][0]          # 'el'            ← only the word"""


# idea: jump through the list in steps of `size`, and cut one slice at each jump
def chunk_list(items, size):
    chunks = []
    for start in range(0, len(items), size):
        chunks.append(items[start:start + size])
    return chunks

def chunk_list(items, size):
    return [items[start:start + size] for start in range(0, len(items), size)]

