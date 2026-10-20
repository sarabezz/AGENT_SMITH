
def is_palindrome(text):
    text = text.lower()
    half = len(text) // 2
    for i in range(half):
        if text()[i] != text[-1-i]:
            return False
    return True

def is_palindrome(text):
    text = text.lower()
    return text == text[::-1]


def first_unique(text):
    for letter in text:
        if text.count(letter) == 1:
            return letter
    return None

from collections import Counter
def first_unique(text):
    counts = Counter(text)
    for letter in text:
        if counts[letter] == 1:
            return letter
    return None


def second_largest(numbers):
    first = None
    second = None
    for n in numbers:
        if first is None or n > first:
            second = first
            first = n
        elif n != first and (second is None or n > second):
            second = n
    return second
