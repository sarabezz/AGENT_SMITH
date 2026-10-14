
def count_vowels(text):
    count = 0
    for letter in text:
        if letter in "aeiou":
            count +=1
    return count


def count_digits(text):
    count = 0
    for char in text:
        if char.isdigit():
            count += 1
    return count


def remove_vowels(text):
    final_text = []
    for letter in text:
        if letter.lower() not in "aeiou":
            final_text.append(letter)
    return "".join(final_text)

def remove_vowels(text):
    final_text = []
    for letter in text:
        if letter not in "aeiouAEIOU":
            final_text.append(letter)
    return "".join(final_text)

def remove_vowels(text):
    return "".join(char for char in text if char.lower() not in "aeiou")