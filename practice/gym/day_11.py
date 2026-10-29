

def count_long_words(text, n):
    count = 0
    for word in text.split():
        if len(word) > n:
            count += 1
    return count

def count_long_words(text, n):
    return sum(len(word) > n for word in text.split())



def sum_of_digits(number):
    text = str(number)
    result = 0
    for char in text:
        result += int(char)
    return result

def sum_of_digits(number):
    return sum(int(char) for char in str(number))



def make_dict(keys, values):
    result = {}
    for k, v in zip(keys, values):
        result[k] = v
    return result

def make_dict(keys, values):
    return dict(zip(keys, values))